"""KLayout-backed IHP SG13G2 GDS verification."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

import yaml

from .result import JudgeResult, Measurement

MAX_GDS_BYTES = 8 * 1024 * 1024
LVS_SUCCESS = "Congratulations! Netlists match."
DRC_RULES_PATTERN = re.compile(r"Violated rules are\s*:\s*\{([^}]*)\}")
DRC_COUNT_PATTERN = re.compile(
    r"Number of DRC errors for maximum rule set:\s*(\d+)", re.IGNORECASE
)
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
        klayout: str = "klayout",
        timeout: float = 300.0,
    ) -> None:
        self.challenges_path = Path(
            challenges_path or os.getenv("CHALLENGES_PATH", "/app/challenges")
        )
        self.pdk_root = Path(pdk_root or os.getenv("PDK_ROOT", "/opt/IHP-Open-PDK"))
        self.klayout = klayout
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
            return JudgeResult(False, 0.0, message="invalid layout reference path")
        if not reference.is_file():
            return JudgeResult(False, 0.0, message="layout reference netlist is missing")

        tech = self.pdk_root / "ihp-sg13g2" / "libs.tech" / "klayout" / "tech"
        drc_runner = tech / "drc" / "run_drc.py"
        lvs_runner = tech / "lvs" / "run_lvs.py"
        inspect_macro = Path("/app/scripts/inspect-layout.rb")
        if not all(path.is_file() for path in (drc_runner, lvs_runner, inspect_macro)):
            return JudgeResult(False, 0.0, message="layout verification toolchain is incomplete")

        try:
            with tempfile.TemporaryDirectory(prefix="leetspice-layout-") as directory:
                work = Path(directory)
                gds = work / "submission.gds"
                inspection = work / "inspection.yaml"
                gds.write_bytes(payload)
                self._run(
                    [
                        self.klayout,
                        "-b",
                        "-r",
                        str(inspect_macro),
                        "-rd",
                        f"input={gds}",
                        "-rd",
                        f"expected={expected_top}",
                        "-rd",
                        f"output={inspection}",
                    ],
                    "GDS inspection",
                )
                metadata = yaml.safe_load(inspection.read_text(encoding="utf-8"))
                area = float(metadata["area_um2"])
                cell_count = int(metadata["cell_count"])

                drc_directory = work / "drc"
                drc_command = [
                    "python",
                    str(drc_runner),
                    f"--path={gds}",
                    f"--topcell={expected_top}",
                    "--run_mode=deep",
                    f"--run_dir={drc_directory}",
                    "--mp=1",
                    "--no_density",
                ]
                self._run(drc_command, "DRC")
                if not any(drc_directory.glob("*.lyrdb")):
                    raise ValueError("DRC did not produce a result database")

                lvs_directory = work / "lvs"
                self._run(
                    [
                        "python",
                        str(lvs_runner),
                        f"--layout={gds}",
                        f"--netlist={reference}",
                        f"--topcell={expected_top}",
                        "--run_mode=deep",
                        f"--run_dir={lvs_directory}",
                    ],
                    "LVS",
                )
                reports = list(lvs_directory.glob("*.lvsdb"))
                extracted_netlists = list(lvs_directory.glob("*_extracted.cir"))
                logs = list(lvs_directory.glob("*.log"))
                if not reports or not extracted_netlists or not logs:
                    raise ValueError("LVS did not produce all required results")
                lvs_output = "\n".join(
                    path.read_text(encoding="utf-8", errors="replace") for path in logs
                )
                if LVS_SUCCESS not in lvs_output:
                    extracted_netlist = extracted_netlists[0].read_text(
                        encoding="utf-8", errors="replace"
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
                        self._lvs_failure(extracted_netlist, reference, expected_pins),
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
        )
        score = round(1_000.0 / max(area, 0.001), 6)
        return JudgeResult(True, score, measurements, "SG13G2 DRC and strict LVS passed")

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
    def _drc_failure(output: str) -> str:
        rules_match = DRC_RULES_PATTERN.search(output)
        count_match = DRC_COUNT_PATTERN.search(output)
        if rules_match:
            rules = sorted(re.findall(r"['\"]([^'\"]+)['\"]", rules_match.group(1)))
            count = count_match.group(1) if count_match else str(len(rules))
            return f"DRC failed with {count} violation(s): {', '.join(rules)}"
        return f"DRC failed: {output[-2_048:]}"

    @classmethod
    def _lvs_failure(
        cls, extracted: str, reference: Path, expected_pins: list[str]
    ) -> str:
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
        return ", ".join(
            f"{model.removeprefix('sg13_lv_')} W={width} L={length}"
            for model, width, length in devices
        ) or "none"
