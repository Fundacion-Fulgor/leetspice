"""Headless Magic extraction for SG13G2 layouts."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

DRC_COUNT = re.compile(r"LEETSPICE_DRC_COUNT\s+(\d+)")


class MagicRunner:
    def __init__(
        self,
        pdk_root: str | Path | None = None,
        executable: str = "magic",
        timeout: float = 300,
    ) -> None:
        self.pdk_root = Path(pdk_root or os.getenv("PDK_ROOT", "/opt/IHP-Open-PDK"))
        self.executable = executable
        self.timeout = timeout
        self.rcfile = self.pdk_root / "ihp-sg13g2" / "libs.tech" / "magic" / "ihp-sg13g2.magicrc"

    def _run(self, work: Path, name: str, commands: list[str]) -> str:
        if not self.rcfile.is_file():
            raise ValueError("Magic SG13G2 rcfile is missing")
        script = work / f"{name}.tcl"
        script.write_text(
            "\n".join(["crashbackups stop", "drc off", *commands, "quit -noprompt", ""]),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                self.executable,
                "-dnull",
                "-noconsole",
                "-rcfile",
                str(self.rcfile),
                str(script),
            ],
            cwd=work,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=self.timeout,
            check=False,
            env={**os.environ, "HOME": str(work)},
        )
        if completed.returncode != 0:
            raise ValueError(f"Magic {name} failed: {completed.stdout[-4096:]}")
        return completed.stdout

    @staticmethod
    def _validate(gds: Path, top: str) -> None:
        if not gds.is_file():
            raise ValueError("GDSII file is missing")
        if not top.isidentifier():
            raise ValueError("invalid layout top cell")

    def drc(self, gds: Path, top: str, work: Path) -> int:
        self._validate(gds, top)
        output = self._run(
            work,
            "drc",
            [
                f"gds read {gds}",
                f"load {top}",
                "select top cell",
                "drc on",
                "drc euclidean on",
                "drc style drc(full)",
                "drc check",
                "set drcresult [drc listall why]",
                "set count 0",
                "foreach {errtype coordlist} $drcresult {",
                "  foreach coord $coordlist { set count [expr {$count + 1}] }",
                "}",
                'puts "LEETSPICE_DRC_COUNT $count"',
            ],
        )
        match = DRC_COUNT.search(output)
        if match is None:
            raise ValueError("Magic DRC did not report a violation count")
        return int(match.group(1))

    def extract_lvs(self, gds: Path, top: str, work: Path) -> Path:
        self._validate(gds, top)
        output = work / f"{top}.lvs.spice"
        self._run(
            work,
            "extract_lvs",
            [
                f"gds read {gds}",
                f"load {top}",
                "select top cell",
                f"extract path {work}",
                "extract no capacitance",
                "extract no coupling",
                "extract no resistance",
                "extract no length",
                "extract all",
                "ext2spice lvs",
                f"ext2spice -p {work} -o {output}",
            ],
        )
        if not output.is_file() or output.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("Magic did not produce a bounded LVS netlist")
        return output

    def extract_pex(self, gds: Path, top: str, work: Path, mode: str = "coupled_c") -> Path:
        self._validate(gds, top)
        if mode not in {"coupled_c", "full_rc"}:
            raise ValueError("PEX mode must be coupled_c or full_rc")
        output = work / f"{top}.pex.spice"
        extraction = ["extract all"]
        if mode == "full_rc":
            extraction = [
                "extresist threshold 10000",
                "extract do resistance",
                "extract do unique",
                "extract all",
                "ext2spice extresist on",
            ]
        self._run(
            work,
            "extract_pex",
            [
                f"gds read {gds}",
                f"load {top}",
                "select top cell",
                f"flatten {top}_flat",
                f"load {top}_flat",
                f"cellname delete {top}",
                f"cellname rename {top}_flat {top}",
                "select top cell",
                f"extract path {work}",
                "extract style ngspice()",
                *extraction,
                "ext2spice lvs",
                "ext2spice cthresh 0.01",
                f"ext2spice -p {work} -o {output}",
            ],
        )
        if not output.is_file() or output.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Magic did not produce a bounded PEX netlist")
        return output
