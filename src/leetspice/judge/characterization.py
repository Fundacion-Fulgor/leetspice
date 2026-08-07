"""Manifest-driven direct-ngspice characterization backend."""

from __future__ import annotations

import itertools
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path
from string import Template

from .definition import CharacterizationDefinition, TestDefinition, load_definition
from .result import JudgeResult, Measurement
from .validator import validate_netlist

RESULT_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\s+([^\s]+)$")
SAFE_TEXT = re.compile(r"^[A-Za-z0-9_.+-]+$")


class CharacterizationJudge:
    def __init__(
        self,
        challenges_path: str | Path | None = None,
        executable: str = "ngspice",
        pdk_root: str | Path | None = None,
    ) -> None:
        self.challenges_path = Path(
            challenges_path or os.getenv("CHALLENGES_PATH", "/app/challenges")
        )
        self.executable = executable
        self.pdk_root = Path(pdk_root or os.getenv("PDK_ROOT", "/opt/IHP-Open-PDK"))

    def judge(
        self,
        netlist: str,
        expected_subckt: str,
        expected_pins: list[str],
        fixture_path: str,
        config: dict[str, object],
    ) -> JudgeResult:
        try:
            validate_netlist(netlist, expected_subckt, expected_pins)
            challenge_root = (self.challenges_path / fixture_path).resolve()
            challenge_root.relative_to(self.challenges_path.resolve())
            definition_path = config.get("definition")
            if not isinstance(definition_path, str):
                raise ValueError("ngspice challenge is missing judge_config.definition")
            definition = load_definition(challenge_root, definition_path)
            measurements = self._run_definition(definition, netlist)
            accepted = all(item.passed for item in measurements)
            score = self._score(definition, measurements) if accepted else 0.0
        except subprocess.TimeoutExpired as error:
            return JudgeResult(False, 0.0, message=f"ngspice timed out after {error.timeout:g}s")
        except (OSError, ValueError) as error:
            return JudgeResult(False, 0.0, message=str(error))
        message = (
            "SG13G2 ngspice characterization passed"
            if accepted
            else "One or more simulation limits failed"
        )
        return JudgeResult(accepted, score, tuple(measurements), message)

    def _run_definition(
        self, definition: CharacterizationDefinition, netlist: str
    ) -> list[Measurement]:
        collected: list[Measurement] = []
        with tempfile.TemporaryDirectory(prefix="leetspice-ngspice-") as directory:
            root = Path(directory)
            for test in definition.tests:
                for index, conditions in enumerate(self._conditions(test)):
                    run = root / f"{test.name}-{index}"
                    run.mkdir()
                    (run / "submission.spice").write_text(netlist, encoding="utf-8")
                    context = {name: self._safe_value(value) for name, value in conditions.items()}
                    context["pdk_root"] = str(self.pdk_root)
                    template = Template(test.template.read_text(encoding="utf-8"))
                    try:
                        deck = template.substitute(context)
                    except (KeyError, ValueError) as error:
                        raise ValueError(
                            f"invalid template {test.template.name}: {error}"
                        ) from error
                    deck_path = run / "testbench.cir"
                    deck_path.write_text(deck, encoding="utf-8")
                    completed = subprocess.run(
                        [self.executable, "-b", "-o", "ngspice.log", deck_path.name],
                        cwd=run,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=test.timeout,
                        check=False,
                    )
                    if completed.returncode != 0:
                        raise ValueError(f"ngspice failed: {completed.stdout[-4096:]}")
                    values = self._parse_results(run / test.result_file, test)
                    suffix = self._suffix(conditions)
                    for spec in test.measurements:
                        value = values[spec.name]
                        passed = (spec.minimum is None or value >= spec.minimum) and (
                            spec.maximum is None or value <= spec.maximum
                        )
                        collected.append(
                            Measurement(
                                f"{spec.name}_{suffix}" if suffix else spec.name,
                                value,
                                spec.unit,
                                passed,
                            )
                        )
        return collected

    @staticmethod
    def _conditions(test: TestDefinition) -> list[dict[str, str | float | int]]:
        names = tuple(test.sweep)
        if not names:
            return [{}]
        return [
            dict(zip(names, values, strict=True))
            for values in itertools.product(*(test.sweep[n] for n in names))
        ]

    @staticmethod
    def _safe_value(value: str | float | int) -> str:
        rendered = str(value)
        if not SAFE_TEXT.fullmatch(rendered):
            raise ValueError(f"unsafe condition value: {rendered}")
        return rendered

    @staticmethod
    def _parse_results(path: Path, test: TestDefinition) -> dict[str, float]:
        if not path.is_file() or path.stat().st_size > 64 * 1024:
            raise ValueError(f"test {test.name} did not produce a bounded result file")
        expected = {item.name for item in test.measurements}
        values: dict[str, float] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            match = RESULT_PATTERN.fullmatch(line.strip())
            if match is None or match.group(1) not in expected or match.group(1) in values:
                raise ValueError(f"test {test.name} produced invalid measurement output")
            try:
                value = float(match.group(2))
            except ValueError as error:
                raise ValueError(f"test {test.name} produced a non-numeric measurement") from error
            if not math.isfinite(value):
                raise ValueError(f"test {test.name} produced a non-finite measurement")
            values[match.group(1)] = value
        if values.keys() != expected:
            raise ValueError(f"test {test.name} omitted an expected measurement")
        return values

    @staticmethod
    def _suffix(conditions: dict[str, str | float | int]) -> str:
        parts = []
        for name, value in conditions.items():
            rendered = f"{value}C" if name == "temperature" else str(value)
            parts.append(rendered if name in {"corner", "temperature"} else f"{name}_{rendered}")
        return "_".join(parts)

    @staticmethod
    def _score(definition: CharacterizationDefinition, measurements: list[Measurement]) -> float:
        score = definition.score
        primary = [
            item.value
            for item in measurements
            if item.name == score.measurement or item.name.startswith(f"{score.measurement}_")
        ]
        if not primary:
            raise ValueError("score measurement is missing")
        if score.strategy == "inverse_worst":
            value = score.scale / max(max(primary), 1e-30)
        elif score.strategy == "maximize_minimum":
            value = score.scale * min(primary)
        else:
            denominator = [
                item.value
                for item in measurements
                if item.name == score.denominator or item.name.startswith(f"{score.denominator}_")
            ]
            if not denominator:
                raise ValueError("score denominator is missing")
            value = score.scale * min(primary) / max(max(denominator), 1e-30)
        if not math.isfinite(value):
            raise ValueError("score is non-finite")
        return round(value, 6)
