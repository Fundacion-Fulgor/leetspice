from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from leetspice.judge.characterization import CharacterizationJudge
from leetspice.judge.definition import load_definition
from leetspice.judge.result import Measurement

NETLIST = ".subckt dut in out vdd vss\nR1 in out 1k\n.ends dut\n"


def package(tmp_path: Path, definition: str | None = None) -> Path:
    root = tmp_path / "challenges" / "test"
    (root / "judge" / "tests").mkdir(parents=True)
    (root / "judge" / "definition.yaml").write_text(
        definition
        or """version: 1
conditions:
  corner: [tt, ss]
  temperature: [27]
tests:
  - name: dc
    template: judge/tests/dc.cir
    timeout: 3
    sweep: {corner: all, temperature: all}
    measurements:
      - {name: gain, unit: V/V, minimum: 5}
      - {name: current, unit: A, maximum: 0.001}
score: {strategy: efficiency, measurement: gain, denominator: current, scale: 0.001}
""",
        encoding="utf-8",
    )
    (root / "judge" / "tests" / "dc.cir").write_text(
        ".lib ${pdk_root}/models.lib mos_${corner}\n"
        ".include submission.spice\n"
        ".temp ${temperature}\n",
        encoding="utf-8",
    )
    return root


def pdk(tmp_path: Path) -> Path:
    root = tmp_path / "pdk"
    spiceinit = root / "ihp-sg13g2" / "libs.tech" / "ngspice" / ".spiceinit"
    spiceinit.parent.mkdir(parents=True)
    spiceinit.write_text("* test init\n", encoding="utf-8")
    return root


