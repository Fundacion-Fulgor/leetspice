import re

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

from leetspice import db
from leetspice.auth import SSO_PASSWORD_MARKER, hash_password
from leetspice.config import Settings
from leetspice.limiter import limiter
from leetspice.main import create_app
from leetspice.models import User

SECRET = "proxy-secret-for-tests-0123456789"


@pytest.fixture
def sso_client(tmp_path):
    limiter.reset()
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'sso.db'}",
        secret_key="test-secret-key",
        seed_demo=True,
        sso_enabled=True,
        sso_proxy_secret=SECRET,
    )
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def headers():
    def build(
        uid="uid-ada",
        email="ada@ffulgor.org",
        name="Ada Lovelace",
        username="ada",
        groups="",
        secret=SECRET,
    ):
        values = {
            "X-Authentik-Uid": uid,
            "X-Authentik-Email": email,
            "X-Authentik-Name": name,
            "X-Authentik-Username": username,
            "X-Authentik-Groups": groups,
        }
        if secret is not None:
            values["X-Leetspice-Proxy-Secret"] = secret
        return {k: v for k, v in values.items() if v is not None}

    return build


def _users() -> list[User]:
    with db.SessionLocal() as session:
        return list(session.scalars(select(User).order_by(User.id)))


def _user(**where) -> User:
    with db.SessionLocal() as session:
        return session.scalars(select(User).filter_by(**where)).one()


def test_first_request_creates_the_account_from_the_headers(sso_client, headers):
    response = sso_client.get("/profile", headers=headers())
    assert response.status_code == 200
    assert "ada@ffulgor.org" in response.text
    (user,) = _users()
    assert user.authentik_uid == "uid-ada"
    assert user.authentik_username == "ada"
    assert user.email == "ada@ffulgor.org"
    assert user.display_name == "Ada Lovelace"
    assert user.password_hash == SSO_PASSWORD_MARKER
    assert not user.is_admin and not user.is_tester


def test_email_is_lowercased_and_repeat_requests_reuse_the_account(sso_client, headers):
    sso_client.get("/", headers=headers(email="Ada@FFulgor.org"))
    sso_client.get("/", headers=headers(email="ada@ffulgor.org"))
    (user,) = _users()
    assert user.email == "ada@ffulgor.org"


def test_name_and_username_are_refreshed_on_each_request(sso_client, headers):
    sso_client.get("/", headers=headers())
    sso_client.get("/", headers=headers(name="Ada Byron", username="abyron"))
    user = _user(authentik_uid="uid-ada")
    assert (user.display_name, user.authentik_username) == ("Ada Byron", "abyron")


def test_existing_account_is_linked_by_exact_email_only(sso_client, headers):
    with db.SessionLocal() as session:
        session.add(
            User(
                email="ada@ffulgor.org",
                display_name="Old Ada",
                password_hash=hash_password("correct-horse-battery"),
            )
        )
        session.add(User(email="bob@ffulgor.org", display_name="Bob", password_hash="x"))
        session.commit()
    sso_client.get("/", headers=headers(email="ADA@ffulgor.org"))
    users = {u.email: u for u in _users()}
    assert len(users) == 2
    assert users["ada@ffulgor.org"].authentik_uid == "uid-ada"
    assert users["ada@ffulgor.org"].password_hash.startswith("$argon2")  # kept, so rollback works
    assert users["bob@ffulgor.org"].authentik_uid is None

    # A near-miss email is a new account, not a link.
    sso_client.get("/", headers=headers(uid="uid-x", email="ada@bec.ffulgor.org"))
    assert len(_users()) == 3


def test_uid_keeps_the_account_after_an_email_change(sso_client, headers):
    sso_client.get("/", headers=headers())
    first_id = _user(authentik_uid="uid-ada").id
    sso_client.get("/", headers=headers(email="ada.lovelace@fundacionfulgor.org.ar"))
    users = _users()
    assert len(users) == 1
    assert users[0].id == first_id
    assert users[0].email == "ada.lovelace@fundacionfulgor.org.ar"


def test_email_of_an_account_linked_to_another_uid_is_refused(sso_client, headers):
    sso_client.get("/", headers=headers())
    response = sso_client.get("/", headers=headers(uid="uid-other"))
    assert response.status_code == 409
    assert len(_users()) == 1

    sso_client.get("/", headers=headers(uid="uid-bob", email="bob@ffulgor.org"))
    clash = sso_client.get("/", headers=headers(uid="uid-bob", email="ada@ffulgor.org"))
    assert clash.status_code == 409
    assert _user(authentik_uid="uid-bob").email == "bob@ffulgor.org"


def test_roles_follow_the_groups_in_both_directions(sso_client, headers):
    sso_client.get("/", headers=headers())
    user = _user(authentik_uid="uid-ada")
    assert (user.is_admin, user.is_tester) == (False, False)

    sso_client.get("/", headers=headers(groups="eda-users|leetspice-tester"))
    user = _user(authentik_uid="uid-ada")
    assert (user.is_admin, user.is_tester) == (False, True)

    sso_client.get("/", headers=headers(groups="leetspice-admin"))
    user = _user(authentik_uid="uid-ada")
    assert (user.is_admin, user.is_tester) == (True, False)

    sso_client.get("/", headers=headers(groups="leetspice-admin|leetspice-tester"))
    user = _user(authentik_uid="uid-ada")
    assert (user.is_admin, user.is_tester) == (True, True)

    # Removed from every group: back to a normal user at the next request.
    sso_client.get("/", headers=headers(groups="eda-users"))
    user = _user(authentik_uid="uid-ada")
    assert (user.is_admin, user.is_tester) == (False, False)
    sso_client.get("/", headers=headers(groups=""))
    assert not _user(authentik_uid="uid-ada").is_admin


