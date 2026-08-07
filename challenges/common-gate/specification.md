# Common-Gate Amplifier

## Objective

Design `.subckt common_gate in out bias vdd vss` as a non-inverting common-gate stage. The server applies 1.2 V supply, fixes `bias` at 0.75 V, sinks 40 uA from `in`, adds 100 fF at `out`, and injects a 1 A small-signal AC current at `in`. It evaluates TT, SS, and FF at -40 C, 27 C, and 125 C.

The AC fixture obtains input resistance from `|V(in)| / 1 A`, transimpedance from `|V(out)| / 1 A`, and voltage gain from their ratio. Bandwidth is the first frequency where transimpedance falls by 3 dB.

## Hard limits

- output bias: 0.35 V to 0.45 V;
- source/input bias: 0 V to 0.36 V, preserving drain-source headroom;
- input resistance: 1 ohm to 15 kohm;
- low-frequency voltage gain: at least 1.4 V/V;
- bandwidth: at least 60 MHz;
- supply current: 0.1 uA to 100 uA.

## Score

After feasibility, the score is the geometric mean of worst-case gain and bandwidth, normalized to 2 V/V and 70 MHz and maximized, and worst-case input resistance, normalized to 10 kohm and minimized. More transconductance reduces input resistance, while device geometry and load resistance trade gain against bandwidth and headroom.
