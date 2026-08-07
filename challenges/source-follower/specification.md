# Challenge 1: Source Follower

## Objective
Design and optimize an IHP SG13G2 N-channel source follower to buffer a high-impedance source. The design must maximize AC gain at low frequencies and high input impedance while minimizing static power consumption and output offset voltage.

## Interface
The submission must define exactly one subcircuit with the following signature:
```spice
.subckt source_follower in out vdd vss
```

## Public PVT and Load Envelope
- **Supply Voltage (VDD to VSS):** Nominal 1.2 V (VSS = 0 V)
- **Temperature:** Nominal 27°C, evaluated across Corners (`tt`, `ss`, `ff`) and Temperatures (`-40°C`, `27°C`, `125°C`)
- **Input Common-Mode range:** Bias point at 0.8 V DC
- **Output Load:** $C_L = 1\text{ pF}$ to ground

## Analyses
1. **DC Operating Point (OP):** Verification of quiescent output level ($V_{out}$) and DC bias current ($I_{supply}$).
2. **AC Small-Signal Analysis:** Swept from 1 Hz to 10 GHz to evaluate low-frequency gain ($A_v$) and -3dB bandwidth ($f_{-3\text{dB}}$).

## Hard Limits
- **DC Offset Voltage:** $0.20\text{ V} \le V_{out} \le 0.50\text{ V}$ at $V_{in} = 0.8\text{ V}$
- **Supply Current:** $I_{supply} \le 1.0\text{ mA}$
- **Low-Frequency AC Gain:** $A_v \ge 0.72\text{ V/V}$
- **Bandwidth:** $f_{-3\text{dB}} \ge 80\text{ MHz}$

## Score Formula & Tradeoffs
The challenge evaluates the tradeoff between gain ($A_v$, maximize), bandwidth ($f_{-3\text{dB}}$, maximize), and supply current ($I_{supply}$, minimize).
The composite score is calculated using the weighted geometric mean of three normalized objectives:
- **Gain ($A_v$):** Maximized, aggregated as minimum across PVT. Normalization: 0.85. Weight: 2.0.
- **Bandwidth ($f_{-3\text{dB}}$):** Maximized, aggregated as minimum across PVT. Normalization: 100 MHz. Weight: 1.0.
- **Supply Current ($I_{supply}$):** Minimized, aggregated as maximum across PVT. Normalization: 100 µA. Weight: 1.5.

A larger transistor increases $g_m$ and bandwidth but increases gate capacitance (loading the source) and requires more supply current to maintain headroom.
