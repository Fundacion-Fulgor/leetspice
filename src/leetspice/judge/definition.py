"""Strict definitions for server-owned ngspice characterization."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SCORE_STRATEGIES = {"inverse_worst", "maximize_minimum", "efficiency"}


@dataclass(frozen=True, slots=True)
class MeasurementDefinition:
    name: str
    unit: str
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True, slots=True)
class TestDefinition:
    name: str
    template: Path
    result_file: str
    timeout: float
    sweep: dict[str, tuple[str | float | int, ...]]
    measurements: tuple[MeasurementDefinition, ...]


@dataclass(frozen=True, slots=True)
class ScoreDefinition:
    strategy: str
    measurement: str
    denominator: str | None = None
    scale: float = 1.0


@dataclass(frozen=True, slots=True)
class CharacterizationDefinition:
    tests: tuple[TestDefinition, ...]
    score: ScoreDefinition


def resolve_private_file(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError("judge file path must be relative")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError("judge file path escapes the challenge package") from error
    if not candidate.is_file():
        raise ValueError(f"judge file is missing: {relative}")
    return candidate


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{label} must be finite{' and positive' if positive else ''}")
    return result


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.replace("_", "").isalnum() or not value[0].isalpha():
        raise ValueError(f"{label} must be an identifier")
    return value


def load_definition(root: Path, relative: str) -> CharacterizationDefinition:
    source = resolve_private_file(root, relative)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError(f"invalid characterization definition: {error}") from error
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("characterization definition version must be 1")

    conditions = data.get("conditions", {})
    if not isinstance(conditions, dict):
        raise ValueError("conditions must be an object")
    parsed_conditions: dict[str, tuple[str | float | int, ...]] = {}
    for raw_name, raw_values in conditions.items():
        name = _identifier(raw_name, "condition name")
        if not isinstance(raw_values, list) or not raw_values:
            raise ValueError(f"condition {name} must be a non-empty list")
        if not all(
            isinstance(item, (str, int, float)) and not isinstance(item, bool)
            for item in raw_values
        ):
            raise ValueError(f"condition {name} contains an invalid value")
        parsed_conditions[name] = tuple(raw_values)

    raw_tests = data.get("tests")
    if not isinstance(raw_tests, list) or not raw_tests:
        raise ValueError("tests must be a non-empty list")
    tests = []
    all_measurements: set[str] = set()
    for raw_test in raw_tests:
        if not isinstance(raw_test, dict):
            raise ValueError("each test must be an object")
        name = _identifier(raw_test.get("name"), "test name")
        template = resolve_private_file(root, raw_test.get("template", ""))
        result_file = raw_test.get("result_file", "results.data")
        if not isinstance(result_file, str) or Path(result_file).name != result_file:
            raise ValueError(f"test {name} has an invalid result_file")
        timeout = _number(raw_test.get("timeout", 30), f"test {name} timeout", positive=True)
        raw_sweep = raw_test.get("sweep", conditions)
        if not isinstance(raw_sweep, dict):
            raise ValueError(f"test {name} sweep must be an object")
        sweep: dict[str, tuple[str | float | int, ...]] = {}
        for condition_name, selected in raw_sweep.items():
            condition_name = _identifier(condition_name, "sweep condition")
            if condition_name not in parsed_conditions:
                raise ValueError(f"test {name} references unknown condition {condition_name}")
            values = parsed_conditions[condition_name] if selected == "all" else selected
            if not isinstance(values, (list, tuple)) or not values:
                raise ValueError(f"test {name} sweep {condition_name} must be non-empty")
            if any(value not in parsed_conditions[condition_name] for value in values):
                raise ValueError(f"test {name} sweep {condition_name} contains an undeclared value")
            sweep[condition_name] = tuple(values)

        raw_measurements = raw_test.get("measurements")
        if not isinstance(raw_measurements, list) or not raw_measurements:
            raise ValueError(f"test {name} measurements must be a non-empty list")
        measurements = []
        for raw_measurement in raw_measurements:
            if not isinstance(raw_measurement, dict):
                raise ValueError(f"test {name} measurement must be an object")
            measurement_name = _identifier(raw_measurement.get("name"), "measurement name")
            unit = raw_measurement.get("unit", "")
            if not isinstance(unit, str) or len(unit) > 30:
                raise ValueError(f"measurement {measurement_name} has an invalid unit")
            minimum = raw_measurement.get("minimum")
            maximum = raw_measurement.get("maximum")
            minimum = None if minimum is None else _number(minimum, f"{measurement_name} minimum")
            maximum = None if maximum is None else _number(maximum, f"{measurement_name} maximum")
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"measurement {measurement_name} has inverted limits")
            measurements.append(MeasurementDefinition(measurement_name, unit, minimum, maximum))
            all_measurements.add(measurement_name)
        tests.append(
            TestDefinition(name, template, result_file, timeout, sweep, tuple(measurements))
        )

    raw_score = data.get("score")
    if not isinstance(raw_score, dict) or raw_score.get("strategy") not in SCORE_STRATEGIES:
        raise ValueError(f"score strategy must be one of {sorted(SCORE_STRATEGIES)}")
    measurement = _identifier(raw_score.get("measurement"), "score measurement")
    denominator = raw_score.get("denominator")
    if denominator is not None:
        denominator = _identifier(denominator, "score denominator")
    if measurement not in all_measurements or (denominator and denominator not in all_measurements):
        raise ValueError("score references an undeclared measurement")
    scale = _number(raw_score.get("scale", 1), "score scale", positive=True)
    return CharacterizationDefinition(
        tuple(tests), ScoreDefinition(raw_score["strategy"], measurement, denominator, scale)
    )