def test_group_names_must_match_exactly(sso_client, headers):
    sso_client.get("/", headers=headers(groups="leetspice-admins|xleetspice-tester|leetspice-dev"))
    user = _user(authentik_uid="uid-ada")
    assert (user.is_admin, user.is_tester) == (False, False)


def test_roles_apply_to_the_admin_panel_and_testing_bench(sso_client, headers):
    plain = sso_client.get("/testing", headers=headers(), follow_redirects=False)
    assert plain.status_code in (302, 303, 403)
    admin = sso_client.get("/admin/", headers=headers(groups="leetspice-admin"))
    assert admin.status_code == 200
    # Same session cookie, role removed in Authentik: access goes away at once.
    revoked = sso_client.get("/admin/", headers=headers(groups=""), follow_redirects=False)
    assert revoked.status_code in (302, 303, 403)


def test_cookie_cannot_override_the_proxy_identity(sso_client, headers):
    sso_client.get("/", headers=headers())
    other = sso_client.get("/profile", headers=headers(uid="uid-bob", email="bob@ffulgor.org"))
    assert "bob@ffulgor.org" in other.text and "ada@ffulgor.org" not in other.text


@pytest.mark.parametrize(
    "drop",
    [
        {"secret": None},
        {"secret": "wrong-secret"},
        {"secret": ""},
        {"uid": None},
        {"uid": ""},
        {"email": None},
        {"email": "not-an-email"},
        {"email": "a@b@ffulgor.org"},
    ],
)
def test_requests_without_valid_proxy_headers_are_rejected(sso_client, headers, drop):
    response = sso_client.get("/", headers=headers(**drop))
    assert response.status_code == 403
    assert _users() == []


def test_spoofed_identity_without_the_secret_creates_nothing(sso_client):
    spoof = {
        "X-Authentik-Uid": "evil",
        "X-Authentik-Email": "x@ffulgor.org",
        "X-Authentik-Groups": "leetspice-admin",
    }
    assert sso_client.get("/", headers=spoof).status_code == 403
    assert sso_client.get("/admin/", headers=spoof).status_code == 403
    assert sso_client.post("/logout", headers=spoof, data={"csrf_token": "x"}).status_code == 403
    assert _users() == []


def test_no_headers_at_all_is_rejected_but_health_stays_open(sso_client):
    assert sso_client.get("/").status_code == 403
    assert sso_client.get("/static/app.css").status_code == 403
    assert sso_client.get("/health").status_code == 200


def test_static_files_are_served_with_the_secret_and_no_identity(sso_client):
    response = sso_client.get("/static/app.css", headers={"X-Leetspice-Proxy-Secret": SECRET})
    assert response.status_code == 200
    assert _users() == []


def test_local_signup_and_password_login_are_off(sso_client, headers):
    h = headers()
    assert sso_client.get("/register", headers=h, follow_redirects=False).status_code == 303
    assert sso_client.get("/login", headers=h, follow_redirects=False).status_code == 303
    form = {
        "email": "n@ffulgor.org",
        "display_name": "N",
        "password": "correct-horse-battery",
        "csrf_token": "x",
    }
    assert sso_client.post("/register", headers=h, data=form).status_code == 404
    assert sso_client.post("/login", headers=h, data=form).status_code == 404
    assert [u.email for u in _users()] == ["ada@ffulgor.org"]


def test_profile_changes_are_refused_and_logout_goes_to_authentik(sso_client, headers):
    h = headers()
    token = _csrf_from_nav(sso_client.get("/", headers=h))
    assert (
        sso_client.post(
            "/profile", headers=h, data={"display_name": "Mallory", "csrf_token": token}
        ).status_code
        == 404
    )
    password = sso_client.post(
        "/profile/password",
        headers=h,
        data={
            "current_password": "x",
            "new_password": "y" * 12,
            "confirm_password": "y" * 12,
            "csrf_token": token,
        },
    )
    assert password.status_code == 422
    assert _user(authentik_uid="uid-ada").display_name == "Ada Lovelace"
    out = sso_client.post("/logout", headers=h, data={"csrf_token": token}, follow_redirects=False)
    assert out.status_code == 303
    assert out.headers["location"] == "/outpost.goauthentik.io/sign_out"


def _csrf_from_nav(response) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def test_sso_without_a_proxy_secret_does_not_start():
    with pytest.raises(ValidationError):
        Settings(sso_enabled=True, sso_proxy_secret="")
    with pytest.raises(ValidationError):
        Settings(sso_enabled=True, sso_proxy_secret="short")
    Settings(sso_enabled=False)


def test_no_duplicate_accounts_are_created(sso_client, headers):
    for _ in range(3):
        sso_client.get("/", headers=headers())
    with db.SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1
