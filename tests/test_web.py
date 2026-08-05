from hashlib import sha256

from sqlalchemy import select

from leetspice import db
from leetspice.models import Challenge, Submission, User


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


def test_submission_groups_pvt_results_into_nested_tabs(client, register):
    register()
    measurements = [
        {"name": "tphl_ff_125C", "value": 20.0, "unit": "ps", "passed": True},
        {"name": "rise_time_ss_-40C", "value": 51.0, "unit": "ps", "passed": True},
        {"name": "tphl_tt_27C", "value": 30.0, "unit": "ps", "passed": True},
        {"name": "tphl_ss_27C", "value": 40.0, "unit": "ps", "passed": False},
        {"name": "tphl_ss_-40C", "value": 42.0, "unit": "ps", "passed": True},
    ]
    with db.SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "designer@example.com"))
        challenge = session.scalar(select(Challenge).where(Challenge.slug == "demo-cmos-inverter"))
        submission = Submission(
            user_id=user.id,
            challenge_id=challenge.id,
            netlist="reference",
            status="accepted",
            score=25.0,
            result_json={"message": "passed", "measurements": measurements},
        )
        session.add(submission)
        session.commit()
        submission_id = submission.id

    for url in (f"/submissions/{submission_id}", f"/submissions/{submission_id}/status"):
        response = client.get(url)
        assert response.status_code == 200
        assert response.text.index(">SS<") < response.text.index(">TT<")
        assert response.text.index(">TT<") < response.text.index(">FF<")
        assert response.text.index(">-40 °C<") < response.text.index(">27 °C<")
        assert "rise time" in response.text
        assert "rise time ss -40C" not in response.text
        assert 'aria-selected="true" tabindex="0">SS</button>' in response.text
        assert 'aria-selected="true" tabindex="0">-40 °C</button>' in response.text
        assert 'class="failed"><dt>tphl</dt><dd>40.0 ps</dd>' in response.text


def test_submission_keeps_flat_results_for_non_pvt_backend(client, register):
    register()
    with db.SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "designer@example.com"))
        challenge = session.scalar(select(Challenge).where(Challenge.slug == "demo-cmos-inverter"))
        submission = Submission(
            user_id=user.id,
            challenge_id=challenge.id,
            netlist="reference",
            status="accepted",
            result_json={
                "measurements": [{"name": "propagation_delay", "value": 10, "unit": "ps"}]
            },
        )
        session.add(submission)
        session.commit()
        submission_id = submission.id

    response = client.get(f"/submissions/{submission_id}")
    assert "propagation delay" in response.text
    assert 'aria-label="Process corner"' not in response.text


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


def test_stylesheet_url_is_versioned(client):
    response = client.get("/")
    assert "/static/app.css?v=5" in response.text
    assert "Fundación Fulgor" in response.text
    assert "/static/fulgor-mark.png" in response.text


def test_demo_challenge_identifies_target_pdk(client):
    response = client.get("/challenges/demo-cmos-inverter")
    assert response.status_code == 200
    assert "IHP SG13G2" in response.text


def test_layout_challenge_upload_and_assets(client, csrf, register):
    register()
    page = client.get("/challenges/demo-cmos-inverter-layout")
    assert page.status_code == 200
    assert 'enctype="multipart/form-data"' in page.text
    assert 'accept=".gds"' in page.text
    assert "Xschem schematic" in page.text

    schematic = client.get("/challenges/demo-cmos-inverter-layout/assets/schematic")
    assert schematic.status_code == 200
    assert "attachment" in schematic.headers["content-disposition"]
    assert schematic.headers["x-content-type-options"] == "nosniff"
    assert client.get("/challenges/demo-cmos-inverter-layout/assets/reference").status_code == 404

    payload = b"\x00\x06\x00\x02GDS"
    response = client.post(
        "/challenges/demo-cmos-inverter-layout/submit",
        data={"csrf_token": csrf(page)},
        files={"layout": ("inverter.gds", payload, "application/octet-stream")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(response.headers["location"])
    assert "inverter.gds" in detail.text
    assert sha256(payload).hexdigest() in detail.text

    with db.SessionLocal() as session:
        submission = session.scalar(select(Submission).where(Submission.submission_kind == "gds"))
        assert submission is not None
        assert submission.netlist is None
        assert submission.payload_binary == payload
        assert submission.payload_size == len(payload)


def test_layout_challenge_rejects_wrong_or_empty_upload(client, csrf, register):
    register()
    page = client.get("/challenges/demo-cmos-inverter-layout")
    wrong = client.post(
        "/challenges/demo-cmos-inverter-layout/submit",
        data={"csrf_token": csrf(page)},
        files={"layout": ("inverter.zip", b"data", "application/zip")},
    )
    assert wrong.status_code == 422
    assert "must be a .gds file" in wrong.text

    empty = client.post(
        "/challenges/demo-cmos-inverter-layout/submit",
        data={"csrf_token": csrf(wrong)},
        files={"layout": ("inverter.gds", b"", "application/octet-stream")},
    )
    assert empty.status_code == 422
    assert "cannot be empty" in empty.text


def test_layout_starter_wires_touch_all_mos_terminals():
    schematic = (
        __import__("pathlib").Path(__file__).parents[1]
        / "challenges/demo-cmos-inverter-layout/inverter.sch"
    ).read_text()
    expected_wires = (
        "N 0 0 0 50 {lab=in}",
        "N 0 -50 0 0 {lab=in}",
        "N 40 0 40 20 {lab=out}",
        "N 40 -20 40 0 {lab=out}",
        "N 40 -100 40 -80 {lab=vdd}",
        "N 40 -50 50 -50 {lab=vdd}",
        "N 40 50 50 50 {lab=vss}",
        "N 40 80 40 100 {lab=vss}",
    )
    assert all(wire in schematic for wire in expected_wires)


def test_manifest_seeding_and_grouping(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "MOS Foundations" in response.text
    assert "Physical Design" in response.text
    assert "introductory" in response.text
    with db.SessionLocal() as session:
        challenges = session.scalars(select(Challenge)).all()
        assert len(challenges) == 31
        for c in challenges:
            if c.slug == "demo-cmos-inverter":
                assert c.difficulty == "introductory"
                assert "wn" in c.description
            elif c.slug == "demo-cmos-inverter-layout":
                assert c.difficulty == "intermediate"
                assert "DRC" in c.description
