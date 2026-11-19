import io
import json
import shutil
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from leetspice import db
from leetspice.config import Settings
from leetspice.leaderboards import global_leaderboard
from leetspice.limiter import limiter
from leetspice.main import create_app
from leetspice.models import Challenge, Submission, User
from leetspice.testing import (
    VerificationError,
    apply_action,
    bench_order,
    can_tester_edit,
    effective_status,
    expire_verifications,
    invalidate_verification,
)
from leetspice.web import WELCOME_SLUG, _challenge_progress, _leaderboard

CHALLENGES = Path(__file__).parents[1] / "challenges"


def _make_user(email: str, *, tester: bool = False, admin: bool = False) -> int:
    with db.SessionLocal() as session:
        user = User(
            email=email,
            display_name=email.split("@")[0],
            password_hash="unused",
            is_tester=tester,
            is_admin=admin,
        )
        session.add(user)
        session.commit()
        return user.id


def _promote(email: str, *, tester: bool = True, admin: bool = False) -> None:
    with db.SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        user.is_tester = tester
        user.is_admin = admin
        session.commit()


def _accepted(user_id: int, challenge: Challenge, score: float, *, is_test: bool) -> Submission:
    return Submission(
        user_id=user_id,
        challenge_id=challenge.id,
        verification_version=challenge.verification_version,
        status="accepted",
        score=score,
        is_test=is_test,
    )


def _netlist_challenge_with_prerequisites(session) -> Challenge:
    return next(
        challenge
        for challenge in session.scalars(select(Challenge).order_by(Challenge.id))
        if challenge.prerequisites
        and challenge.submission_kind == "netlist"
        and challenge.starter_netlist
    )


@pytest.fixture
def tester(client, register):
    register()
    _promote("designer@example.com")


def test_test_submissions_never_reach_rankings(client) -> None:
    student = _make_user("student@example.com")
    tester_id = _make_user("tester@example.com", tester=True)
    with db.SessionLocal() as session:
        challenge = session.scalar(
            select(Challenge).where(Challenge.is_active.is_(True), Challenge.is_ranked.is_(True))
        )
        session.add_all(
            [
                _accepted(student, challenge, 5.0, is_test=False),
                _accepted(tester_id, challenge, 1.0, is_test=True),
            ]
        )
        session.commit()

        assert [leader.user.id for leader in global_leaderboard(session)] == [student]
        assert [user.id for user, _ in _leaderboard(session, challenge)] == [student]


def test_tester_opens_drafts_and_skips_prerequisites(client, csrf, tester) -> None:
    with db.SessionLocal() as session:
        challenge = _netlist_challenge_with_prerequisites(session)
        challenge.is_active = False
        session.commit()
        slug, netlist = challenge.slug, challenge.starter_netlist

    page = client.get(f"/challenges/{slug}")
    assert page.status_code == 200
    assert "Draft Challenge" in page.text
    response = client.post(
        f"/challenges/{slug}/submit",
        data={"csrf_token": csrf(page), "netlist": netlist},
        follow_redirects=False,
    )
    assert response.status_code == 303
    with db.SessionLocal() as session:
        submission = session.scalar(select(Submission))
        assert submission.is_test is True


def test_students_cannot_see_drafts_or_the_testing_bench(client, register) -> None:
    assert client.get("/testing", follow_redirects=False).status_code == 303
    register()
    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge))
        challenge.is_active = False
        session.commit()
        slug = challenge.slug
    assert client.get(f"/challenges/{slug}").status_code == 404
    assert client.get("/testing").status_code == 403
    assert 'href="/testing"' not in client.get("/").text


