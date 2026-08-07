# MOS DC Characteristics Lab

## Objective

Learn what a MOS operating point contains. Submit exactly one SG13G2 low-voltage NMOS in `.subckt mos_operating_point d g s b`. Change its width and length, then observe how geometry changes drain current, transconductance, output conductance, and intrinsic gain.

## Public test envelope

The body and source are tied to 0 V. The nominal operating point is `VGS = 0.60 V`, `VDS = 0.90 V`, TT, 27 C. The server estimates `gm = dID/dVGS` and `gds = dID/dVDS` with 1 mV terminal finite differences. It reports `ID`, `gm`, `gds`, `ro = 1/gds`, `gm/ID`, and intrinsic gain `gm/gds`.

The lab accepts currents from 100 nA to 5 mA and requires positive `gm` and `gds`; these are validity checks, not an optimization target. This lab is unranked. Its purpose is to compare operating points before attempting the ranked MOS Efficiency Sizing challenge.

Only one `X` device using `sg13_lv_nmos` is allowed. The exact test deck is private, but all applied biases and reported equations are public.
