"""Headless Magic extraction for SG13G2 layouts."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .safe_env import safe_env

DRC_COUNT = re.compile(r"LEETSPICE_DRC_COUNT\s+(\d+)")
DRC_SCALE = re.compile(r"^LEETSPICE_DRC_SCALE\s+([0-9.eE+-]+)\s*$", re.MULTILINE)
DRC_RULE = re.compile(r"^LEETSPICE_DRC_RULE\s+(\d+)\s+(.*?)\s*$")
DRC_BOX = re.compile(r"^LEETSPICE_DRC_BOX\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s*$")
DRC_RULE_ID = re.compile(r"\(([^()]+)\)\s*$")
MAX_DRC_RULES = 50
MAX_DRC_BOXES_PER_RULE = 10

IGNORED_DRC_RULE_PREFIXES = (
    "seal.",
    "sealring",
    "edgeseal",
    "afil.",
    "gfil.",
    "mfil.",
    "m1fil.",
    "m2fil.",
    "m3fil.",
    "m4fil.",
    "m5fil.",
    "tm1fil.",
    "tm2fil.",
    "slt.i",
)
IGNORED_DRC_RULE_IDS = frozenset(
    {
        "pad.d",
        "padb.d",
        "padc.d",
        "m1.j",
        "m1.k",
        "m2.j",
        "m2.k",
        "m3.j",
        "m3.k",
        "m4.j",
        "m4.k",
        "m5.j",
        "m5.k",
        "tm1.c",
        "tm1.d",
        "tm2.c",
        "tm2.d",
        "lbe.i",
    }
)
IGNORED_DRC_DESCRIPTION = re.compile(
    r"\b("
    r"seal\s*ring|edgeseal|"
    r"seal\s+(?:contact|via\d*|topvia\d*|diffusion|metals|passiv)|"
    r"density|coverage\s+ratio|"
    r"(?:diff|activ|gatpoly|poly|metal\d*|topmetal\d*)\s+fill(?:er)?"
    r")\b",
    re.IGNORECASE,
)


def is_ignored_drc_rule(rule_id: str, description: str = "") -> bool:
    """Return True for chip-level density/filler and sealring DRC rules.

    Block-level layout challenges do not include a chip sealring or dummy fill,
    so these rules are excluded from DRC error counts and reports.
    """
    normalized = rule_id.strip().lower()
    if normalized and (
        normalized in IGNORED_DRC_RULE_IDS or normalized.startswith(IGNORED_DRC_RULE_PREFIXES)
    ):
        return True
    return bool(description and IGNORED_DRC_DESCRIPTION.search(description))


class MagicRunner:
    def __init__(
        self,
        pdk_root: str | Path | None = None,
        executable: str = "magic",
        timeout: float = 300,
    ) -> None:
        default_pdk_root = os.getenv("PDK_ROOT", "/opt/IHP-Open-PDK")
        self.pdk_root = Path(pdk_root or default_pdk_root)
        self.executable = executable
        self.timeout = timeout
        self.rcfile = self.pdk_root / "ihp-sg13g2" / "libs.tech" / "magic" / "ihp-sg13g2.magicrc"
        # Per-rule detail of the most recent drc() call (empty when DRC is clean).
        self.drc_violations: list[dict[str, Any]] = []

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
            env=safe_env(HOME=str(work)),
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
                # Magic reports DRC boxes in internal units; derive the um scale from
                # the tech instead of hard-coding it.
                "units internal",
                "box values 0 0 1000000 1000000",
                "units microns",
                "if {[catch {expr {[lindex [box values] 2] / 1000000.0}} unitscale]} "
                "{ set unitscale 0 }",
                "units default",
                'puts "LEETSPICE_DRC_SCALE $unitscale"',
                "set count 0",
                "foreach {errtype coordlist} $drcresult {",
                "  set n [llength $coordlist]",
                "  set count [expr {$count + $n}]",
                '  puts "LEETSPICE_DRC_RULE $n [string map [list \\n { } \\t { }] $errtype]"',
                "  set shown 0",
                "  foreach coord $coordlist {",
                f"    if {{$shown < {MAX_DRC_BOXES_PER_RULE}}} {{",
                '      puts "LEETSPICE_DRC_BOX [join $coord { }]"',
                "      incr shown",
                "    }",
                "  }",
                "}",
                'puts "LEETSPICE_DRC_COUNT $count"',
            ],
        )
        match = DRC_COUNT.search(output)
        if match is None:
            raise ValueError("Magic DRC did not report a violation count")
        violations, saw_rule = self._collect_drc_violations(output)
        self.drc_violations = violations[:MAX_DRC_RULES]
        if saw_rule:
            return sum(int(v["count"]) for v in violations)
        return int(match.group(1))

    @classmethod
    def _parse_drc_violations(cls, output: str) -> list[dict[str, Any]]:
        """Turn Magic's LEETSPICE_DRC_* lines into JSON-friendly per-rule records.

        Each record has the rule id (e.g. ``M1.a``), Magic's description, the number of
        violating boxes and up to ``MAX_DRC_BOXES_PER_RULE`` boxes as ``[x1, y1, x2, y2]``
        in micrometres. Density/filler and sealring rules are filtered out so only
        block-level DRC violations are reported.
        """
        violations, _ = cls._collect_drc_violations(output)
        return violations[:MAX_DRC_RULES]

    @staticmethod
    def _collect_drc_violations(output: str) -> tuple[list[dict[str, Any]], bool]:
        scale_match = DRC_SCALE.search(output)
        scale = float(scale_match.group(1)) if scale_match else 0.0
        violations: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        saw_rule = False
        for line in output.splitlines():
            rule = DRC_RULE.match(line)
            if rule:
                saw_rule = True
                description = rule.group(2)
                id_match = DRC_RULE_ID.search(description)
                rule_id = id_match.group(1) if id_match else ""
                if is_ignored_drc_rule(rule_id, description):
                    current = None
                    continue
                current = {
                    "rule": rule_id,
                    "description": description,
                    "count": int(rule.group(1)),
                    "locations": [],
                }
                violations.append(current)
                continue
            box = DRC_BOX.match(line)
            if box and current is not None and scale > 0:
                current["locations"].append([round(int(v) * scale, 3) for v in box.groups()])
        return violations, saw_rule

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