def test_testing_bench_claims_and_verifies_through_http(client, csrf, tester) -> None:
    bench = client.get("/testing")
    assert bench.status_code == 200
    assert 'href="/testing"' in bench.text
    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge).order_by(Challenge.id))
        slug = challenge.slug

    claimed = client.post(
        f"/testing/{slug}/claim", data={"csrf_token": csrf(bench)}, follow_redirects=False
    )
    assert claimed.status_code == 303
    refused = client.post(f"/testing/{slug}/verify", data={"csrf_token": csrf(bench)})
    assert refused.status_code == 409
    assert "judge must accept" in refused.text

    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge).where(Challenge.slug == slug))
        user = session.scalar(select(User).where(User.email == "designer@example.com"))
        session.add(_accepted(user.id, challenge, 3.0, is_test=True))
        session.commit()

    verified = client.post(
        f"/testing/{slug}/verify",
        data={"csrf_token": csrf(bench), "score_confirmed": "on"},
        follow_redirects=False,
    )
    assert verified.status_code == 303
    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge).where(Challenge.slug == slug))
        assert challenge.verification_status == "verified"
        assert challenge.verified_version == challenge.verification_version
        assert challenge.claimed_by_id is None


def test_verification_workflow_rules(client) -> None:
    author = _make_user("author@example.com", tester=True)
    other = _make_user("other@example.com", tester=True)
    third = _make_user("third@example.com", tester=True)
    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge).order_by(Challenge.id))
        challenge.created_by_id = author
        session.commit()
        users = {user.id: user for user in session.scalars(select(User))}

        with pytest.raises(VerificationError, match="another tester has to"):
            apply_action(session, users[author], challenge, "claim")
        apply_action(session, users[other], challenge, "claim")
        with pytest.raises(VerificationError):
            apply_action(session, users[third], challenge, "claim")
        with pytest.raises(VerificationError):
            apply_action(session, users[third], challenge, "release")

        session.add(_accepted(other, challenge, 2.0, is_test=True))
        session.commit()
        with pytest.raises(VerificationError, match="Confirm that the score"):
            apply_action(session, users[other], challenge, "verify")
        apply_action(session, users[other], challenge, "verify", score_confirmed=True)
        assert challenge.verification_status == "verified"
        assert challenge.verified_by_id == other

        with pytest.raises(VerificationError, match="Describe the problem"):
            apply_action(session, users[third], challenge, "report")
        apply_action(session, users[third], challenge, "report", notes="Score is inverted")
        assert challenge.verification_status == "problems"
        assert challenge.verification_notes == "Score is inverted"

        with pytest.raises(VerificationError):
            apply_action(session, users[third], challenge, "reopen")
        apply_action(session, users[author], challenge, "reopen")
        assert challenge.verification_status == "unverified"


def test_authors_can_never_verify_their_own_challenge(client) -> None:
    author = _make_user("author@example.com", tester=True)
    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge).order_by(Challenge.id))
        challenge.created_by_id = author
        # Even with a claim in place and an accepted run of their own.
        challenge.verification_status = "testing"
        challenge.claimed_by_id = author
        challenge.claimed_at = datetime.now(UTC)
        session.add(_accepted(author, challenge, 2.0, is_test=True))
        session.commit()
        user = session.get(User, author)

        with pytest.raises(VerificationError, match="another tester has to"):
            apply_action(session, user, challenge, "verify", score_confirmed=True)
        assert challenge.verification_status == "testing"


def test_admins_can_verify_challenges_they_created(client) -> None:
    admin = _make_user("admin@example.com", admin=True)
    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge).order_by(Challenge.id))
        challenge.created_by_id = admin
        session.add(_accepted(admin, challenge, 2.0, is_test=True))
        session.commit()
        user = session.get(User, admin)

        apply_action(session, user, challenge, "claim")
        apply_action(session, user, challenge, "verify", score_confirmed=True)
        assert challenge.verification_status == "verified"


def test_invalidate_verification_clears_the_verification_data() -> None:
    challenge = Challenge(
        verification_status="verified",
        verified_by_id=7,
        verified_at=datetime.now(UTC),
        verified_version=3,
        verification_notes="ok",
    )
    invalidate_verification(challenge)
    assert challenge.verification_status == "unverified"
    assert challenge.verified_by_id is None
    assert challenge.verified_at is None
    assert challenge.verified_version is None
    assert challenge.verification_notes is None

    challenge.verification_status = "problems"
    invalidate_verification(challenge)
    assert challenge.verification_status == "problems"


