from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import JSON, Float, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from leetspice.judge import (
    CaceJudge,
    JudgeResult,
    LayoutJudge,
    MockJudge,
    NgspiceJudge,
    validate_netlist,
)
from leetspice.worker import configured_backend, process_one

VALID_INVERTER = """* a small CMOS inverter
.subckt inverter in out vdd vss
X_P out in vdd vdd sg13_lv_pmos
+ W=2u L=180n
X_N out in vss vss sg13_lv_nmos W=1u L=180n ; inline comment
Cout out vss 5f
.ends inverter
"""


def test_validate_netlist_accepts_comments_continuations_and_case() -> None:
    assert validate_netlist(VALID_INVERTER, "INVERTER", ["IN", "OUT", "VDD", "VSS"]) is None


def test_validate_netlist_accepts_ihp_gate_count_parameter() -> None:
    netlist = VALID_INVERTER.replace("W=1u L=180n", "W=1u L=130n ng=2")
    assert validate_netlist(netlist, "inverter", ["in", "out", "vdd", "vss"]) is None


@pytest.mark.parametrize(
    ("netlist", "message"),
    [
        ("M1 out in vss vss nmos\n", "outside"),
        (".subckt inverter out in vdd vss\nM1 out in vss vss nmos\n.ends\n", "order"),
        (".subckt wrong in out vdd vss\nM1 out in vss vss nmos\n.ends\n", "name"),
        (".subckt inverter in out vdd vss\n.model nmos NMOS\n.ends\n", "directive"),
        (".subckt inverter in out vdd vss\nV1 vdd vss 1.8\n.ends\n", "not allowed"),
        (".subckt inverter in out vdd vss\nL1 out vss 1n\n.ends\n", "not allowed"),
        (".subckt inverter in out vdd vss\nX1 in out child\n.ends\n", "incomplete X"),
        (
            ".subckt inverter in out vdd vss\nX1 out in vss vss arbitrary W=1u L=130n\n.ends\n",
            "unsupported SG13G2",
        ),
        (".subckt inverter in out vdd vss\nM1 out in vss vss nmos\n", "complete"),
        (".subckt inverter in out vdd vss\n.ends\n", "at least one"),
        ("+ W=1u\n.subckt inverter in out vdd vss\n.ends\n", "continuation"),
        (
            ".subckt inverter in out vdd vss\nM1 out in vss vss nmos\n"
            ".ends\n.subckt inverter in out vdd vss\nM2 out in vss vss nmos\n.ends\n",
            "exactly one",
        ),
        (
            ".subckt inverter in out vdd vss\nM1 out in vss vss nmos\n"
            "M1 out in vdd vdd pmos\n.ends\n",
            "duplicate",
        ),
        (".subckt inverter in out vdd vss\nM1 out in vss vss 'shell'\n.ends\n", "unsafe"),
        (
            ".subckt inverter in out vdd vss\nM1 out in vss vss nmos W={temper}\n.ends\n",
            "invalid MOS parameter",
        ),
        (".subckt inverter in out vdd vss\nR1 out vss 1k extra\n.ends\n", "numeric"),
    ],
)
def test_validate_netlist_rejects_unsafe_or_malformed_input(netlist: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_netlist(netlist, "inverter", ["in", "out", "vdd", "vss"])


def test_validate_netlist_enforces_device_and_size_limits() -> None:
    devices = "\n".join(f"R{index} out vss 1k" for index in range(257))
    with pytest.raises(ValueError, match="256 devices"):
        validate_netlist(
            f".subckt inverter in out vdd vss\n{devices}\n.ends\n",
            "inverter",
            ["in", "out", "vdd", "vss"],
        )
    with pytest.raises(ValueError, match="65536 bytes"):
        validate_netlist("*" + "x" * 65536, "inverter", ["in", "out", "vdd", "vss"])


def test_mock_judge_is_deterministic_and_serializable() -> None:
    judge = MockJudge()
    first = judge.judge(VALID_INVERTER, "inverter", ["in", "out", "vdd", "vss"])
    second = judge.judge(VALID_INVERTER, "inverter", ["in", "out", "vdd", "vss"])

    assert first == second
    assert first.accepted is True
    assert 0 < first.score <= 100
    assert [item.name for item in first.measurements] == [
        "propagation_delay",
        "estimated_power",
        "device_area",
    ]
    assert first.to_dict()["measurements"][0]["unit"] == "ps"


def test_mock_judge_rejects_invalid_and_non_inverter_topologies() -> None:
    invalid = MockJudge().judge(".end\n", "inverter", ["in", "out", "vdd", "vss"])
    assert invalid == JudgeResult(False, 0.0, message="line 1: directive '.end' is not allowed")

    wrong_gate = VALID_INVERTER.replace("X_N out in", "X_N out out")
    result = MockJudge().judge(wrong_gate, "inverter", ["in", "out", "vdd", "vss"])
    assert result.accepted is False
    assert result.score == 0
    assert "CMOS inverter" in result.message


def test_ngspice_runs_only_assembled_testbench(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed["kwargs"] = kwargs
        deck = Path(command[-1]).read_text(encoding="utf-8")
        assert deck != VALID_INVERTER
        assert "XDUT in out vdd vss inverter" in deck
        Path(command[-2]).write_text("delay = 4e-11\npower = 2e-6\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = NgspiceJudge(timeout=3).judge(
        VALID_INVERTER, "inverter", ["in", "out", "vdd", "vss"]
    )

    assert result.accepted is True
    assert observed["command"][1:3] == ["-b", "-o"]
    assert observed["kwargs"]["stdin"] is subprocess.DEVNULL
    assert observed["kwargs"]["timeout"] == 3


def test_ngspice_rejects_direct_user_deck_and_handles_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    direct = NgspiceJudge(testbench_builder=lambda netlist, _name, _pins: netlist)
    assert "directly" in direct.judge(
        VALID_INVERTER, "inverter", ["in", "out", "vdd", "vss"]
    ).message

    def timeout(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired("ngspice", 0.01)

    monkeypatch.setattr(subprocess, "run", timeout)
    result = NgspiceJudge(timeout=0.01).judge(
        VALID_INVERTER, "inverter", ["in", "out", "vdd", "vss"]
    )
    assert result.accepted is False
    assert "timed out" in result.message


class Base(DeclarativeBase):
    pass


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    netlist: Mapped[str] = mapped_column(Text)
    expected_subckt: Mapped[str] = mapped_column(String(50))
    expected_pins: Mapped[list[str]] = mapped_column(JSON)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)


def test_worker_claims_and_persists_a_mock_result() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    with sessions() as session:
        session.add(
            Submission(
                status="queued",
                netlist=VALID_INVERTER,
                expected_subckt="inverter",
                expected_pins=["in", "out", "vdd", "vss"],
            )
        )
        session.commit()

    assert process_one(sessions, Submission, MockJudge()) is True
    assert process_one(sessions, Submission, MockJudge()) is False
    with sessions() as session:
        submission = session.get(Submission, 1)
        assert submission is not None
        assert submission.status == "accepted"
        assert submission.score is not None and submission.score > 0
        assert submission.result_json is not None
        assert submission.result_json["accepted"] is True


def test_worker_populates_application_judge_run_contract() -> None:
    from leetspice.db import Base as ApplicationBase
    from leetspice.models import Challenge, User
    from leetspice.models import Submission as ApplicationSubmission

    engine = create_engine("sqlite://")
    ApplicationBase.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as session:
        user = User(email="worker@example.test", display_name="Worker", password_hash="unused")
        challenge = Challenge(
            slug="inverter",
            title="Inverter",
            summary="Test",
            description="Test",
            expected_subckt="inverter",
            expected_pins=["in", "out", "vdd", "vss"],
        )
        session.add_all([user, challenge])
        session.flush()
        session.add(
            ApplicationSubmission(
                user_id=user.id,
                challenge_id=challenge.id,
                netlist=VALID_INVERTER,
            )
        )
        session.commit()

    assert process_one(sessions, ApplicationSubmission, MockJudge()) is True
    with sessions() as session:
        submission = session.get(ApplicationSubmission, 1)
        assert submission is not None
        assert submission.status == "accepted"
        assert submission.accepted_at is not None
        assert submission.error_message is None
        assert len(submission.judge_runs) == 1
        assert submission.judge_runs[0].backend == "MockJudge"
        assert submission.judge_runs[0].status == "completed"
        assert len(submission.judge_runs[0].measurements) == 3


def test_backend_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEETSPICE_JUDGE_BACKEND", "mock")
    assert isinstance(configured_backend(), MockJudge)
    monkeypatch.delenv("LEETSPICE_JUDGE_BACKEND")
    monkeypatch.setenv("RUNNER_BACKEND", "ngspice")
    assert isinstance(configured_backend(), NgspiceJudge)
    assert isinstance(configured_backend("cace"), CaceJudge)
    assert isinstance(configured_backend("ngspice"), NgspiceJudge)
    with pytest.raises(ValueError, match="unknown"):
        configured_backend("other")


def test_cace_collects_pvt_measurements(tmp_path: Path) -> None:
    run = tmp_path / "RUN_test" / "parameters" / "timing" / "run_0"
    run.mkdir(parents=True)
    (run / "conditions.yaml").write_text("corner: ss\ntemperature: 125\n", encoding="utf-8")
    (run / "timing_0.data").write_text(
        "40e-12 37e-12 55e-12 52e-12 -2.13e-6 1e-6 1.2\n",
        encoding="utf-8",
    )

    measurements = CaceJudge._collect(tmp_path)

    assert len(measurements) == 7
    assert measurements[0].name == "tphl_ss_125C"
    assert measurements[0].value == 40.0
    assert measurements[4].value == 2.13
    assert all(measurement.passed for measurement in measurements)


def test_cace_schematic_embeds_validated_submission() -> None:
    schematic = CaceJudge._schematic(VALID_INVERTER)
    assert VALID_INVERTER.strip() in schematic
    assert "devices/code_shown.sym" in schematic


def test_layout_judge_requires_lvs_success_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    challenge = tmp_path / "challenges" / "layout"
    reference = challenge / "reference"
    reference.mkdir(parents=True)
    (reference / "inverter.spice").write_text(".subckt inverter in out vdd vss\n.ends\n")
    pdk = tmp_path / "pdk" / "ihp-sg13g2" / "libs.tech" / "klayout" / "tech"
    for runner in (pdk / "drc" / "run_drc.py", pdk / "lvs" / "run_lvs.py"):
        runner.parent.mkdir(parents=True, exist_ok=True)
        runner.write_text("# runner\n")
    macro = Path("/app/scripts/inspect-layout.rb")
    original_is_file = Path.is_file
    monkeypatch.setattr(
        Path, "is_file", lambda self: True if self == macro else original_is_file(self)
    )

    def fake_run(
        command: list[str], *_args: object, **_kwargs: object
    ) -> subprocess.CompletedProcess:
        values = {
            part.split("=", 1)[0]: part.split("=", 1)[1]
            for part in command
            if "=" in part
        }
        if "output" in values:
            Path(values["output"]).write_text(
                "top_cell: inverter\narea_um2: 12.5\ncell_count: 1\n"
            )
        elif any("run_drc.py" in part for part in command):
            run_dir = Path(
                next(part.split("=", 1)[1] for part in command if part.startswith("--run_dir="))
            )
            run_dir.mkdir()
            (run_dir / "result.lyrdb").write_text("result")
        else:
            run_dir = Path(
                next(part.split("=", 1)[1] for part in command if part.startswith("--run_dir="))
            )
            run_dir.mkdir()
            (run_dir / "result.lvsdb").write_text("result")
            (run_dir / "result_extracted.cir").write_text("result")
            (run_dir / "result.log").write_text("ERROR : Netlists don't match")
        return subprocess.CompletedProcess(command, 0, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = LayoutJudge(
        challenges_path=tmp_path / "challenges", pdk_root=tmp_path / "pdk"
    ).judge(
        b"gds",
        "inverter",
        ["in", "out", "vdd", "vss"],
        "layout",
        {"reference_netlist": "reference/inverter.spice"},
    )
    assert result.accepted is False
    assert "LVS mismatch" in result.message
    assert result.measurements[-1].passed is False


def test_layout_judge_summarizes_drc_failure() -> None:
    output = """
Rule M3Fil.b: 0 error(s)
Rule LU.a: 1 error(s)
Number of DRC errors for maximum rule set: 3
ERROR | Violated rules are : {'LU.b', 'LU.a', 'M1.d'}
"""

    assert LayoutJudge._drc_failure(output) == (
        "DRC failed with 3 violation(s): LU.a, LU.b, M1.d"
    )


def test_layout_judge_explains_mos_dimension_mismatch(tmp_path: Path) -> None:
    reference = tmp_path / "inverter.spice"
    reference.write_text(
        ".subckt inverter in out vdd vss\n"
        "MN out in vss vss sg13_lv_nmos W=0.74u L=0.13u\n"
        "MP out in vdd vdd sg13_lv_pmos W=1.12u L=0.13u\n"
        ".ends inverter\n"
    )
    extracted = (
        ".SUBCKT inverter vss vdd in out\n"
        "M$1 vdd in out vdd sg13_lv_pmos L=0.13u W=0.3u\n"
        "M$2 vss in out vss sg13_lv_nmos L=0.13u W=0.15u\n"
        ".ENDS inverter\n"
    )

    assert LayoutJudge._lvs_failure(
        extracted, reference, ["in", "out", "vdd", "vss"]
    ) == (
        "LVS mismatch; extracted MOS dimensions: nmos W=0.15u L=0.13u, "
        "pmos W=0.3u L=0.13u; required: nmos W=0.74u L=0.13u, "
        "pmos W=1.12u L=0.13u"
    )


def test_layout_judge_reports_missing_pins_first(tmp_path: Path) -> None:
    reference = tmp_path / "inverter.spice"
    reference.write_text(".subckt inverter in out vdd vss\n.ends inverter\n")

    assert LayoutJudge._lvs_failure(
        ".subckt inverter in out vdd\n.ends inverter\n",
        reference,
        ["in", "out", "vdd", "vss"],
    ) == "LVS mismatch; missing top-level pins: vss"
