# SG13G2 inverter layout

Submit one raw GDSII file with exactly one top-level cell named `inverter`.

The layout must implement the supplied Xschem inverter and expose labeled `in`, `out`, `vdd`, and `vss` pins. The judge runs Magic full DRC and Netgen LVS against the server-owned reference. Missing or mismatched pins fail LVS.

After DRC and LVS, Magic produces a coupled-capacitance PEX netlist and ngspice measures nominal inverter delay and current. Score combines electrical merit and compactness as `electrical score × 1000 / bounding-box area in um^2`. This educational open-PDK check is not equivalent to private foundry sign-off.
