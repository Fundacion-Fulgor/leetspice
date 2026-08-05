"""Profile-specific structural judge for the built-in circuit library."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .result import JudgeResult, Measurement
from .validator import validate_netlist

NUMBER = re.compile(r"^(?P<value>\d+(?:\.\d*)?|\.\d+)(?P<suffix>meg|[tgkmunpf])?$", re.I)
SCALE = {
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
}

PROFILE_LIMITS = {
    "device": (1, 4, 1, 0),
    "source_follower": (2, 8, 1, 0),
    "amplifier": (2, 12, 1, 0),
    "amplifier_bias": (2, 16, 1, 0),
    "mirror": (2, 16, 2, 0),
    "reference_current": (3, 24, 1, 1),
    "reference_voltage": (3, 32, 1, 1),
    "differential": (5, 20, 2, 0),
    "ota": (5, 24, 2, 2),
    "complex_opamp": (7, 48, 3, 2),
    "cmfb": (3, 24, 1, 0),
    "sampler": (5, 20, 1, 1),
    "oscillator": (6, 36, 3, 3),
    "oscillator_control": (7, 48, 4, 3),
    "charge_pump": (3, 16, 1, 1),
}


def _number(value: str) -> float:
    match = NUMBER.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid numeric value {value!r}")
    return (
        float(match.group("value"))
        * SCALE[match.group("suffix").casefold() if match.group("suffix") else None]
    )


class ProfileJudge:
    """Enforce circuit-family structure and score implementation compactness."""

    def judge(
        self,
        netlist: str,
        expected_subckt: str,
        expected_pins: Sequence[str],
        config: dict[str, object],
    ) -> JudgeResult:
        try:
            validate_netlist(netlist, expected_subckt, expected_pins)
            family = str(config.get("family", ""))
            limits = PROFILE_LIMITS[family]
            measurements, score = self._measure(netlist, expected_pins, limits)
        except (KeyError, TypeError, ValueError) as error:
            return JudgeResult(False, 0.0, message=str(error))
        accepted = all(item.passed for item in measurements)
        message = (
            "Circuit profile passed structural and sizing checks"
            if accepted
            else "Circuit profile failed one or more structural or sizing checks"
        )
        return JudgeResult(accepted, score if accepted else 0.0, measurements, message)

    @staticmethod
    def _measure(
        netlist: str, expected_pins: Sequence[str], limits: tuple[int, int, int, int]
    ) -> tuple[tuple[Measurement, ...], float]:
        minimum_devices, maximum_devices, minimum_nmos, minimum_pmos = limits
        devices = []
        node_groups: list[set[str]] = []
        nmos = pmos = 0
        total_width_um = total_gate_area_um2 = 0.0
        for raw_line in netlist.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("*", ".", "+")):
                continue
            tokens = line.split()
            devices.append(tokens[0])
            node_slice = tokens[1:5] if tokens[0][0].casefold() in {"m", "x"} else tokens[1:3]
            nodes = {node.casefold() for node in node_slice}
            overlaps = [group for group in node_groups if group & nodes]
            for group in overlaps:
                nodes |= group
                node_groups.remove(group)
            node_groups.append(nodes)
            if tokens[0][0].casefold() not in {"m", "x"} or len(tokens) < 6:
                continue
            model = tokens[5].casefold()
            nmos += model == "sg13_lv_nmos"
            pmos += model == "sg13_lv_pmos"
            parameters = {
                name.casefold(): value
                for token in tokens[6:]
                if "=" in token
                for name, value in [token.split("=", 1)]
            }
            width = _number(parameters.get("w", "1u")) * 1e6
            length = _number(parameters.get("l", "0.13u")) * 1e6
            gates = _number(parameters.get("ng", parameters.get("nf", "1")))
            multiplier = _number(parameters.get("m", "1")) * gates
            total_width_um += width * multiplier
            total_gate_area_um2 += width * length * multiplier

        count = len(devices)
        circuit_nodes = set().union(*node_groups) if node_groups else set()
        all_pins_used = {pin.casefold() for pin in expected_pins} <= circuit_nodes
        one_network = len(node_groups) == 1
        measurements = (
            Measurement(
                "device_count",
                float(count),
                "devices",
                minimum_devices <= count <= maximum_devices,
            ),
            Measurement("nmos_count", float(nmos), "devices", nmos >= minimum_nmos),
            Measurement("pmos_count", float(pmos), "devices", pmos >= minimum_pmos),
            Measurement("public_pins_used", float(all_pins_used), "boolean", all_pins_used),
            Measurement("connected_network", float(one_network), "boolean", one_network),
            Measurement(
                "total_mos_width",
                round(total_width_um, 6),
                "um",
                0.1 <= total_width_um <= 2_000.0,
            ),
            Measurement(
                "total_gate_area",
                round(total_gate_area_um2, 6),
                "um^2",
                0.01 <= total_gate_area_um2 <= 2_000.0,
            ),
        )
        score = round(10_000.0 / (10.0 + count + total_gate_area_um2), 6)
        return measurements, score
