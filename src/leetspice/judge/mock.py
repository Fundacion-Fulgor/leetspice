"""Deterministic, simulator-free judge used by the proof of concept."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .result import JudgeResult, Measurement
from .validator import _logical_lines, validate_netlist

_NUMBER = re.compile(
    r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)(meg|mil|[tgkmunpf])?",
    re.IGNORECASE,
)
_SCALE = {
    None: 1.0,
    "t": 1e12,
    "g": 1e9,
    "meg": 1e6,
    "k": 1e3,
    "m": 1e-3,
    "u": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
    "mil": 25.4e-6,
}


def _spice_number(value: str, default: float = 0.0) -> float:
    match = _NUMBER.match(value)
    if not match:
        return default
    return float(match.group(1)) * _SCALE[match.group(2).casefold() if match.group(2) else None]


def _parameters(tokens: list[str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for token in tokens:
        if "=" in token:
            name, value = token.split("=", 1)
            result[name.casefold()] = _spice_number(value)
    return result


class MockJudge:
    """Score an inverter topology using stable estimates, not simulation."""

    def judge(
        self, netlist: str, expected_subckt: str, expected_pins: Sequence[str]
    ) -> JudgeResult:
        try:
            validate_netlist(netlist, expected_subckt, expected_pins)
        except ValueError as error:
            return JudgeResult(False, 0.0, message=str(error))

        mosfets: list[tuple[list[str], dict[str, float]]] = []
        resistance = 0.0
        capacitance = 0.0
        for _, line in _logical_lines(netlist):
            if line.startswith("."):
                continue
            tokens = line.split()
            if tokens[0][0].upper() in {"M", "X"}:
                mosfets.append((tokens, _parameters(tokens[6:])))
            elif tokens[0][0].upper() == "R":
                resistance += _spice_number(tokens[3])
            elif tokens[0][0].upper() == "C":
                capacitance += _spice_number(tokens[3])

        pins = [pin.casefold() for pin in expected_pins]
        if len(pins) < 4 or len(mosfets) < 2:
            return JudgeResult(
                False,
                0.0,
                message="an inverter requires at least four pins and two MOSFETs",
            )
        input_node, output_node, high_node, low_node = pins[:4]

        pull_up = False
        pull_down = False
        total_width = 0.0
        total_length = 0.0
        for tokens, parameters in mosfets:
            drain, gate, source, bulk, model = (token.casefold() for token in tokens[1:6])
            width = parameters.get("w", 1e-6)
            length = parameters.get("l", 0.18e-6)
            total_width += max(width, 0.0)
            total_length += max(length, 0.0)
            is_pmos = model.startswith("p") or "pmos" in model
            is_nmos = model.startswith("n") or "nmos" in model
            pull_up |= (
                is_pmos
                and drain == output_node
                and gate == input_node
                and source == high_node
                and bulk == high_node
            )
            pull_down |= (
                is_nmos
                and drain == output_node
                and gate == input_node
                and source == low_node
                and bulk == low_node
            )

        topology_ok = pull_up and pull_down
        effective_width_um = max(total_width * 1e6, 0.01)
        area_um2 = total_width * total_length * 1e12
        load_ff = capacitance * 1e15
        delay_ps = 12.0 + 35.0 / effective_width_um + 0.6 * load_ff + resistance * 1e-3
        power_uw = 0.4 + 0.25 * effective_width_um + 0.01 * load_ff
        complexity_penalty = max(0, len(mosfets) - 2) * 3.0
        score = max(
            0.0,
            min(
                100.0,
                100.0
                - delay_ps * 0.45
                - power_uw * 0.8
                - area_um2 * 0.15
                - complexity_penalty,
            ),
        )
        measurements = (
            Measurement("propagation_delay", round(delay_ps, 4), "ps", topology_ok),
            Measurement("estimated_power", round(power_uw, 4), "uW", topology_ok),
            Measurement("device_area", round(area_um2, 4), "um^2", topology_ok),
        )
        if not topology_ok:
            return JudgeResult(False, 0.0, measurements, "MOSFETs do not form a CMOS inverter")
        return JudgeResult(
            True,
            round(score, 4),
            measurements,
            "accepted by deterministic mock judge",
        )

    __call__ = judge