def test_definition_rejects_private_path_escape(tmp_path: Path) -> None:
    root = package(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        load_definition(root, "../definition.yaml")


def test_characterization_expands_conditions_and_scores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package(tmp_path)
    pdk_root = pdk(tmp_path)
    calls = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        run = Path(kwargs["cwd"])
        deck = (run / "testbench.cir").read_text(encoding="utf-8")
        assert "submission.spice" in deck
        assert "${" not in deck
        (run / "results.data").write_text("gain 10\ncurrent 0.0005\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CharacterizationJudge(
        challenges_path=tmp_path / "challenges", pdk_root=pdk_root, executable="ngspice"
    ).judge(
        NETLIST, "dut", ["in", "out", "vdd", "vss"], "test", {"definition": "judge/definition.yaml"}
    )

    assert result.accepted
    assert result.score == 20.0
    assert [item.name for item in result.measurements] == [
        "gain_tt_27C",
        "current_tt_27C",
        "gain_ss_27C",
        "current_ss_27C",
    ]
    assert len(calls) == 2
    assert calls[0][1]["stdin"] is subprocess.DEVNULL
    assert calls[0][1]["timeout"] == 3
    assert calls[0][1]["env"]["PDK"] == "ihp-sg13g2"


@pytest.mark.parametrize(
    "output", ["gain nan\ncurrent 1e-4\n", "gain 10\n", "gain 10\ngain 11\ncurrent 1e-4\n"]
)
def test_characterization_rejects_invalid_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    package(tmp_path)
    pdk_root = pdk(tmp_path)

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(kwargs["cwd"], "results.data").write_text(output, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CharacterizationJudge(
        challenges_path=tmp_path / "challenges", pdk_root=pdk_root
    ).judge(
        NETLIST, "dut", ["in", "out", "vdd", "vss"], "test", {"definition": "judge/definition.yaml"}
    )
    assert not result.accepted
    assert result.score == 0


def test_extracted_characterization_uses_private_definition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = package(tmp_path)
    definition = (root / "judge/definition.yaml").read_text(encoding="utf-8")
    (root / "judge/post_layout.yaml").write_text(definition, encoding="utf-8")
    pdk_root = pdk(tmp_path)

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(kwargs["cwd"], "results.data").write_text(
            "gain 10\ncurrent 0.0005\n", encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CharacterizationJudge(
        challenges_path=tmp_path / "challenges", pdk_root=pdk_root
    ).judge_extracted(
        NETLIST,
        "test",
        {"post_layout_definition": "judge/post_layout.yaml"},
    )
    assert result.accepted
    assert "post-layout" in result.message


V2_DEFINITION = """version: 2
conditions:
  corner: [tt, ss]
  temperature: [27, 125]
tests:
  - name: dc
    template: judge/tests/dc.cir
    sweep: {corner: all, temperature: all}
    measurements:
      - {name: gain, unit: V/V, minimum: 5}
      - {name: current, unit: A, maximum: 0.001}
      - {name: output, unit: V, minimum: 0, maximum: 1.2}
score:
  objectives:
    - measurement: gain
      direction: maximize
      aggregation: minimum
      normalization: 10
      weight: 2
    - measurement: current
      direction: minimize
      aggregation: maximum
      normalization: 0.0005
    - measurement: output
      direction: target
      aggregation: nominal
      normalization: 0.1
      target: 0.6
"""


def test_version_two_definition_parses_multi_objective_score(tmp_path: Path) -> None:
    root = package(tmp_path, V2_DEFINITION)
    definition = load_definition(root, "judge/definition.yaml")

    assert definition.version == 2
    assert definition.maximum_runs == 64
    assert definition.total_timeout == 300
    assert [objective.measurement for objective in definition.score.objectives] == [
        "gain",
        "current",
        "output",
    ]
    assert definition.score.objectives[0].weight == 2
    assert definition.score.objectives[-1].target == 0.6


@pytest.mark.parametrize(
    ("original", "replacement", "message"),
    [
        ("normalization: 10", None, "non-empty list"),
        ("normalization: 10", "normalization: 0", "positive"),
        ("weight: 2", "weight: 0", "positive"),
        ("direction: maximize", "direction: sideways", "direction"),
        ("aggregation: minimum", "aggregation: median", "aggregation"),
        ("direction: maximize", "direction: target", "require target"),
    ],
)
def test_version_two_definition_rejects_invalid_objectives(
    tmp_path: Path, original: str, replacement: str | None, message: str
) -> None:
    if replacement is None:
        definition = V2_DEFINITION.replace(
            "objectives:\n    -", "objectives: []\nunused:\n    -", 1
        )
    else:
        definition = V2_DEFINITION.replace(original, replacement, 1)
    root = package(tmp_path, definition)
    assert message is not None
    with pytest.raises(ValueError, match=message):
        load_definition(root, "judge/definition.yaml")


def test_version_two_scoring_is_normalized_weighted_geomean(tmp_path: Path) -> None:
    definition = load_definition(package(tmp_path, V2_DEFINITION), "judge/definition.yaml")
    measurements = [
        Measurement("gain_tt_27C", 20, conditions={"corner": "tt", "temperature": 27}),
        Measurement("gain_ss_125C", 10, conditions={"corner": "ss", "temperature": 125}),
        Measurement("current_tt_27C", 0.00025, conditions={"corner": "tt", "temperature": 27}),
        Measurement(
            "current_ss_125C", 0.0005, conditions={"corner": "ss", "temperature": 125}
        ),
        Measurement("output_tt_27C", 0.6, conditions={"corner": "tt", "temperature": 27}),
        Measurement(
            "output_ss_125C", 0.8, conditions={"corner": "ss", "temperature": 125}
        ),
    ]

    # All three normalized objective factors are one.
    assert CharacterizationJudge._score(definition, measurements) == 1.0


def test_version_two_supports_mean_geomean_and_nominal_aggregation(tmp_path: Path) -> None:
    definition_text = V2_DEFINITION.replace("aggregation: minimum", "aggregation: mean").replace(
        "aggregation: maximum", "aggregation: geomean"
    )
    definition = load_definition(package(tmp_path, definition_text), "judge/definition.yaml")
    measurements = [
        Measurement("gain_tt_27C", 8, conditions={"corner": "tt", "temperature": 27}),
        Measurement("gain_ss_125C", 12, conditions={"corner": "ss", "temperature": 125}),
        Measurement("current_tt_27C", 0.00025, conditions={"corner": "tt", "temperature": 27}),
        Measurement("current_ss_125C", 0.001, conditions={"corner": "ss", "temperature": 125}),
        Measurement("output_tt_27C", 0.6, conditions={"corner": "tt", "temperature": 27}),
        Measurement("output_ss_125C", 0.9, conditions={"corner": "ss", "temperature": 125}),
    ]

    # gain mean=10, current geomean=0.0005, nominal output=target.
    assert CharacterizationJudge._score(definition, measurements) == 1.0


def test_version_two_nominal_aggregation_requires_unique_tt_27c(tmp_path: Path) -> None:
    definition = load_definition(package(tmp_path, V2_DEFINITION), "judge/definition.yaml")
    measurements = [
        Measurement("gain", 10),
        Measurement("current", 0.0005),
        Measurement("output", 0.6),
        Measurement("output_other", 0.7),
    ]
    with pytest.raises(ValueError, match="exactly one"):
        CharacterizationJudge._score(definition, measurements)


def test_definition_enforces_aggregate_execution_limits(tmp_path: Path) -> None:
    definition = V2_DEFINITION.replace(
        "conditions:\n", "execution: {maximum_runs: 3, total_timeout: 12}\nconditions:\n"
    )
    root = package(tmp_path, definition)
    with pytest.raises(ValueError, match="4 runs"):
        load_definition(root, "judge/definition.yaml")

    definition = definition.replace("maximum_runs: 3", "maximum_runs: 4")
    parsed = load_definition(package(tmp_path / "valid", definition), "judge/definition.yaml")
    assert parsed.maximum_runs == 4
    assert parsed.total_timeout == 12


def test_characterization_enforces_total_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    definition = V2_DEFINITION.replace(
        "conditions:\n", "execution: {maximum_runs: 4, total_timeout: 0.001}\nconditions:\n"
    )
    package(tmp_path, definition)
    pdk_root = pdk(tmp_path)
    monkeypatch.setattr("leetspice.judge.characterization.time.monotonic", lambda: 1.0)
    loaded = load_definition(tmp_path / "challenges/test", "judge/definition.yaml")
    loaded = type(loaded)(
        loaded.version,
        loaded.maximum_runs,
        -1,
        loaded.tests,
        loaded.score,
    )
    monkeypatch.setattr("leetspice.judge.characterization.load_definition", lambda *_args: loaded)
    result = CharacterizationJudge(
        challenges_path=tmp_path / "challenges", pdk_root=pdk_root
    ).judge(
        NETLIST,
        "dut",
        ["in", "out", "vdd", "vss"],
        "test",
        {"definition": "judge/definition.yaml"},
    )
    assert not result.accepted
    assert "timed out" in result.message
