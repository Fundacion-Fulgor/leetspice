# MOS gm/ID Characterization Lab

## Objective

Use `gm/ID` as a way to describe inversion level, not as a drain-current contest. Submit one `sg13_lv_nmos` device in `.subckt mos_gmid d g s b`. The server compares the same geometry at `VGS = 0.45 V`, `0.60 V`, and `0.80 V`, with `VDS = 0.90 V`, TT, 27 C.

At each bias, the server estimates `gm` from a 1 mV gate-voltage finite difference and reports `ID` and `gm/ID`. You should observe that `gm/ID` is generally larger at low current, while current density and speed increase toward stronger inversion. Maximum `gm/ID` alone is therefore not a complete design objective.

Valid results require positive drain current and `gm/ID` between 0.1 and 40 1/V. This lab is unranked. The follow-on MOS Efficiency Sizing challenge adds current and intrinsic-gain constraints so that geometry choices create a real tradeoff.

Only one `X` device using `sg13_lv_nmos` is allowed. An interactive curve explorer remains planned future work.
