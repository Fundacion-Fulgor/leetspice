"""CACE-backed SG13G2 characterization backend."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

import yaml

from .result import JudgeResult, Measurement
from .validator import validate_netlist

PDK_COMMIT = "8d3ee38d4540ed675d3ac08332a51f75258fc3a7"


class CaceJudge:
    """Run a validated inverter through server-owned CACE characterization."""

    def __init__(
        self,
        challenge_root: str | Path | None = None,
        executable: str = "cace",
        timeout: float = 120.0,
    ) -> None:
        self.challenge_root = Path(
            challenge_root
            or os.getenv("LEETSPICE_CACE_CHALLENGE", "/app/challenges/demo-cmos-inverter")
        )
        self.executable = executable
        self.timeout = timeout

    def judge(
        self, netlist: str, expected_subckt: str, expected_pins: Sequence[str]
    ) -> JudgeResult:
        try:
            validate_netlist(netlist, expected_subckt, expected_pins)
        except ValueError as error:
            return JudgeResult(False, 0.0, message=str(error))

        required = (self.challenge_root / "cace", self.challenge_root / "xschem")
        if not all(path.is_dir() for path in required):
            return JudgeResult(False, 0.0, message="CACE challenge package is incomplete")

        try:
            with tempfile.TemporaryDirectory(prefix="leetspice-cace-") as directory:
                workspace = Path(directory) / "challenge"
                shutil.copytree(self.challenge_root, workspace)
                (workspace / "submission.spice").write_text(netlist, encoding="utf-8")
                schematic_path = workspace / "xschem" / "inverter.sch"
                schematic_path.write_text(self._schematic(netlist), encoding="utf-8")
                run_path = workspace / "runs"
                environment = os.environ.copy()
                environment.setdefault("PDK", "ihp-sg13g2")
                completed = subprocess.run(
                    [
                        self.executable,
                        str(workspace / "cace" / "inverter.yaml"),
                        "--source",
                        "schematic",
                        "--run-path",
                        str(run_path),
                        "--no-plot",
                        "--no-progress-bar",
                        "--sequential",
                    ],
                    cwd=workspace,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )
                output = completed.stdout[-16_384:]
                if completed.returncode != 0:
                    return JudgeResult(False, 0.0, message=f"CACE failed: {output}")
                measurements = self._collect(run_path)
        except subprocess.TimeoutExpired:
            return JudgeResult(False, 0.0, message=f"CACE timed out after {self.timeout:g}s")
        except OSError as error:
            return JudgeResult(False, 0.0, message=f"CACE could not start: {error}")
        except (ValueError, yaml.YAMLError) as error:
            return JudgeResult(False, 0.0, message=f"invalid CACE result: {error}")

        if not measurements:
            return JudgeResult(False, 0.0, message="CACE produced no measurements")
        accepted = all(measurement.passed for measurement in measurements)
        delays = [
            measurement.value
            for measurement in measurements
            if measurement.name.startswith(("tphl_", "tplh_"))
        ]
        worst_delay_ps = max(delays)
        score = round(1_000.0 / max(worst_delay_ps, 0.001), 6) if accepted else 0.0
        message = (
            f"SG13G2 CACE verification passed; PDK commit {PDK_COMMIT[:12]}"
            if accepted
            else "SG13G2 CACE verification failed one or more PVT limits"
        )
        return JudgeResult(accepted, score, tuple(measurements), message)

    @staticmethod
    def _schematic(netlist: str) -> str:
        escaped = netlist.replace("\\", "\\\\").replace('"', '\\"')
        return (
            "v {xschem version=3.4.4 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            'C {devices/code_shown.sym} 0 0 0 0 {name=DUT only_toplevel=true value="\n'
            f"{escaped.rstrip()}\n"
            '"}\n'
        )

    @staticmethod
    def _collect(run_path: Path) -> list[Measurement]:
        measurements: list[Measurement] = []
        result_files = sorted(run_path.glob("**/timing_*.data"))
        for result_file in result_files:
            conditions_path = result_file.parent / "conditions.yaml"
            if not conditions_path.is_file():
                raise ValueError(f"missing conditions for {result_file.name}")
            conditions = yaml.safe_load(conditions_path.read_text(encoding="utf-8"))
            values = result_file.read_text(encoding="utf-8").split()
            if len(values) != 7:
                raise ValueError(f"expected seven values in {result_file.name}")
            tphl, tplh, rise, fall, current, low, high = map(float, values)
            corner = str(conditions["corner"])
            temperature = int(float(conditions["temperature"]))
            suffix = f"{corner}_{temperature}C"
            quantities = (
                ("tphl", tphl * 1e12, "ps", 500.0),
                ("tplh", tplh * 1e12, "ps", 500.0),
                ("rise_time", rise * 1e12, "ps", 500.0),
                ("fall_time", fall * 1e12, "ps", 500.0),
                ("average_current", abs(current) * 1e6, "uA", 100.0),
                ("logic_low", low, "V", 0.12),
                ("logic_high", high, "V", None),
            )
            for name, value, unit, maximum in quantities:
                passed = value >= 1.08 if name == "logic_high" else value >= 0
                if maximum is not None:
                    passed = passed and value <= maximum
                measurements.append(Measurement(f"{name}_{suffix}", round(value, 6), unit, passed))
        return measurements
