from sqlalchemy import select

from leetspice import db
from leetspice.models import Submission, User


def test_registration_login_logout_and_csrf(client, csrf, register):
    response = register()
    assert response.status_code == 303

    home = client.get("/")
    assert "Ada" in home.text
    assert "argon2" not in home.text

    assert client.post("/logout", data={"csrf_token": "wrong"}).status_code == 403
    token = csrf(home)
    assert (
        client.post("/logout", data={"csrf_token": token}, follow_redirects=False).status_code
        == 303
    )

    token = csrf(client.get("/login"))
    response = client.post(
        "/login",
        data={
            "email": "DESIGNER@example.com",
            "password": "correct-horse-battery",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    with db.SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "designer@example.com"))
        assert user is not None
        assert user.password_hash.startswith("$argon2")


def test_submission_preserves_netlist_and_is_private(client, csrf, register):
    register()
    page = client.get("/challenges/demo-cmos-inverter")
    netlist = ".subckt inverter in out vdd vss\nR1 vdd out  10k\n.ends inverter\n"
    response = client.post(
        "/challenges/demo-cmos-inverter/submit",
        data={"csrf_token": csrf(page), "netlist": netlist},
        follow_redirects=False,
    )
    assert response.status_code == 303
    submission_url = response.headers["location"]
    detail = client.get(submission_url)
    assert detail.status_code == 200
    assert "QUEUED" in detail.text

    with db.SessionLocal() as session:
        submission = session.scalar(select(Submission))
        assert submission is not None
        assert submission.netlist == netlist

    home = client.get("/")
    client.post("/logout", data={"csrf_token": csrf(home)})
    register(email="other@example.com", name="Grace")
    assert client.get(submission_url).status_code == 404
    assert client.get(f"{submission_url}/status").status_code == 404


def test_empty_submission_is_rejected(client, csrf, register):
    register()
    page = client.get("/challenges/demo-cmos-inverter")
    response = client.post(
        "/challenges/demo-cmos-inverter/submit",
        data={"csrf_token": csrf(page), "netlist": ""},
    )
    assert response.status_code == 422
    assert "Netlist cannot be empty" in response.text
    with db.SessionLocal() as session:
        assert session.scalar(select(Submission)) is None


def test_leaderboard_uses_each_users_best_accepted_score(client, register):
    register(email="first@example.com", name="First")
    register(email="second@example.com", name="Second")

    with db.SessionLocal() as session:
        users = {user.display_name: user for user in session.scalars(select(User))}
        from leetspice.models import Challenge

        challenge = session.scalar(select(Challenge).where(Challenge.slug == "demo-cmos-inverter"))
        session.add_all(
            [
                Submission(
                    user_id=users["First"].id,
                    challenge_id=challenge.id,
                    netlist="a",
                    status="accepted",
                    score=8.0,
                ),
                Submission(
                    user_id=users["First"].id,
                    challenge_id=challenge.id,
                    netlist="b",
                    status="accepted",
                    score=3.0,
                ),
                Submission(
                    user_id=users["Second"].id,
                    challenge_id=challenge.id,
                    netlist="c",
                    status="accepted",
                    score=5.0,
                ),
                Submission(
                    user_id=users["Second"].id,
                    challenge_id=challenge.id,
                    netlist="d",
                    status="failed",
                    score=1.0,
                ),
            ]
        )
        session.commit()

    response = client.get("/challenges/demo-cmos-inverter/leaderboard")
    assert response.status_code == 200
    assert response.text.index("First") < response.text.index("Second")
    assert ">8 <small>points" in response.text
    assert ">5 <small>points" in response.text
    assert ">3 <small>points" not in response.text


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
