"""Constrained ngspice process boundary."""

from __future__ import annotations

import re
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from .result import JudgeResult, Measurement
from .validator import validate_netlist

TestbenchBuilder = Callable[[str, str, Sequence[str]], str]
_MEASUREMENT = re.compile(
    r"^\s*(delay|power)\s*=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)",
    re.IGNORECASE | re.MULTILINE,
)


def _default_testbench(netlist: str, subckt: str, pins: Sequence[str]) -> str:
    if len(pins) != 4:
        raise ValueError("default ngspice testbench requires input, output, VDD, and VSS pins")
    nodes = " ".join(pins)
    return f"""LeetSpice server-owned inverter testbench
{netlist.rstrip()}
.model NMOS NMOS (LEVEL=1 VTO=0.45 KP=120u)
.model PMOS PMOS (LEVEL=1 VTO=-0.45 KP=50u)
VDD {pins[2]} {pins[3]} 1.8
VIN {pins[0]} {pins[3]} PULSE(0 1.8 1n 10p 10p 5n 10n)
CLOAD {pins[1]} {pins[3]} 10f
XDUT {nodes} {subckt}
.tran 2p 20n
.measure tran delay TRIG v({pins[0]}) VAL=0.9 RISE=1 TARG v({pins[1]}) VAL=0.9 FALL=1
.measure tran power AVG par('abs(v({pins[2]})*i(VDD))') FROM=2n TO=20n
.end
"""


def _sanitize_output(output: str, limit: int = 8_192) -> str:
    cleaned = "".join(
        character if character in "\n\t" or ord(character) >= 32 else "?"
        for character in output
    )
    return cleaned[-limit:]


class NgspiceJudge:
    """Run only a validated submission embedded in a server-owned testbench."""

    def __init__(
        self,
        executable: str = "ngspice",
        timeout: float = 10.0,
        testbench_builder: TestbenchBuilder | None = None,
    ) -> None:
        self.executable = executable
        self.timeout = timeout
        self._build_testbench = testbench_builder or _default_testbench

    def judge(
        self, netlist: str, expected_subckt: str, expected_pins: Sequence[str]
    ) -> JudgeResult:
        try:
            validate_netlist(netlist, expected_subckt, expected_pins)
            deck = self._build_testbench(netlist, expected_subckt, expected_pins)
        except ValueError as error:
            return JudgeResult(False, 0.0, message=str(error))
        if deck == netlist:
            return JudgeResult(
                False,
                0.0,
                message="testbench builder returned the user deck directly",
            )

        try:
            with tempfile.TemporaryDirectory(prefix="leetspice-") as directory:
                testbench = Path(directory) / "testbench.cir"
                output_file = Path(directory) / "ngspice.log"
                testbench.write_text(deck, encoding="utf-8")
                completed = subprocess.run(
                    [self.executable, "-b", "-o", str(output_file), str(testbench)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                    cwd=directory,
                )
                output = completed.stdout
                if output_file.exists():
                    output += "\n" + output_file.read_text(encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return JudgeResult(False, 0.0, message=f"ngspice timed out after {self.timeout:g}s")
        except OSError as error:
            return JudgeResult(False, 0.0, message=f"ngspice could not start: {error}")

        output = _sanitize_output(output)
        if completed.returncode != 0:
            return JudgeResult(False, 0.0, message=f"ngspice failed: {output}")
        values = {name.casefold(): float(value) for name, value in _MEASUREMENT.findall(output)}
        if "delay" not in values or "power" not in values:
            return JudgeResult(False, 0.0, message=f"ngspice produced no measurements: {output}")

        delay_ps = values["delay"] * 1e12
        power_uw = abs(values["power"]) * 1e6
        accepted = delay_ps >= 0.0 and delay_ps <= 1_000.0 and power_uw <= 1_000.0
        score = max(0.0, min(100.0, 100.0 - delay_ps * 0.08 - power_uw * 0.02)) if accepted else 0.0
        measurements = (
            Measurement("propagation_delay", round(delay_ps, 4), "ps", delay_ps <= 1_000.0),
            Measurement("average_power", round(power_uw, 4), "uW", power_uw <= 1_000.0),
        )
        message = "accepted" if accepted else "limits exceeded"
        return JudgeResult(accepted, round(score, 4), measurements, message)

    __call__ = judge
