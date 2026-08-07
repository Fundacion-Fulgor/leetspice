# Five-Transistor OTA Layout

Submit one raw GDSII file with exactly one top cell named `ota5` and labeled pins `inp`, `inn`, `out`, `bias`, `vdd`, `vss`. The judge runs Magic full DRC, Netgen LVS against a private reference, Magic coupled-capacitance PEX, and a private ngspice post-layout operating-point test. Score combines electrical merit and compactness. For matching-oriented challenges, DRC/LVS verifies legality and connectivity; geometric common-centroid quality is a documented design objective, not yet a scored proof.