def test_claims_expire_after_ten_days(client) -> None:
    tester_id = _make_user("tester@example.com", tester=True)
    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge).order_by(Challenge.id))
        user = session.get(User, tester_id)
        claimed_at = datetime.now(UTC) - timedelta(days=10, minutes=1)
        apply_action(session, user, challenge, "claim", now=claimed_at)

        expire_verifications(session, now=claimed_at + timedelta(days=9))
        assert challenge.verification_status == "testing"
        expire_verifications(session)
        assert challenge.verification_status == "unverified"
        assert challenge.claimed_by_id is None


def test_concurrent_claims_only_let_the_first_one_win(client) -> None:
    first = _make_user("first@example.com", tester=True)
    second = _make_user("second@example.com", tester=True)
    with db.SessionLocal() as one, db.SessionLocal() as two:
        # Both testers loaded the challenge while it was still unverified.
        mine = one.scalar(select(Challenge).order_by(Challenge.id))
        theirs = two.get(Challenge, mine.id)
        assert mine.verification_status == theirs.verification_status == "unverified"

        apply_action(one, one.get(User, first), mine, "claim")
        with pytest.raises(VerificationError, match="claimed this challenge first"):
            apply_action(two, two.get(User, second), theirs, "claim")

    with db.SessionLocal() as session:
        stored = session.get(Challenge, mine.id)
        assert stored.verification_status == "testing"
        assert stored.claimed_by_id == first


def test_bench_page_shows_expired_claims_without_writing(client, csrf, tester) -> None:
    other = _make_user("other@example.com", tester=True)
    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge).order_by(Challenge.id))
        challenge.verification_status = "testing"
        challenge.claimed_by_id = other
        challenge.claimed_at = datetime.now(UTC) - timedelta(days=11)
        session.commit()
        slug = challenge.slug
    assert effective_status(challenge) == "unverified"

    bench = client.get("/testing")
    assert f"/testing/{slug}/claim" in bench.text
    with db.SessionLocal() as session:
        stored = session.scalar(select(Challenge).where(Challenge.slug == slug))
        assert stored.verification_status == "testing"
        assert stored.claimed_by_id == other

    claimed = client.post(
        f"/testing/{slug}/claim", data={"csrf_token": csrf(bench)}, follow_redirects=False
    )
    assert claimed.status_code == 303
    with db.SessionLocal() as session:
        stored = session.scalar(select(Challenge).where(Challenge.slug == slug))
        assert stored.verification_status == "testing"
        assert stored.claimed_by_id != other


def test_verification_resets_when_the_judge_version_changes(client) -> None:
    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge).order_by(Challenge.id))
        challenge.verification_status = "verified"
        challenge.verified_version = challenge.verification_version
        session.commit()
        expire_verifications(session)
        assert challenge.verification_status == "verified"

        challenge.verification_version += 1
        session.commit()
        expire_verifications(session)
        assert challenge.verification_status == "unverified"


def test_testers_edit_only_their_drafts_or_reported_challenges() -> None:
    author = User(id=1, email="a@example.com", display_name="a", password_hash="x")
    challenge = Challenge(created_by_id=1, is_active=False, verification_status="unverified")
    assert can_tester_edit(author, challenge)

    challenge.is_active = True
    assert not can_tester_edit(author, challenge)
    challenge.verification_status = "problems"
    assert can_tester_edit(author, challenge)

    stranger = User(id=2, email="b@example.com", display_name="b", password_hash="x")
    assert not can_tester_edit(stranger, challenge)


def test_testers_only_reach_challenge_views_in_the_admin_panel(client, tester) -> None:
    assert client.get("/admin/create-challenge").status_code == 200
    assert client.get("/admin/challenge/list").status_code == 200
    assert client.get("/admin/user/list").status_code == 403
    assert client.get("/admin/submission/list").status_code == 403
    assert client.get("/admin/recent-activity").status_code == 403


