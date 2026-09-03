"""KLayout-backed IHP SG13G2 GDS verification."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

import yaml

from .characterization import CharacterizationJudge
from .magic import MagicRunner
from .netgen import NetgenRunner
from .result import JudgeResult, Measurement

MAX_GDS_BYTES = 8 * 1024 * 1024
DRC_RULES_PATTERN = re.compile(r"Violated rules are\s*:\s*\{([^}]*)\}")
DRC_COUNT_PATTERN = re.compile(r"Number of DRC errors for maximum rule set:\s*(\d+)", re.IGNORECASE)
SUBCKT_PATTERN = re.compile(r"^\.subckt\s+\S+\s+(.+)$", re.IGNORECASE | re.MULTILINE)
MOS_PATTERN = re.compile(
    r"^M\S+\s+(?:\S+\s+){4}(sg13_lv_[np]mos)\s+(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
MOS_PARAMETER_PATTERN = re.compile(r"\b([WL])\s*=\s*([^\s]+)", re.IGNORECASE)


class LayoutJudge:
    """Run server-owned SG13G2 DRC and LVS decks against a bounded GDSII payload."""

    def __init__(
        self,
        challenges_path: str | Path | None = None,
        pdk_root: str | Path | None = None,
        timeout: float = 300.0,
    ) -> None:
        self.challenges_path = Path(
            challenges_path or os.getenv("CHALLENGES_PATH", "/app/challenges")
        )
        self.pdk_root = Path(pdk_root or os.getenv("PDK_ROOT", "/opt/IHP-Open-PDK"))
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

                def rem_time():
                    t = deadline - time.monotonic()
                    if t <= 0: raise subprocess.TimeoutExpired("layout", self.timeout)
                    return t

                try:
                    with ProcessPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(self._inspect, gds, expected_top)
                        area, cell_count = future.result(timeout=rem_time())
                except Exception:
                    return JudgeResult(False, 0.0, message="GDSII parsing failed: malformed layout or crash")

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
                    )
                
                magic.timeout = rem_time()
                extracted = magic.extract_lvs(gds, expected_top, work)
                try:
                    NetgenRunner(pdk_root=self.pdk_root, timeout=rem_time()).lvs(
                        extracted, reference, expected_top, work
                    )
                except ValueError:
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
                            extracted.read_text(encoding="utf-8", errors="replace"),
                            reference,
                            expected_pins,
                        ),
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
            env={**os.environ, "HOME": "/tmp", "KLAYOUT_PATH": ""},
        )
        if completed.returncode != 0:
            if stage == "DRC":
                raise ValueError(self._drc_failure(completed.stdout))
            output = completed.stdout[-8_192:]
            raise ValueError(f"{stage} failed: {output}")

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
            rules = sorted(re.findall(r"['\"]([^'\"]+)['\"]", rules_match.group(1)))
            count = count_match.group(1) if count_match else str(len(rules))
            return f"DRC failed with {count} violation(s): {', '.join(rules)}"
        return f"DRC failed: {output[-2_048:]}"

    @classmethod
    def _lvs_failure(cls, extracted: str, reference: Path, expected_pins: list[str]) -> str:
        subckt_match = SUBCKT_PATTERN.search(extracted)
        extracted_pins = subckt_match.group(1).split() if subckt_match else []
        missing_pins = [pin for pin in expected_pins if pin not in extracted_pins]
        if missing_pins:
            return f"LVS mismatch; missing top-level pins: {', '.join(missing_pins)}"

        submitted_devices = cls._mos_dimensions(extracted)
        required_devices = cls._mos_dimensions(
            reference.read_text(encoding="utf-8", errors="replace")
        )
        if submitted_devices != required_devices:
            submitted = cls._format_mos_dimensions(submitted_devices)
            required = cls._format_mos_dimensions(required_devices)
            return f"LVS mismatch; extracted MOS dimensions: {submitted}; required: {required}"

        return "LVS mismatch; extracted connectivity does not match the reference inverter"

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
                f"{model.removeprefix('sg13_lv_')} W={width} L={length}"
                for model, width, length in devices
            )
            or "none"
        )
