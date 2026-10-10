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
