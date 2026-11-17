"""Batch Netgen LVS for SG13G2 layouts."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .safe_env import safe_env

LVS_SUCCESS = "Circuits match uniquely"
LVS_PROPERTY_ERROR = "Property errors were found"
SUBCKT_MOS_PATTERN = re.compile(
    r"^X\S+\s+(?:\S+\s+){4}sg13_[lh]v_[np]mos\b",
    re.IGNORECASE | re.MULTILINE,
)
PRIMITIVE_MOS_PATTERN = re.compile(
    r"^M(\S+\s+(?:\S+\s+){4}sg13_[lh]v_[np]mos\b)",
    re.IGNORECASE | re.MULTILINE,
)


class NetgenRunner:
    def __init__(
        self,
        pdk_root: str | Path | None = None,
        executable: str = "netgen",
        timeout: float = 300,
    ) -> None:
        default_pdk_root = os.getenv("PDK_ROOT", "/opt/IHP-Open-PDK")
        self.pdk_root = Path(pdk_root or default_pdk_root)
        self.executable = executable
        self.timeout = timeout
        self.setup = self.pdk_root / "ihp-sg13g2" / "libs.tech" / "netgen" / "ihp-sg13g2_setup.tcl"
        self.last_report: str = ""

    @staticmethod
    def _prepare_reference(extracted: Path, reference: Path, work: Path) -> Path:
        """Align SG13G2 MOS instance prefixes with Magic's subcircuit extraction."""
        extracted_text = extracted.read_text(encoding="utf-8", errors="replace")
        reference_text = reference.read_text(encoding="utf-8", errors="replace")
        if SUBCKT_MOS_PATTERN.search(extracted_text) and PRIMITIVE_MOS_PATTERN.search(
            reference_text
        ):
            normalized = PRIMITIVE_MOS_PATTERN.sub(r"X\1", reference_text)
            target = work / "reference.lvs.spice"
            target.write_text(normalized, encoding="utf-8")
            return target
        return reference

    def lvs(self, extracted: Path, reference: Path, top: str, work: Path) -> str:
        if not top.isidentifier() or not extracted.is_file() or not reference.is_file():
            raise ValueError("invalid Netgen LVS inputs")
        if not self.setup.is_file():
            raise ValueError("Netgen SG13G2 setup is missing")
        report = work / "lvs.out"
        ref_to_use = self._prepare_reference(extracted, reference, work)
        completed = subprocess.run(
            [
                self.executable,
                "-batch",
                "lvs",
                f"{extracted} {top}",
                f"{ref_to_use} {top}",
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
            env=safe_env(HOME=str(work)),
        )
        if not report.is_file():
            raise ValueError(f"Netgen did not produce an LVS report: {completed.stdout[-4096:]}")
        result = report.read_text(encoding="utf-8", errors="replace")
        self.last_report = result
        if LVS_SUCCESS not in result or LVS_PROPERTY_ERROR in result:
            raise ValueError("LVS mismatch; Magic extraction does not match the reference")
        return result
