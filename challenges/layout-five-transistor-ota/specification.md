# Five-Transistor OTA Layout

Submit one raw GDSII file with exactly one top cell named `ota5` and labeled pins `inp`, `inn`, `out`, `bias`, `vdd`, `vss`. The judge runs the pinned IHP maximal DRC deck without density, then strict LVS against a private reference. Score is `1000 / bounding-box area in um^2`. For matching-oriented challenges, DRC/LVS verifies legality and connectivity; geometric common-centroid quality is a documented design objective, not yet a scored proof.
