"""Validation for the deliberately small SPICE submission language."""

from __future__ import annotations

import re
from collections.abc import Sequence

MAX_NETLIST_BYTES = 64 * 1024
MAX_PHYSICAL_LINES = 1_000
MAX_DEVICES = 256
MAX_TOKENS_PER_LINE = 64

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.$-]*$")
_NODE = re.compile(r"^[A-Za-z0-9_.$-]+$")
_NUMBER = re.compile(
    r"^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?(?:meg|mil|[tgkmunpf])?$",
    re.IGNORECASE,
)
_MOS_PARAMETERS = {"w", "l", "m", "nf", "ad", "as", "pd", "ps", "nrd", "nrs"}
_SG13G2_MOS_MODELS = {"sg13_lv_nmos", "sg13_lv_pmos"}


def _logical_lines(netlist: str) -> list[tuple[int, str]]:
    physical = netlist.splitlines()
    if len(physical) > MAX_PHYSICAL_LINES:
        raise ValueError(f"netlist exceeds {MAX_PHYSICAL_LINES} lines")

    logical: list[tuple[int, str]] = []
    for number, raw_line in enumerate(physical, 1):
        if any(ord(character) < 32 and character != "\t" for character in raw_line):
            raise ValueError(f"line {number}: control characters are not allowed")
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        # Semicolon comments are supported, but only outside parameter expressions.
        stripped = stripped.split(";", 1)[0].rstrip()
        if not stripped:
            continue
        if stripped.startswith("+"):
            continuation = stripped[1:].strip()
            if not logical or not continuation:
                raise ValueError(f"line {number}: invalid continuation")
            start, previous = logical[-1]
            logical[-1] = (start, f"{previous} {continuation}")
        else:
            logical.append((number, stripped))
    return logical


def _validate_tokens(tokens: list[str], line_number: int) -> None:
    if len(tokens) > MAX_TOKENS_PER_LINE:
        raise ValueError(f"line {line_number}: too many tokens")
    for token in tokens:
        if len(token) > 128 or any(character in token for character in "'\"\\`"):
            raise ValueError(f"line {line_number}: unsafe token {token!r}")


def _validate_device(tokens: list[str], line_number: int) -> None:
    kind = tokens[0][0].upper()
    if not _IDENTIFIER.fullmatch(tokens[0]):
        raise ValueError(f"line {line_number}: invalid element name")
    required = 6 if kind in {"M", "X"} else 4
    if len(tokens) < required:
        raise ValueError(f"line {line_number}: incomplete {kind} element")
    node_tokens = tokens[1:5] if kind in {"M", "X"} else tokens[1:3]
    if any(not _NODE.fullmatch(node) for node in node_tokens):
        raise ValueError(f"line {line_number}: invalid node name")

    if kind in {"R", "C"}:
        if len(tokens) != 4 or not _NUMBER.fullmatch(tokens[3]):
            raise ValueError(f"line {line_number}: {kind} requires one numeric value")
        return

    if not _IDENTIFIER.fullmatch(tokens[5]):
        raise ValueError(f"line {line_number}: invalid MOS model name")
    if kind == "X" and tokens[5].casefold() not in _SG13G2_MOS_MODELS:
        raise ValueError(f"line {line_number}: unsupported SG13G2 device {tokens[5]!r}")
    seen_parameters: set[str] = set()
    for parameter in tokens[6:]:
        if parameter.count("=") != 1:
            raise ValueError(f"line {line_number}: invalid MOS parameter")
        name, value = parameter.split("=", 1)
        folded_name = name.casefold()
        if (
            folded_name not in _MOS_PARAMETERS
            or folded_name in seen_parameters
            or not _NUMBER.fullmatch(value)
        ):
            raise ValueError(f"line {line_number}: invalid MOS parameter {parameter!r}")
        seen_parameters.add(folded_name)


def validate_netlist(
    netlist: str,
    expected_subckt: str,
    expected_pins: Sequence[str],
) -> None:
    """Validate a submission, returning ``None`` or raising ``ValueError``.

    The accepted language is one subcircuit containing primitive MOSFETs,
    resistors, capacitors, and the SG13G2 low-voltage MOS subcircuits. Model
    definitions and every SPICE analysis directive remain server-owned.
    """

    if not isinstance(netlist, str):
        raise ValueError("netlist must be text")
    if len(netlist.encode("utf-8")) > MAX_NETLIST_BYTES:
        raise ValueError(f"netlist exceeds {MAX_NETLIST_BYTES} bytes")
    if not isinstance(expected_subckt, str) or not _IDENTIFIER.fullmatch(expected_subckt):
        raise ValueError("invalid expected subcircuit name")
    try:
        pins = tuple(expected_pins)
    except TypeError as error:
        raise ValueError("expected pins must be a sequence") from error
    if any(not isinstance(pin, str) or not _IDENTIFIER.fullmatch(pin) for pin in pins):
        raise ValueError("invalid expected pin name")
    if not pins or len(set(pin.casefold() for pin in pins)) != len(pins):
        raise ValueError("expected pins must be non-empty and unique")

    lines = _logical_lines(netlist)
    if not lines:
        raise ValueError("netlist is empty")

    in_subckt = False
    ended = False
    subckt_count = 0
    ends_count = 0
    device_count = 0
    device_names: set[str] = set()

    for line_number, line in lines:
        tokens = line.split()
        _validate_tokens(tokens, line_number)
        first = tokens[0]
        lowered = first.casefold()

        if lowered == ".subckt":
            subckt_count += 1
            if in_subckt or ended or subckt_count != 1:
                raise ValueError(f"line {line_number}: exactly one .subckt is required")
            if len(tokens) != len(pins) + 2:
                raise ValueError(f"line {line_number}: subcircuit pins do not match")
            if tokens[1].casefold() != expected_subckt.casefold():
                raise ValueError(f"line {line_number}: unexpected subcircuit name")
            if tuple(token.casefold() for token in tokens[2:]) != tuple(
                pin.casefold() for pin in pins
            ):
                raise ValueError(f"line {line_number}: subcircuit pins must match in order")
            in_subckt = True
            continue

        if lowered == ".ends":
            ends_count += 1
            if not in_subckt or ended or ends_count != 1:
                raise ValueError(f"line {line_number}: unmatched .ends")
            if len(tokens) > 2:
                raise ValueError(f"line {line_number}: invalid .ends")
            if len(tokens) == 2 and tokens[1].casefold() != expected_subckt.casefold():
                raise ValueError(f"line {line_number}: .ends name does not match")
            in_subckt = False
            ended = True
            continue

        if first.startswith("."):
            raise ValueError(f"line {line_number}: directive {first!r} is not allowed")
        if not in_subckt:
            raise ValueError(f"line {line_number}: content outside the subcircuit")

        kind = first[0].upper()
        if kind not in {"M", "X", "R", "C"}:
            raise ValueError(f"line {line_number}: element type {first[0]!r} is not allowed")
        _validate_device(tokens, line_number)
        folded_name = first.casefold()
        if folded_name in device_names:
            raise ValueError(f"line {line_number}: duplicate element name {first!r}")
        device_names.add(folded_name)
        device_count += 1
        if device_count > MAX_DEVICES:
            raise ValueError(f"netlist exceeds {MAX_DEVICES} devices")

    if subckt_count != 1 or ends_count != 1 or in_subckt or not ended:
        raise ValueError("exactly one complete .subckt/.ends pair is required")
    if device_count == 0:
        raise ValueError("subcircuit must contain at least one device")
