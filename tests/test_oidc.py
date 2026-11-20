import base64
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from authlib.jose import JsonWebKey, jwt
from fastapi.testclient import TestClient

from leetspice import db, oidc
from leetspice.auth import OIDC_PASSWORD_MARKER, verify_password
from leetspice.config import Settings
from leetspice.limiter import limiter
from leetspice.main import create_app
from leetspice.models import User

ISSUER = "https://auth.example.org/application/o/leetspice/"
CLIENT_ID = "leetspice-client"
KEY = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "test-key"})
JWKS = {"keys": [KEY.as_dict(is_private=False)]}
DISCOVERY = {
    "issuer": ISSUER,
    "authorization_endpoint": "https://auth.example.org/application/o/authorize/",
    "token_endpoint": "https://auth.example.org/application/o/token/",
    "userinfo_endpoint": "https://auth.example.org/application/o/userinfo/",
    "jwks_uri": "https://auth.example.org/application/o/leetspice/jwks/",
}


class FakeIdp:
    """Stands in for Authentik: serves discovery, JWKS, token and userinfo."""

    def __init__(self):
        self.claims: dict = {}
        self.id_token_overrides: dict = {}
        self.userinfo: dict = {}
        self.token_requests: list[httpx.Request] = []

    def sign(self, nonce: str) -> str:
        now = int(time.time())
        payload = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "iat": now,
            "exp": now + 300,
            "nonce": nonce,
            **self.claims,
            **self.id_token_overrides,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        header = {"alg": "RS256", "kid": "test-key"}
        return jwt.encode(header, payload, KEY).decode()

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json=DISCOVERY)
        if url == DISCOVERY["jwks_uri"]:
            return httpx.Response(200, json=JWKS)
        if url == DISCOVERY["token_endpoint"]:
            self.token_requests.append(request)
            return httpx.Response(
                200,
                json={"access_token": "at", "token_type": "Bearer", "id_token": self.nonce_token},
            )
        if url == DISCOVERY["userinfo_endpoint"]:
            return httpx.Response(200, json=self.userinfo)
        return httpx.Response(404)


@pytest.fixture
def idp(monkeypatch):
    fake = FakeIdp()
    transport = httpx.MockTransport(fake.handler)
    monkeypatch.setattr(oidc, "_http", lambda: httpx.Client(transport=transport))
    oidc.clear_cache()
    return fake


def make_client(tmp_path, **overrides):
    limiter.reset()
    values = {
        "database_url": f"sqlite:///{tmp_path / 'oidc.db'}",
        "secret_key": "test-secret-key",
        "seed_demo": False,
        "oidc_issuer": ISSUER,
        "oidc_client_id": CLIENT_ID,
        "oidc_client_secret": "shh",
        **overrides,
    }
    return TestClient(create_app(Settings(**values)))


@pytest.fixture
def sso(tmp_path):
    with make_client(tmp_path, oidc_admin_group="lab-admins") as client:
        yield client


def begin(client, idp):
    """Hit the login route and return (state, nonce) from the redirect."""
    response = client.get("/auth/oidc/login", follow_redirects=False)
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    idp.nonce_token = idp.sign(query["nonce"][0])
    return query["state"][0], query["nonce"][0]


def sign_in(client, idp, claims, state=None, **overrides):
    idp.claims = claims
    idp.id_token_overrides = overrides
    real_state, _ = begin(client, idp)
    return client.get(
        "/auth/oidc/callback",
        params={"code": "abc", "state": state or real_state},
        follow_redirects=False,
    )


def get_user(email):
    with db.SessionLocal() as session:
        return session.query(User).filter(User.email == email).one()


def test_disabled_returns_404(client):
    assert client.get("/auth/oidc/login", follow_redirects=False).status_code == 404
    assert client.get("/auth/oidc/callback").status_code == 404
    assert "Sign in with" not in client.get("/login").text


def test_button_shown_when_enabled(sso):
    assert "/auth/oidc/login" in sso.get("/login").text
    assert "Sign in with Fundación Fulgor" in sso.get("/register").text


