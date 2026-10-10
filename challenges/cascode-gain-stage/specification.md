# Cascode Gain Stage

## Objective

Design `.subckt cascode_gain_stage in out bias vdd vss` with a common-source input device and a common-gate cascode device. The server applies 1.2 V supply, 0.50 V input bias with AC magnitude 1, 0.75 V cascode bias, and 100 fF output load. It evaluates TT, SS, and FF at -40 C, 27 C, and 125 C.

## Hard limits

- output bias: 0.35 V to 1.00 V;
- low-frequency gain magnitude: at least 2.2 V/V;
- `-3 dB` bandwidth: at least 75 MHz;
- supply current: 0.1 uA to 100 uA.

After feasibility, the score maximizes worst gain and bandwidth normalized to 3 V/V and 80 MHz and minimizes worst current normalized to 40 uA. The resistor load limits available gain; this challenge focuses on keeping both stacked transistors correctly biased while retaining output headroom and high-frequency isolation across PVT.
