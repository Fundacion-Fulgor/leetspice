# SG13G2 inverter layout

Submit one raw GDSII file with exactly one top-level cell named `inverter`.

The layout must implement the supplied Xschem inverter and expose labeled `in`, `out`, `vdd`, and `vss` pins. The judge runs the IHP SG13G2 KLayout DRC deck in deep mode without whole-chip density checks, followed by strict LVS against the server-owned reference netlist. Missing or mismatched pins fail LVS.

Accepted layouts score `1000 / bounding-box area in um^2`; smaller is better through a higher score. This educational open-PDK check is not equivalent to private foundry sign-off.