def test_login_redirects_with_pkce(sso, idp):
    response = sso.get("/auth/oidc/login", follow_redirects=False)
    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert location.geturl().startswith(DISCOVERY["authorization_endpoint"])
    query = parse_qs(location.query)
    assert query["code_challenge_method"] == ["S256"]
    for key in ("code_challenge", "state", "nonce"):
        assert query[key][0]
    assert query["client_id"] == [CLIENT_ID]
    assert query["scope"] == ["openid email profile"]


def test_callback_creates_user_and_logs_in(sso, idp):
    response = sign_in(sso, idp, {"sub": "u1", "email": "New@Example.com", "name": "Nia"})
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    user = get_user("new@example.com")
    assert user.oidc_subject == "u1"
    assert user.display_name == "Nia"
    assert user.password_hash == OIDC_PASSWORD_MARKER
    assert "Nia" in sso.get("/").text
    # PKCE verifier and client credentials were sent to the token endpoint.
    sent = idp.token_requests[0]
    assert b"code_verifier=" in sent.content
    assert sent.headers["authorization"].startswith("Basic ")


def test_display_name_falls_back_to_local_part(sso, idp):
    sign_in(sso, idp, {"sub": "u2", "email": "grace@example.com"})
    assert get_user("grace@example.com").display_name == "grace"


def test_admin_group_grants_and_revokes(sso, idp):
    base = {"sub": "u3", "email": "boss@example.com", "name": "Boss"}
    sign_in(sso, idp, {**base, "groups": ["lab-admins", "other"]})
    assert get_user("boss@example.com").is_admin is True
    sign_in(sso, idp, {**base, "groups": ["other"]})
    assert get_user("boss@example.com").is_admin is False


def test_no_admin_group_leaves_is_admin_untouched(tmp_path, idp):
    with make_client(tmp_path) as client:
        base = {"sub": "u4", "email": "keep@example.com", "name": "Keep"}
        sign_in(client, idp, {**base, "groups": ["lab-admins"]})
        assert get_user("keep@example.com").is_admin is False
        with db.SessionLocal() as session:
            session.query(User).filter(User.email == "keep@example.com").one().is_admin = True
            session.commit()
        sign_in(client, idp, {**base, "groups": []})
        assert get_user("keep@example.com").is_admin is True


def test_links_existing_local_user_and_password_still_works(sso, idp, register, csrf):
    register("local@example.com", "Local")
    sso.post("/logout", data={"csrf_token": csrf(sso.get("/profile"))})
    response = sign_in(sso, idp, {"sub": "u5", "email": "local@example.com", "name": "Other"})
    assert response.status_code == 303
    user = get_user("local@example.com")
    assert user.oidc_subject == "u5"
    assert user.display_name == "Local"
    assert user.password_hash != OIDC_PASSWORD_MARKER
    sso.post("/logout", data={"csrf_token": csrf(sso.get("/profile"))})
    login = sso.post(
        "/login",
        data={
            "email": "local@example.com",
            "password": "correct-horse-battery",
            "csrf_token": csrf(sso.get("/login")),
        },
        follow_redirects=False,
    )
    assert login.status_code == 303


def test_userinfo_fallback(sso, idp):
    idp.userinfo = {
        "sub": "u6",
        "email": "info@example.com",
        "name": "Info",
        "groups": ["lab-admins"],
    }
    sign_in(sso, idp, {"sub": "u6"})
    user = get_user("info@example.com")
    assert user.display_name == "Info"
    assert user.is_admin is True


def test_missing_email_rejected(sso, idp):
    response = sign_in(sso, idp, {"sub": "u7"})
    assert response.status_code == 400
    assert "Single sign-on failed" in response.text


def test_state_mismatch_rejected(sso, idp):
    response = sign_in(sso, idp, {"sub": "u8", "email": "x@example.com"}, state="forged")
    assert response.status_code == 400
    assert "Single sign-on failed" in response.text
    assert not idp.token_requests


def test_callback_without_login_rejected(sso, idp):
    response = sso.get("/auth/oidc/callback", params={"code": "c", "state": "s"})
    assert response.status_code == 400


def test_state_cannot_be_replayed(sso, idp):
    idp.claims = {"sub": "u9", "email": "replay@example.com"}
    state, _ = begin(sso, idp)
    params = {"code": "abc", "state": state}
    assert sso.get("/auth/oidc/callback", params=params, follow_redirects=False).status_code == 303
    assert sso.get("/auth/oidc/callback", params=params, follow_redirects=False).status_code == 400


