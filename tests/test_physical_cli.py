from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from leetspice.judge.magic import MagicRunner
from leetspice.judge.netgen import NetgenRunner


def toolchain(tmp_path: Path) -> tuple[Path, Path, Path]:
    pdk = tmp_path / "pdk"
    rcfile = pdk / "ihp-sg13g2/libs.tech/magic/ihp-sg13g2.magicrc"
    setup = pdk / "ihp-sg13g2/libs.tech/netgen/ihp-sg13g2_setup.tcl"
    rcfile.parent.mkdir(parents=True)
    setup.parent.mkdir(parents=True)
    rcfile.write_text("rc", encoding="utf-8")
    setup.write_text("setup", encoding="utf-8")
    gds = tmp_path / "test.gds"
    gds.write_bytes(b"gds")
    return pdk, gds, setup


def test_magic_builds_drc_lvs_and_full_rc_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdk, gds, _ = toolchain(tmp_path)
    observed = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        script = Path(command[-1]).read_text(encoding="utf-8")
        observed.append((command, kwargs, script))
        if "extract_lvs" in command[-1]:
            (tmp_path / "top.lvs.spice").write_text(".subckt top a\n.ends\n")
        if "extract_pex" in command[-1]:
            (tmp_path / "top.pex.spice").write_text(".subckt top a\n.ends\n")
        return subprocess.CompletedProcess(command, 0, "LEETSPICE_DRC_COUNT 3")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = MagicRunner(pdk_root=pdk)
    assert runner.drc(gds, "top", tmp_path) == 3
    assert runner.extract_lvs(gds, "top", tmp_path).name == "top.lvs.spice"
    assert runner.extract_pex(gds, "top", tmp_path, "full_rc").name == "top.pex.spice"
    assert "drc style drc(full)" in observed[0][2]
    assert "extract no capacitance" in observed[1][2]
    assert "ext2spice lvs" in observed[1][2]
    assert "extract do resistance" in observed[2][2]
    assert "ext2spice extresist on" in observed[2][2]
    assert observed[0][1]["stdin"] is subprocess.DEVNULL


def test_netgen_requires_unique_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdk, _, setup = toolchain(tmp_path)
    extracted = tmp_path / "extracted.spice"
    reference = tmp_path / "reference.spice"
    extracted.write_text("netlist", encoding="utf-8")
    reference.write_text("netlist", encoding="utf-8")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert str(setup) in command
        Path(command[-1]).write_text("Circuits match uniquely", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert "match uniquely" in NetgenRunner(pdk_root=pdk).lvs(extracted, reference, "top", tmp_path)


def test_magic_rejects_invalid_top(tmp_path: Path) -> None:
    pdk, gds, _ = toolchain(tmp_path)
    with pytest.raises(ValueError, match="top cell"):
        MagicRunner(pdk_root=pdk).drc(gds, "bad-name", tmp_path)


def test_magic_drc_reports_per_rule_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdk, gds, _ = toolchain(tmp_path)
    output = "\n".join(
        [
            "Magic noise that must be ignored",
            "LEETSPICE_DRC_SCALE 0.005",
            "LEETSPICE_DRC_RULE 3 Metal1 width < 0.16um (M1.a)",
            "LEETSPICE_DRC_BOX 1116 39 1117 71",
            "LEETSPICE_DRC_BOX 1148 -115 1149 39",
            "LEETSPICE_DRC_RULE 1 Some rule without an id",
            "LEETSPICE_DRC_BOX 0 0 200 400",
            "LEETSPICE_DRC_COUNT 4",
        ]
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, output)

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = MagicRunner(pdk_root=pdk)
    assert runner.drc(gds, "top", tmp_path) == 4
    first, second = runner.drc_violations
    assert first["rule"] == "M1.a"
    assert first["description"] == "Metal1 width < 0.16um (M1.a)"
    assert first["count"] == 3  # total boxes, even though only 2 are listed
    assert first["locations"] == [[5.58, 0.195, 5.585, 0.355], [5.74, -0.575, 5.745, 0.195]]
    assert second["rule"] == ""
    assert second["locations"] == [[0.0, 0.0, 1.0, 2.0]]


def test_magic_drc_ignores_density_filler_and_sealring_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdk, gds, _ = toolchain(tmp_path)
    output = "\n".join(
        [
            "LEETSPICE_DRC_SCALE 0.005",
            "LEETSPICE_DRC_RULE 2 Metal1 width < 0.16um (M1.a)",
            "LEETSPICE_DRC_BOX 100 100 200 200",
            "LEETSPICE_DRC_RULE 4 Diff fill width < 1.0um (AFil.a)",
            "LEETSPICE_DRC_BOX 300 300 400 400",
            "LEETSPICE_DRC_RULE 3 Metal1 density < 35% (M1.k)",
            "LEETSPICE_DRC_BOX 500 500 600 600",
            "LEETSPICE_DRC_RULE 1 Seal Contact width != 0.16um (Seal.c1)",
            "LEETSPICE_DRC_BOX 700 700 800 800",
            "LEETSPICE_DRC_COUNT 10",
        ]
    )

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, output),
    )
    runner = MagicRunner(pdk_root=pdk)
    assert runner.drc(gds, "top", tmp_path) == 2
    assert len(runner.drc_violations) == 1
    assert runner.drc_violations[0]["rule"] == "M1.a"
    assert runner.drc_violations[0]["locations"] == [[0.5, 0.5, 1.0, 1.0]]


def test_magic_drc_returns_zero_when_only_ignored_rules_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdk, gds, _ = toolchain(tmp_path)
    output = "\n".join(
        [
            "LEETSPICE_DRC_SCALE 0.005",
            "LEETSPICE_DRC_RULE 4 Diff fill spacing to Diff < 0.42um (AFil.c1 - AFil.e)",
            "LEETSPICE_DRC_BOX 300 300 400 400",
            "LEETSPICE_DRC_RULE 1 Sealring missing or broken (Seal.a)",
            "LEETSPICE_DRC_BOX 700 700 800 800",
            "LEETSPICE_DRC_COUNT 5",
        ]
    )

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, output),
    )
    runner = MagicRunner(pdk_root=pdk)
    assert runner.drc(gds, "top", tmp_path) == 0
    assert runner.drc_violations == []
