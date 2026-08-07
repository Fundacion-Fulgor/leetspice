"""Batch Netgen LVS for SG13G2 layouts."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

LVS_SUCCESS = "Circuits match uniquely"


class NetgenRunner:
    def __init__(
        self,
        pdk_root: str | Path | None = None,
        executable: str = "netgen",
        timeout: float = 300,
    ) -> None:
        self.pdk_root = Path(pdk_root or os.getenv("PDK_ROOT", "/opt/IHP-Open-PDK"))
        self.executable = executable
        self.timeout = timeout
        self.setup = self.pdk_root / "ihp-sg13g2" / "libs.tech" / "netgen" / "ihp-sg13g2_setup.tcl"

    def lvs(self, extracted: Path, reference: Path, top: str, work: Path) -> str:
        if not top.isidentifier() or not extracted.is_file() or not reference.is_file():
            raise ValueError("invalid Netgen LVS inputs")
        if not self.setup.is_file():
            raise ValueError("Netgen SG13G2 setup is missing")
        report = work / "lvs.out"
        completed = subprocess.run(
            [
                self.executable,
                "-batch",
                "lvs",
                f"{extracted} {top}",
                f"{reference} {top}",
                str(self.setup),
                str(report),
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
        if not report.is_file():
            raise ValueError(f"Netgen did not produce an LVS report: {completed.stdout[-4096:]}")
        result = report.read_text(encoding="utf-8", errors="replace")
        if LVS_SUCCESS not in result:
            raise ValueError("LVS mismatch; Magic extraction does not match the reference")
        return result
