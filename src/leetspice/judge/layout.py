"""KLayout-backed IHP SG13G2 GDS verification."""

from __future__ import annotations

import multiprocessing
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

import yaml

from .characterization import CharacterizationJudge
from .magic import MagicRunner, is_ignored_drc_rule
from .netgen import NetgenRunner
from .result import JudgeResult, Measurement
from .safe_env import safe_env

MAX_GDS_BYTES = 8 * 1024 * 1024
DRC_RULES_PATTERN = re.compile(r"Violated rules are\s*:\s*\{([^}]*)\}")
DRC_COUNT_PATTERN = re.compile(r"Number of DRC errors for maximum rule set:\s*(\d+)", re.IGNORECASE)
SUBCKT_DECL_PATTERN = re.compile(r"^\.subckt\s+(\S+)\s+(.+)$", re.IGNORECASE | re.MULTILINE)
MOS_PATTERN = re.compile(
    r"^[MX]\S+\s+(?:\S+\s+){4}(sg13_[lh]v_[np]mos)\s+(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
MOS_PARAMETER_PATTERN = re.compile(r"\b([WL])\s*=\s*([^\s]+)", re.IGNORECASE)
PROPERTY_HEADER_PATTERN = re.compile(r"^(\S+)\s+vs\.\s+(\S+):\s*$")
PROPERTY_LINE_PATTERN = re.compile(
    r"^\s*(\S+)\s+circuit1:\s*(\S+)\s+circuit2:\s*(\S+)\s*(.*)$",
    re.IGNORECASE,
)
COLUMN_SPLIT_PATTERN = re.compile(r"(?:^|\s+)\|")
MOS_PORT_TRANSLATIONS = (
    (re.compile(r"(sg13_[lh]v_[np]mos)/\(1\|3\)", re.IGNORECASE), r"\1/(drain|source)"),
    (re.compile(r"(sg13_[lh]v_[np]mos)/1\b", re.IGNORECASE), r"\1/drain"),
    (re.compile(r"(sg13_[lh]v_[np]mos)/2\b", re.IGNORECASE), r"\1/gate"),
    (re.compile(r"(sg13_[lh]v_[np]mos)/3\b", re.IGNORECASE), r"\1/source"),
    (re.compile(r"(sg13_[lh]v_[np]mos)/4\b", re.IGNORECASE), r"\1/bulk"),
)


class _InspectCrashed(Exception):
    """The isolated worker died without reporting a result."""


def _child_main(conn: Connection, target: Callable[..., Any], args: tuple[Any, ...]) -> None:
    try:
        # Only ValueError text is reported back; other failures exit non-zero so
        # internal details such as paths are not leaked.
        try:
            conn.send(("ok", target(*args)))
        except ValueError as error:
            conn.send(("error", str(error)))
    finally:
        conn.close()


def _run_isolated(target: Callable[..., Any], args: tuple[Any, ...], timeout: float) -> Any:
    """Run target(*args) in a spawned child so native crashes and hangs stay contained."""
    ctx = multiprocessing.get_context("spawn")
    recv, send = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child_main, args=(send, target, args), daemon=True)
    try:
        proc.start()
        send.close()  # parent's copy; lets recv() see EOF if the child dies
        if not recv.poll(timeout):
            proc.kill()
            raise subprocess.TimeoutExpired("layout", timeout)
        try:
            kind, value = recv.recv()
        except (EOFError, OSError):
            raise _InspectCrashed("worker exited without a result") from None
        if kind == "error":
            raise ValueError(value)
        return value
    finally:
        if proc.is_alive():
            proc.kill()
        if proc.pid is not None:
            proc.join()
        recv.close()
        send.close()
        proc.close()


def _format_mos_terminals(text: str) -> str:
    for pattern, replacement in MOS_PORT_TRANSLATIONS:
        text = pattern.sub(replacement, text)
    return text


def _format_si_length(raw: str) -> str:
    try:
        val = float(raw)
    except ValueError:
        return raw
    if 0 < abs(val) < 1e-3:
        return f"{round(val * 1e6, 4):g}u"
    return raw


