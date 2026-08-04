# CMOS Inverter: First Switch

**Target process context:** IHP SG13G2 130 nm BiCMOS Open Source PDK.

## Goal

Submit a CMOS inverter as exactly one `.subckt inverter in out vdd vss`. The PoC validator permits MOSFETs, resistors, and capacitors, but no testbench directives, sources, includes, models, or control scripts.

The judge uses CACE 2.11.0 and ngspice with the SG13G2 low-voltage compact
models pinned at PDK commit `8d3ee38d4540ed675d3ac08332a51f75258fc3a7`.
It evaluates `tt`, `ff`, and `ss` process corners at -40, 27, and 125 °C with
a 1.2 V supply and 10 fF output load.

## Suggested dimensions

| Parameter | Suggested range | Starter value |
| --- | ---: | ---: |
| `wn` | 0.13 µm to 20 µm | 1 µm |
| `wp` | 0.13 µm to 40 µm | 2 µm |

## Public PoC checks

- `tPHL`, `tPLH`, 10-90% rise time, and 90-10% fall time must each be at most 500 ps.
- Average supply current must be at most 100 µA.
- Settled logic low must be at most 0.12 V and logic high at least 1.08 V.
- Every limit must pass at all nine process/temperature combinations.

The score is `1000 / worst propagation delay in ps`, so higher is better after
all hard limits pass. This is schematic-level simulation, not post-layout
signoff, mismatch, Monte Carlo, reliability, or manufacturability verification.

Local development defaults to the mock runner. A mock pass demonstrates the submission workflow only and is not evidence that ngspice evaluated the circuit.
