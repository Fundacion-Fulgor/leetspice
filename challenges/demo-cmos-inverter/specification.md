# CMOS Inverter: First Switch

## Goal

Submit a CMOS inverter as exactly one `.subckt inverter in out vdd vss`. The PoC validator permits MOSFETs, resistors, and capacitors, but no testbench directives, sources, includes, models, or control scripts.

## Suggested dimensions

| Parameter | Suggested range | Starter value |
| --- | ---: | ---: |
| `wn` | 0.22 µm to 20 µm | 1 µm |
| `wp` | 0.22 µm to 40 µm | 2 µm |

## Public PoC checks

- A PMOS must connect `out` to `vdd` and be controlled by `in`.
- An NMOS must connect `out` to `vss` and be controlled by `in`.
- The deterministic mock score estimates propagation delay, power, and device area.

The mock backend validates the product workflow only. It does not run SPICE and its score is not physical evidence. The optional experimental ngspice backend uses server-owned educational level-1 models, not a foundry PDK. No hidden process-corner checks are implied.

Local development defaults to the mock runner. A mock pass demonstrates the submission workflow only and is not evidence that ngspice evaluated the circuit.