class LayoutJudge:
    """Run server-owned SG13G2 DRC and LVS decks against a bounded GDSII payload."""

    def __init__(
        self,
        challenges_path: str | Path | None = None,
        pdk_root: str | Path | None = None,
        timeout: float = 300.0,
    ) -> None:
        default_challenges_path = os.getenv("CHALLENGES_PATH", "/app/challenges")
        default_pdk_root = os.getenv("PDK_ROOT", "/opt/IHP-Open-PDK")
        self.challenges_path = Path(challenges_path or default_challenges_path)
        self.pdk_root = Path(pdk_root or default_pdk_root)
        self.timeout = timeout

    def judge(
        self,
        payload: bytes,
        expected_top: str,
        expected_pins: list[str],
        fixture_path: str,
        config: dict[str, object],
    ) -> JudgeResult:
        if not payload or len(payload) > MAX_GDS_BYTES:
            return JudgeResult(False, 0.0, message="GDSII payload is empty or exceeds 8 MiB")
        if not expected_top.isidentifier() or not fixture_path:
            return JudgeResult(False, 0.0, message="invalid layout challenge configuration")

        challenge_root = (self.challenges_path / fixture_path).resolve()
        reference = (challenge_root / str(config.get("reference_netlist", ""))).resolve()
        try:
            reference.relative_to(challenge_root)
        except ValueError:
            return JudgeResult(False, 0.0, message="reference netlist escapes challenge root")
        if not reference.is_file():
            return JudgeResult(False, 0.0, message="layout reference netlist is missing")

        magicrc = self.pdk_root / "ihp-sg13g2/libs.tech/magic/ihp-sg13g2.magicrc"
        netgen_setup = self.pdk_root / "ihp-sg13g2/libs.tech/netgen/ihp-sg13g2_setup.tcl"
        if not all(path.is_file() for path in (magicrc, netgen_setup)):
            return JudgeResult(False, 0.0, message="layout verification toolchain is incomplete")

        try:
            with tempfile.TemporaryDirectory(prefix="leetspice-layout-") as directory:
                work = Path(directory)
                gds = work / "submission.gds"
                gds.write_bytes(payload)

                deadline = time.monotonic() + self.timeout

                def rem_time():
                    t = deadline - time.monotonic()
                    if t <= 0:
                        raise subprocess.TimeoutExpired("layout", self.timeout)
                    return t

                try:
                    area, cell_count = self._inspect_isolated(gds, expected_top, rem_time())
                except _InspectCrashed:
                    return JudgeResult(
                        False, 0.0, message="GDSII parsing failed: malformed layout or crash"
                    )

                magic = MagicRunner(pdk_root=self.pdk_root, timeout=rem_time())
                violations = magic.drc(gds, expected_top, work)
                if violations:
                    return JudgeResult(
                        False,
                        0.0,
                        (
                            Measurement("bounding_box_area", round(area, 6), "um^2", True),
                            Measurement("cell_count", float(cell_count), "cells", True),
                            Measurement("drc", float(violations), "violations", False),
                        ),
                        f"DRC failed with {violations} violation(s)",
                        details={"drc_violations": magic.drc_violations}
                        if magic.drc_violations
                        else {},
                    )

                magic.timeout = rem_time()
                extracted = magic.extract_lvs(gds, expected_top, work)
                netgen = NetgenRunner(pdk_root=self.pdk_root, timeout=rem_time())
                try:
                    netgen.lvs(extracted, reference, expected_top, work)
                except ValueError:
                    extracted_text = extracted.read_text(encoding="utf-8", errors="replace")
                    lvs_report = self._build_lvs_report(
                        extracted_text,
                        reference,
                        expected_pins,
                        expected_top=expected_top,
                        lvs_output=netgen.last_report,
                    )
                    return JudgeResult(
                        False,
                        0.0,
                        (
                            Measurement("bounding_box_area", round(area, 6), "um^2", True),
                            Measurement("cell_count", float(cell_count), "cells", True),
                            Measurement("drc", 0.0, "violations", True),
                            Measurement("lvs", 0.0, "match", False),
                        ),
                        self._lvs_failure(
                            extracted_text,
                            reference,
                            expected_pins,
                            expected_top=expected_top,
                            lvs_output=netgen.last_report,
                        ),
                        details={"lvs_report": lvs_report} if lvs_report else {},
                    )

                magic.timeout = rem_time()
                pex = magic.extract_pex(
                    gds, expected_top, work, str(config.get("pex_mode", "coupled_c"))
                )
                electrical = CharacterizationJudge(
                    challenges_path=self.challenges_path,
                    pdk_root=self.pdk_root,
                ).judge_extracted(
                    self._normalize_pex_pins(
                        pex.read_text(encoding="utf-8", errors="replace"),
                        expected_top,
                        expected_pins,
                    ),
                    fixture_path,
                    config,
                )
                if not electrical.accepted:
                    return JudgeResult(
                        False,
                        0.0,
                        (
                            Measurement("bounding_box_area", round(area, 6), "um^2", True),
                            Measurement("cell_count", float(cell_count), "cells", True),
                            Measurement("drc", 0.0, "violations", True),
                            Measurement("lvs", 1.0, "match", True),
                            Measurement("pex", 1.0, "extracted", True),
                            *electrical.measurements,
                        ),
                        electrical.message,
                    )
        except subprocess.TimeoutExpired:
            return JudgeResult(
                False,
                0.0,
                message=f"layout verification timed out after {self.timeout:g}s",
            )
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
            return JudgeResult(False, 0.0, message=f"layout verification failed: {error}")

        measurements = (
            Measurement("bounding_box_area", round(area, 6), "um^2", True),
            Measurement("cell_count", float(cell_count), "cells", True),
            Measurement("drc", 0.0, "violations", True),
            Measurement("lvs", 1.0, "match", True),
            Measurement("pex", 1.0, "extracted", True),
            *electrical.measurements,
        )
        score = round(electrical.score * 1_000.0 / max(area, 0.001), 6)
        return JudgeResult(
            True,
            score,
            measurements,
            "SG13G2 DRC, LVS, PEX, and post-layout characterization passed",
        )

    def _run(self, command: list[str], stage: str) -> None:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=self.timeout,
            check=False,
            env=safe_env(HOME="/tmp", KLAYOUT_PATH=""),
        )
        if completed.returncode != 0:
            if stage == "DRC":
                raise ValueError(self._drc_failure(completed.stdout))
            output = completed.stdout[-8_192:]
            raise ValueError(f"{stage} failed: {output}")

    def _inspect_isolated(self, gds: Path, expected_top: str, timeout: float) -> tuple[float, int]:
        return _run_isolated(LayoutJudge._inspect, (gds, expected_top), timeout)

    @staticmethod
    def _inspect(gds: Path, expected_top: str) -> tuple[float, int]:
        from klayout import db as kdb

        layout = kdb.Layout()
        layout.read(str(gds))
        tops = sorted(cell.name for cell in layout.top_cells())
        if tops != [expected_top]:
            raise ValueError(f"expected exactly one top cell {expected_top!r}, found {tops!r}")
        bbox = layout.cell(expected_top).bbox()
        if bbox.empty():
            raise ValueError("top cell is empty")
        area = bbox.width() * layout.dbu * bbox.height() * layout.dbu
        if area <= 0:
            raise ValueError("layout area is not positive")
        return area, layout.cells()

    @staticmethod
    def _normalize_pex_pins(netlist: str, top: str, pins: list[str]) -> str:
        pattern = re.compile(rf"^\.subckt\s+{re.escape(top)}\s+.+$", re.IGNORECASE | re.MULTILINE)
        if pattern.search(netlist) is None:
            raise ValueError("PEX netlist is missing the expected top-level subcircuit")
        return pattern.sub(f".subckt {top} {' '.join(pins)}", netlist, count=1)

    @staticmethod
    def _drc_failure(output: str) -> str:
        rules_match = DRC_RULES_PATTERN.search(output)
        count_match = DRC_COUNT_PATTERN.search(output)
        if rules_match:
            raw_rules = re.findall(r"['\"]([^'\"]+)['\"]", rules_match.group(1))
            rules = sorted(r for r in raw_rules if not is_ignored_drc_rule(r))
            count = (
                count_match.group(1)
                if count_match and len(rules) == len(raw_rules)
                else str(len(rules))
            )
            return f"DRC failed with {count} violation(s): {', '.join(rules)}"
        return f"DRC failed: {output[-2_048:]}"

    @staticmethod
    def _extract_subckt_pins(netlist: str, expected_top: str | None = None) -> list[str]:
        matches = SUBCKT_DECL_PATTERN.findall(netlist)
        if not matches:
            return []
        if expected_top:
            for name, pin_text in matches:
                if name.lower() == expected_top.lower():
                    return pin_text.split()
        return matches[-1][1].split()

    @classmethod
    def _infer_top_name(cls, reference_text: str, expected_top: str | None = None) -> str | None:
        if expected_top:
            return expected_top
        matches = SUBCKT_DECL_PATTERN.findall(reference_text)
        return matches[-1][0] if matches else None

    @classmethod
    def _lvs_failure(
        cls,
        extracted: str,
        reference: Path,
        expected_pins: list[str],
        expected_top: str | None = None,
        lvs_output: str = "",
    ) -> str:
        reference_text = reference.read_text(encoding="utf-8", errors="replace")
        top_name = cls._infer_top_name(reference_text, expected_top)
        extracted_pins = cls._extract_subckt_pins(extracted, top_name)
        extracted_lower = {pin.lower() for pin in extracted_pins}
        missing_pins = [pin for pin in expected_pins if pin.lower() not in extracted_lower]
        if missing_pins:
            return f"LVS mismatch; missing top-level pins: {', '.join(missing_pins)}"

        report = cls._build_lvs_report(
            extracted,
            reference,
            expected_pins,
            expected_top=top_name,
            lvs_output=lvs_output,
        )
        if report.get("property_errors"):
            first_prop = report["property_errors"][0]
            return (
                f"LVS mismatch; {first_prop['device']} parameter {first_prop['property']} "
                f"is {first_prop['layout']} in layout vs {first_prop['reference']} in reference"
            )

        submitted_devices = cls._mos_dimensions(extracted)
        required_devices = cls._mos_dimensions(reference_text)
        has_device_mismatch = any(
            row["mismatch"] and "number of nets" not in row["layout"].lower()
            for row in report.get("summary_rows", [])
        )
        if submitted_devices != required_devices and (not lvs_output or has_device_mismatch):
            submitted = cls._format_mos_dimensions(submitted_devices)
            required = cls._format_mos_dimensions(required_devices)
            return f"LVS mismatch; extracted MOS dimensions: {submitted}; required: {required}"

        if report.get("net_mismatches"):
            nets = []
            for item in report["net_mismatches"]:
                for net_label in (item["layout_net"], item["reference_net"]):
                    cleaned = net_label.removeprefix("Net:").strip()
                    if cleaned and not cleaned.startswith("(") and cleaned not in nets:
                        nets.append(cleaned)
            if nets:
                return f"LVS mismatch; connectivity mismatch on net(s): {', '.join(nets[:6])}"

        if report.get("pin_mismatches"):
            bad_pins = [
                row["reference_pin"] or row["layout_pin"]
                for row in report["pin_mismatches"]
                if row["mismatch"]
            ]
            if bad_pins:
                return f"LVS mismatch; pin connection mismatch on: {', '.join(bad_pins[:6])}"

        return "LVS mismatch; extracted connectivity does not match the reference inverter"

    @classmethod
    def _build_lvs_report(
        cls,
        extracted: str,
        reference: Path,
        expected_pins: list[str],
        expected_top: str | None = None,
        lvs_output: str = "",
    ) -> dict[str, Any]:
        reference_text = reference.read_text(encoding="utf-8", errors="replace")
        top_name = cls._infer_top_name(reference_text, expected_top)
        extracted_pins = cls._extract_subckt_pins(extracted, top_name)
        extracted_lower = {pin.lower() for pin in extracted_pins}
        expected_lower = {pin.lower() for pin in expected_pins}
        missing_pins = [pin for pin in expected_pins if pin.lower() not in extracted_lower]
        extra_pins = [pin for pin in extracted_pins if pin.lower() not in expected_lower]

        submitted_devices = cls._mos_dimensions(extracted)
        required_devices = cls._mos_dimensions(reference_text)

        parsed = cls._parse_netgen_report(lvs_output, top_name) if lvs_output else {}
        return {
            "expected_pins": expected_pins,
            "extracted_pins": extracted_pins,
            "missing_pins": missing_pins,
            "extra_pins": extra_pins,
            "extracted_devices": cls._format_mos_dimensions(submitted_devices),
            "reference_devices": cls._format_mos_dimensions(required_devices),
            "summary_rows": parsed.get("summary_rows", []),
            "property_errors": parsed.get("property_errors", []),
            "pin_mismatches": parsed.get("pin_mismatches", []),
            "net_mismatches": parsed.get("net_mismatches", []),
            "final_result": parsed.get("final_result", ""),
        }

    @staticmethod
    def _parse_netgen_report(lvs_output: str, top_name: str | None = None) -> dict[str, Any]:
        lines = lvs_output.splitlines()
        summary_rows: list[dict[str, Any]] = []
        property_errors: list[dict[str, str]] = []
        pin_mismatches: list[dict[str, Any]] = []
        net_mismatches: list[dict[str, Any]] = []
        final_result = ""

        def matches_top_header(header_line: str) -> bool:
            if "|" not in header_line or "Circuit 1:" not in header_line:
                return False
            if not top_name:
                return True
            left, right = header_line.split("|", 1)
            c1 = left.split("Circuit 1:", 1)[-1].strip()
            c2 = right.split("Circuit 2:", 1)[-1].strip()
            return c1.lower() == top_name.lower() or c2.lower() == top_name.lower()

        i = 0
        current_prop_device = ""
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if stripped.startswith("Final result:"):
                final_result = stripped.removeprefix("Final result:").strip()

            prop_header = PROPERTY_HEADER_PATTERN.match(stripped)
            if prop_header:
                current_prop_device = f"{prop_header.group(1)} vs {prop_header.group(2)}"
                i += 1
                continue

            prop_line = PROPERTY_LINE_PATTERN.match(line)
            if prop_line and current_prop_device:
                prop_name, c1_val, c2_val, tail = prop_line.groups()
                property_errors.append(
                    {
                        "device": current_prop_device,
                        "property": prop_name.upper(),
                        "layout": _format_si_length(c1_val),
                        "reference": _format_si_length(c2_val),
                        "detail": tail.strip(" ()"),
                    }
                )
                i += 1
                continue

            if stripped == "Subcircuit summary:" and i + 1 < len(lines):
                if matches_top_header(lines[i + 1]):
                    summary_rows = []
                    i += 3  # skip header and dashed separator
                    while i < len(lines) and not lines[i].strip().startswith("---"):
                        row_line = lines[i]
                        if "|" in row_line:
                            left, right = row_line.split("|", 1)
                            mismatch = (
                                "**Mismatch**" in row_line or "(no matching" in row_line.lower()
                            )
                            summary_rows.append(
                                {
                                    "layout": left.replace("**Mismatch**", "").strip(),
                                    "reference": right.replace("**Mismatch**", "").strip(),
                                    "mismatch": mismatch,
                                }
                            )
                        i += 1
                    continue

            if stripped == "Subcircuit pins:" and i + 1 < len(lines):
                if matches_top_header(lines[i + 1]):
                    pin_mismatches = []
                    i += 3  # skip header and dashed separator
                    while i < len(lines) and not lines[i].strip().startswith("---"):
                        row_line = lines[i]
                        if "|" in row_line:
                            left, right = row_line.split("|", 1)
                            l_pin = left.replace("**Mismatch**", "").strip()
                            r_pin = right.replace("**Mismatch**", "").strip()
                            mismatch = (
                                "**Mismatch**" in row_line
                                or "(no " in row_line.lower()
                                or l_pin.lower() != r_pin.lower()
                            )
                            pin_mismatches.append(
                                {
                                    "layout_pin": l_pin,
                                    "reference_pin": r_pin,
                                    "mismatch": mismatch,
                                }
                            )
                        i += 1
                    continue

            if stripped.startswith("NET mismatches:") and i + 1 < len(lines):
                if matches_top_header(lines[i + 1]):
                    net_mismatches = []
                    i += 2
                    current_net: dict[str, Any] | None = None
                    while i < len(lines):
                        row_line = lines[i]
                        row_stripped = row_line.strip()
                        if (
                            row_stripped.startswith("DEVICE mismatches:")
                            or row_stripped.startswith("Netlists ")
                            or row_stripped.startswith("Subcircuit pins:")
                            or row_stripped.startswith("Final result:")
                        ):
                            break
                        if row_stripped.startswith("---") or not row_stripped:
                            current_net = None
                            i += 1
                            continue
                        parts = COLUMN_SPLIT_PATTERN.split(row_line, maxsplit=1)
                        if len(parts) == 2:
                            left, right = parts
                            l_clean = _format_mos_terminals(left.strip())
                            r_clean = _format_mos_terminals(right.strip())
                            net_prefixes = ("Net:", "(no matching net)")
                            if l_clean.startswith(net_prefixes) or r_clean.startswith(net_prefixes):
                                current_net = {
                                    "layout_net": l_clean or "-",
                                    "reference_net": r_clean or "-",
                                    "layout_connections": [],
                                    "reference_connections": [],
                                }
                                net_mismatches.append(current_net)
                            elif current_net is not None:
                                if l_clean:
                                    current_net["layout_connections"].append(l_clean)
                                if r_clean:
                                    current_net["reference_connections"].append(r_clean)
                        i += 1
                    continue

            i += 1

        return {
            "summary_rows": summary_rows,
            "property_errors": property_errors,
            "pin_mismatches": pin_mismatches,
            "net_mismatches": net_mismatches[:20],
            "final_result": final_result,
        }

    @staticmethod
    def _mos_dimensions(netlist: str) -> list[tuple[str, str, str]]:
        devices = []
        for model, parameter_text in MOS_PATTERN.findall(netlist):
            parameters = {
                name.upper(): value for name, value in MOS_PARAMETER_PATTERN.findall(parameter_text)
            }
            devices.append((model.lower(), parameters.get("W", "?"), parameters.get("L", "?")))
        return sorted(devices)

    @staticmethod
    def _format_mos_dimensions(devices: list[tuple[str, str, str]]) -> str:
        return (
            ", ".join(
                f"{model.removeprefix('sg13_lv_').removeprefix('sg13_hv_')} W={width} L={length}"
                for model, width, length in devices
            )
            or "none"
        )
