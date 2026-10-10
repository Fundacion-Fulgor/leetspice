from sqlalchemy import select

from leetspice import db
from leetspice.leaderboards import global_leaderboard
from leetspice.models import Challenge, Submission, User


def test_global_leaderboard_weights_best_current_accepted_scores(client) -> None:
    with db.SessionLocal() as session:
        users = [
            User(email=f"{name}@example.com", display_name=name, password_hash="hash")
            for name in ("Alpha", "Beta", "Gamma")
        ]
        lower = Challenge(
            slug="lower",
            title="Lower",
            summary="Lower score",
            description="Test",
            expected_subckt="lower",
            expected_pins=["in"],
            lower_is_better=True,
            difficulty="intermediate",
            verification_version=2,
        )
        higher = Challenge(
            slug="higher",
            title="Higher",
            summary="Higher score",
            description="Test",
            expected_subckt="higher",
            expected_pins=["in"],
            lower_is_better=False,
            difficulty="advanced",
        )
        inactive = Challenge(
            slug="inactive",
            title="Inactive",
            summary="Inactive",
            description="Test",
            expected_subckt="inactive",
            expected_pins=["in"],
            difficulty="capstone",
            is_active=False,
        )
        guided = Challenge(
            slug="guided",
            title="Guided",
            summary="Unranked lab",
            description="Test",
            expected_subckt="guided",
            expected_pins=["in"],
            difficulty="capstone",
            is_ranked=False,
        )
        session.add_all([*users, lower, higher, inactive, guided])
        session.flush()
        session.add_all(
            [
                Submission(
                    user_id=users[0].id,
                    challenge_id=lower.id,
                    verification_version=2,
                    status="accepted",
                    score=5,
                ),
                Submission(
                    user_id=users[0].id,
                    challenge_id=lower.id,
                    verification_version=2,
                    status="accepted",
                    score=10,
                ),
                Submission(
                    user_id=users[1].id,
                    challenge_id=lower.id,
                    verification_version=2,
                    status="accepted",
                    score=15,
                ),
                Submission(
                    user_id=users[2].id,
                    challenge_id=lower.id,
                    verification_version=2,
                    status="accepted",
                    score=15,
                ),
                Submission(user_id=users[0].id, challenge_id=higher.id, status="accepted", score=8),
                Submission(
                    user_id=users[1].id, challenge_id=higher.id, status="accepted", score=12
                ),
                Submission(
                    user_id=users[2].id, challenge_id=higher.id, status="accepted", score=12
                ),
                Submission(
                    user_id=users[0].id,
                    challenge_id=lower.id,
                    verification_version=1,
                    status="accepted",
                    score=1,
                ),
                Submission(user_id=users[0].id, challenge_id=higher.id, status="failed", score=100),
                Submission(
                    user_id=users[0].id, challenge_id=inactive.id, status="accepted", score=100
                ),
                Submission(
                    user_id=users[0].id, challenge_id=guided.id, status="accepted", score=100
                ),
            ]
        )
        session.commit()
        leaders = global_leaderboard(session)

    assert [leader.user.display_name for leader in leaders] == ["Beta", "Gamma", "Alpha"]
    assert [leader.rank for leader in leaders] == [1, 1, 3]
    assert leaders[0].total_points == leaders[1].total_points
    assert round(leaders[0].total_points, 6) == round(300 + 200 * 2 / 3, 6)
    assert round(leaders[2].total_points, 6) == 300
    assert all(leader.completed == 2 for leader in leaders)


def test_global_leaderboard_gives_sole_participant_full_points(client) -> None:
    with db.SessionLocal() as session:
        user = User(email="sole@example.com", display_name="Sole", password_hash="hash")
        challenge = session.scalar(select(Challenge).where(Challenge.slug == "demo-cmos-inverter"))
        session.add(user)
        session.flush()
        session.add(
            Submission(
                user_id=user.id,
                challenge_id=challenge.id,
                verification_version=challenge.verification_version,
                status="accepted",
                score=1,
            )
        )
        session.commit()
        leaders = global_leaderboard(session)
    assert leaders[0].rank == 1
    assert leaders[0].total_points == 100
