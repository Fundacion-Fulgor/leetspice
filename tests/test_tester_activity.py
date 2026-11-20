from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from leetspice import db
from leetspice.models import Challenge, User
from leetspice.testing import collect_tester_activity


def _user(session, name: str, *, tester: bool = False, admin: bool = False) -> User:
    user = User(
        email=f"{name}@example.com",
        display_name=name,
        password_hash="unused",
        is_tester=tester,
        is_admin=admin,
    )
    session.add(user)
    session.flush()
    return user


def _verify(challenge: Challenge, user: User) -> None:
    challenge.verification_status = "verified"
    challenge.verified_by_id = user.id
    challenge.verified_version = challenge.verification_version


def test_tester_activity_counts_verified_created_and_testing(client) -> None:
    with db.SessionLocal() as session:
        ana = _user(session, "ana", tester=True)
        beto = _user(session, "beto", tester=True)
        carla = _user(session, "carla", tester=True)
        dani = _user(session, "dani", admin=True)
        _user(session, "student")
        _user(session, "idle-admin", admin=True)
        c = list(session.scalars(select(Challenge).order_by(Challenge.id)))

        _verify(c[0], ana)
        _verify(c[1], ana)
        # Neither a reported verification nor one made on an old judge version counts.
        _verify(c[2], ana)
        c[2].verification_status = "problems"
        _verify(c[3], ana)
        c[3].verified_version = c[3].verification_version - 1
        c[0].created_by_id = ana.id
        c[4].created_by_id = beto.id
        c[5].verification_status = "testing"
        c[5].claimed_by_id = beto.id
        c[5].claimed_at = datetime.now(UTC)
        # An expired claim is no longer "testing".
        c[6].verification_status = "testing"
        c[6].claimed_by_id = carla.id
        c[6].claimed_at = datetime.now(UTC) - timedelta(days=11)
        c[7].created_by_id = dani.id
        # Admins do a tester's work too.
        _verify(c[8], dani)
        session.commit()

        rows = {row.user.display_name: row for row in collect_tester_activity(session)}
        order = [row.user.display_name for row in collect_tester_activity(session)]

    # Every tester and every admin, even without activity; never plain students.
    assert set(rows) == {"ana", "beto", "carla", "dani", "idle-admin"}
    assert {ch.id for ch in rows["ana"].verified} == {c[0].id, c[1].id}
    assert [ch.id for ch in rows["ana"].created] == [c[0].id]
    assert [ch.id for ch in rows["beto"].created] == [c[4].id]
    assert [ch.id for ch in rows["beto"].testing] == [c[5].id]
    assert rows["carla"].verified == rows["carla"].created == rows["carla"].testing == ()
    assert [ch.id for ch in rows["dani"].created] == [c[7].id]
    assert [ch.id for ch in rows["dani"].verified] == [c[8].id]
    assert rows["idle-admin"].verified == rows["idle-admin"].created == ()
    # Most verified first, then most created, then by name.
    assert order == ["ana", "dani", "beto", "carla", "idle-admin"]


def _make_current_user(*, admin: bool = False, tester: bool = False) -> None:
    with db.SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "designer@example.com"))
        user.is_admin = admin
        user.is_tester = tester
        session.commit()


def test_admins_see_the_tester_activity_page(client, register) -> None:
    register()
    _make_current_user(admin=True)
    with db.SessionLocal() as session:
        ana = _user(session, "ana", tester=True)
        challenge = session.scalar(select(Challenge).order_by(Challenge.id))
        _verify(challenge, ana)
        challenge.created_by_id = ana.id
        session.commit()
        title, slug = challenge.title, challenge.slug

    page = client.get("/admin/tester-activity")
    assert page.status_code == 200
    assert "Activity by tester and admin" in page.text
    # The signed-in admin is listed even with no activity of their own.
    assert "designer@example.com" in page.text
    assert "ana@example.com" in page.text
    assert f'href="/challenges/{slug}"' in page.text
    assert title in page.text


def test_testers_cannot_open_the_tester_activity_page(client, register) -> None:
    register()
    _make_current_user(tester=True)
    assert client.get("/admin/tester-activity").status_code == 403