def test_idp_error_shows_friendly_page(sso, idp):
    begin(sso, idp)
    response = sso.get("/auth/oidc/callback", params={"error": "access_denied"})
    assert response.status_code == 400
    assert "Single sign-on failed" in response.text


def test_nonce_mismatch_rejected(sso, idp):
    response = sign_in(sso, idp, {"sub": "u10", "email": "n@example.com"}, nonce="wrong")
    assert response.status_code == 400
    assert sso.get("/").text.count("n@example.com") == 0


def test_bad_audience_rejected(sso, idp):
    response = sign_in(sso, idp, {"sub": "u11", "email": "a@example.com"}, aud="someone-else")
    assert response.status_code == 400


def test_bad_issuer_and_expired_rejected(sso, idp):
    claims = {"sub": "u12", "email": "i@example.com"}
    assert sign_in(sso, idp, claims, iss="https://evil.example/").status_code == 400
    assert sign_in(sso, idp, claims, exp=int(time.time()) - 600).status_code == 400


def test_bad_signature_rejected(sso, idp):
    other = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "test-key"})
    response = sign_in(sso, idp, {"sub": "u13", "email": "s@example.com"})
    assert response.status_code == 303  # sanity: the genuine key is accepted
    state, nonce = begin(sso, idp)
    now = int(time.time())
    payload = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "exp": now + 300,
        "nonce": nonce,
        "sub": "u13",
        "email": "s@example.com",
    }
    idp.nonce_token = jwt.encode({"alg": "RS256", "kid": "test-key"}, payload, other).decode()
    response = sso.get("/auth/oidc/callback", params={"code": "c", "state": state})
    assert response.status_code == 400


def test_symmetric_algorithm_rejected(sso, idp):
    """An HS256 token keyed with the public JWKS must not be accepted (key confusion)."""
    state, nonce = begin(sso, idp)
    now = int(time.time())
    payload = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "exp": now + 300,
        "nonce": nonce,
        "sub": "u14",
        "email": "h@example.com",
    }

    # Built by hand: authlib itself refuses to HMAC-sign with a public key.
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64(json.dumps({"alg": "HS256", "kid": "test-key", "typ": "JWT"}).encode())
    body = b64(json.dumps(payload).encode())
    secret = KEY.as_pem(is_private=False)
    signature = hmac.new(secret, f"{header}.{body}".encode(), hashlib.sha256).digest()
    idp.nonce_token = f"{header}.{body}.{b64(signature)}"
    response = sso.get("/auth/oidc/callback", params={"code": "c", "state": state})
    assert response.status_code == 400


def test_oidc_password_marker_never_verifies():
    assert verify_password(OIDC_PASSWORD_MARKER, OIDC_PASSWORD_MARKER) is False
    assert verify_password(OIDC_PASSWORD_MARKER, "") is False


def test_oidc_user_cannot_password_login_or_change_password(sso, idp, csrf):
    sign_in(sso, idp, {"sub": "u14", "email": "sso@example.com", "name": "Sso"})
    profile = sso.get("/profile")
    assert "managed by Fundación Fulgor" in profile.text
    token = csrf(profile)
    change = sso.post(
        "/profile/password",
        data={
            "current_password": OIDC_PASSWORD_MARKER,
            "new_password": "brand-new-password",
            "confirm_password": "brand-new-password",
            "csrf_token": token,
        },
    )
    assert change.status_code == 422
    assert get_user("sso@example.com").password_hash == OIDC_PASSWORD_MARKER

    sso.post("/logout", data={"csrf_token": token})
    for password in (OIDC_PASSWORD_MARKER, "anything-at-all"):
        response = sso.post(
            "/login",
            data={
                "email": "sso@example.com",
                "password": password,
                "csrf_token": csrf(sso.get("/login")),
            },
        )
        assert response.status_code == 401


def test_discovery_is_cached(sso, idp, monkeypatch):
    calls = []
    original = idp.handler
    monkeypatch.setattr(
        oidc,
        "_http",
        lambda: httpx.Client(
            transport=httpx.MockTransport(lambda r: (calls.append(str(r.url)), original(r))[1])
        ),
    )
    begin(sso, idp)
    begin(sso, idp)
    assert sum(url.endswith("openid-configuration") for url in calls) == 1
    assert json.dumps(JWKS)
