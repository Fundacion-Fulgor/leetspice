# MOS Efficiency Sizing

## Objective

Choose the width and length of exactly one SG13G2 low-voltage NMOS. At `VGS = 0.60 V` and `VDS = 0.90 V`, TT, 27 C, deliver between 45 uA and 55 uA while balancing transconductance efficiency and intrinsic gain.

Submit `.subckt mos_efficiency d g s b` containing exactly one `X` device using `sg13_lv_nmos`. Resistors, capacitors, PMOS devices, and parallel transistors are forbidden for this introductory sizing exercise.

## Measurements

The server estimates `gm = dID/dVGS` and `gds = dID/dVDS` with 1 mV finite differences. Hard limits are `45 uA <= ID <= 55 uA`, `gm/ID >= 5 1/V`, `gm/gds >= 10`, and positive `gds`.

After all limits pass, the score is the equally weighted geometric mean of:

- worst-case `gm/ID`, normalized to 10 1/V and maximized;
- worst-case intrinsic gain `gm/gds`, normalized to 20 V/V and maximized.

The bias envelope and formulas are public; only the exact deck implementation is private. Width primarily sets current, while channel length changes output resistance, current density, and the width needed to recover the target current.