def test_bench_lists_published_unverified_first_then_drafts_then_verified() -> None:
    def challenge(id_: int, *, active: bool, state: str) -> Challenge:
        return Challenge(id=id_, curriculum_order=0, is_active=active, verification_status=state)

    verified = challenge(1, active=True, state="verified")
    draft = challenge(2, active=False, state="unverified")
    published = challenge(3, active=True, state="testing")
    verified_draft = challenge(4, active=False, state="verified")
    ordered = sorted([verified, draft, published, verified_draft], key=bench_order)
    assert ordered == [published, draft, verified, verified_draft]


def test_bench_search_filters_by_challenge_name(client, tester) -> None:
    with db.SessionLocal() as session:
        titles = {c.slug: c.title for c in session.scalars(select(Challenge))}
    needle = titles["mos-gmid"][2:-2].lower()
    bench = client.get("/testing", params={"q": needle})
    assert bench.status_code == 200
    for slug, title in titles.items():
        listed = f'class="testing-challenge" href="/challenges/{slug}"' in bench.text
        assert listed == (needle in title.lower())
    assert "No challenge matches" in client.get("/testing", params={"q": "zz-none-zz"}).text


def test_testers_get_the_draft_switch_in_the_catalog(client, register) -> None:
    register()
    assert 'id="adminToggle"' not in client.get("/").text
    _promote("designer@example.com")
    assert 'id="adminToggle"' in client.get("/").text


def test_testers_skip_the_welcome_gate_that_still_locks_students(client, csrf, register) -> None:
    register()
    with db.SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "designer@example.com"))
        challenges = list(session.scalars(select(Challenge).where(Challenge.is_active.is_(True))))
        challenge = next(c for c in challenges if c.slug != WELCOME_SLUG and c.starter_netlist)
        slug, netlist = challenge.slug, challenge.starter_netlist

        assert _challenge_progress(session, user, challenges)[slug] == "locked"
        user.is_tester = True
        session.commit()
        assert _challenge_progress(session, user, challenges)[slug] != "locked"

    page = client.get(f"/challenges/{slug}")
    assert page.status_code == 200
    response = client.post(
        f"/challenges/{slug}/submit",
        data={"csrf_token": csrf(page), "netlist": netlist},
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.fixture
def editable_client(tmp_path):
    """A client whose challenge packages live in a scratch copy that tests may modify."""
    challenges = tmp_path / "challenges"
    shutil.copytree(CHALLENGES, challenges)
    limiter.reset()
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        secret_key="test-secret-key",
        seed_demo=True,
        challenges_path=str(challenges),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client, challenges


def _login_tester_owning(test_client, csrf, slug: str) -> None:
    test_client.post(
        "/register",
        data={
            "email": "author@example.com",
            "display_name": "Author",
            "password": "correct-horse-battery",
            "csrf_token": csrf(test_client.get("/register")),
        },
    )
    with db.SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "author@example.com"))
        user.is_tester = True
        challenge = session.scalar(select(Challenge).where(Challenge.slug == slug))
        challenge.created_by_id = user.id
        challenge.is_active = False
        session.commit()


def _edit_form(slug: str) -> dict[str, str]:
    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge).where(Challenge.slug == slug))
        return {
            "title": "Edited title",
            "summary": challenge.summary,
            "description": challenge.description,
            "track": challenge.track,
            "difficulty": challenge.difficulty,
            "curriculum_order": str(challenge.curriculum_order),
            "category": challenge.category,
            "prerequisites": ", ".join(challenge.prerequisites),
            "expected_subckt": challenge.expected_subckt,
            "expected_pins": ", ".join(challenge.expected_pins),
            "starter_netlist": challenge.starter_netlist,
            "judge_backend": challenge.judge_backend,
            "submission_kind": challenge.submission_kind,
            "score_unit": challenge.score_unit,
            "verification_version": str(challenge.verification_version),
            "is_ranked": "on" if challenge.is_ranked else "",
            "lower_is_better": "on" if challenge.lower_is_better else "",
        }


def _judge_zip(files: dict[str, bytes]) -> bytes:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return archive.getvalue()


