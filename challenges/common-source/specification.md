# Common-Source Amplifier

## Objective

Design `.subckt common_source in out vdd vss` as an inverting voltage amplifier. The server applies 1.2 V supply, biases `in` at 0.50 V, adds a 100 fF load at `out`, and runs DC and AC analyses from 1 Hz to 100 GHz. It evaluates TT, SS, and FF at -40 C, 27 C, and 125 C.

## Hard limits

- output bias: 0.30 V to 0.90 V;
- low-frequency gain magnitude: at least 2.8 V/V;
- `-3 dB` bandwidth: at least 80 MHz;
- supply current: 0.1 uA to 100 uA.

## Score

After every limit passes, the score is the equally weighted geometric mean of worst-case gain and bandwidth, normalized to 3.5 V/V and 100 MHz and maximized, and worst-case current, normalized to 40 uA and minimized. Longer channels can improve intrinsic gain but add capacitance; larger current can improve speed while reducing output headroom. Exact sampled decks remain private, but all biases, loads, conditions, formulas, limits, and normalizations are public.