def test_testers_edit_their_draft_with_the_challenge_form(editable_client, csrf) -> None:
    test_client, challenges = editable_client
    slug = "mos-gmid"
    _login_tester_owning(test_client, csrf, slug)

    page = test_client.get("/admin/edit-challenge", params={"slug": slug})
    assert page.status_code == 200
    assert "Save Changes" in page.text
    assert 'name="judge_zip"' in page.text
    assert (
        test_client.get("/admin/edit-challenge", params={"slug": "common-source"}).status_code
        == 403
    )

    saved = test_client.post(
        f"/admin/edit-challenge?slug={slug}", data=_edit_form(slug), follow_redirects=False
    )
    assert saved.status_code == 302
    manifest = json.loads((challenges / slug / "challenge.json").read_text(encoding="utf-8"))
    assert manifest["title"] == "Edited title"
    assert manifest["is_active"] is False
    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge).where(Challenge.slug == slug))
        assert challenge.title == "Edited title"
        assert challenge.is_active is False


def test_replacing_the_judge_bumps_the_verification_version(editable_client, csrf) -> None:
    test_client, challenges = editable_client
    slug = "mos-gmid"
    _login_tester_owning(test_client, csrf, slug)
    form = _edit_form(slug)
    judge = challenges / slug / "judge"
    files = {
        f"judge/{path.relative_to(judge).as_posix()}": path.read_bytes()
        for path in judge.rglob("*")
        if path.is_file()
    }

    saved = test_client.post(
        f"/admin/edit-challenge?slug={slug}",
        data=form,
        files={"judge_zip": ("judge.zip", _judge_zip(files), "application/zip")},
        follow_redirects=False,
    )
    assert saved.status_code == 302
    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge).where(Challenge.slug == slug))
        assert challenge.verification_version == int(form["verification_version"]) + 1


def test_broken_judge_upload_keeps_the_previous_package(editable_client, csrf) -> None:
    test_client, challenges = editable_client
    slug = "mos-gmid"
    _login_tester_owning(test_client, csrf, slug)
    before = (challenges / slug / "challenge.json").read_text(encoding="utf-8")
    definition = sorted((challenges / slug / "judge").rglob("*.yaml"))

    response = test_client.post(
        f"/admin/edit-challenge?slug={slug}",
        data=_edit_form(slug),
        files={"judge_zip": ("judge.zip", _judge_zip({"judge/readme.txt": b"x"}), "x/zip")},
    )
    assert "Error saving challenge" in response.text
    assert (challenges / slug / "challenge.json").read_text(encoding="utf-8") == before
    assert sorted((challenges / slug / "judge").rglob("*.yaml")) == definition


def test_authors_see_a_note_instead_of_the_claim_button(client, csrf, tester) -> None:
    with db.SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "designer@example.com"))
        challenge = session.scalar(select(Challenge).order_by(Challenge.id))
        challenge.created_by_id = user.id
        session.commit()
        slug = challenge.slug

    bench = client.get("/testing")
    assert "another tester has to verify it" in bench.text
    assert f"/testing/{slug}/claim" not in bench.text
    refused = client.post(f"/testing/{slug}/claim", data={"csrf_token": csrf(bench)})
    assert refused.status_code == 409
    assert "another tester has to" in refused.text


def test_testers_get_the_admin_panel_button_in_the_profile(client, register) -> None:
    register()
    assert 'href="/admin"' not in client.get("/profile").text
    _promote("designer@example.com")
    assert 'href="/admin"' in client.get("/profile").text
    assert client.get("/admin/").status_code == 200


def test_editing_a_verified_draft_requires_a_new_verification(editable_client, csrf) -> None:
    test_client, _ = editable_client
    slug = "mos-gmid"
    _login_tester_owning(test_client, csrf, slug)
    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge).where(Challenge.slug == slug))
        challenge.verification_status = "verified"
        challenge.verified_version = challenge.verification_version
        challenge.verified_at = datetime.now(UTC)
        session.commit()

    saved = test_client.post(
        f"/admin/edit-challenge?slug={slug}", data=_edit_form(slug), follow_redirects=False
    )
    assert saved.status_code == 302
    with db.SessionLocal() as session:
        challenge = session.scalar(select(Challenge).where(Challenge.slug == slug))
        assert challenge.title == "Edited title"
        assert challenge.verification_status == "unverified"
        assert challenge.verified_at is None
