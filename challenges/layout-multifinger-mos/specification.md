# Multifinger MOS Layout

Submit one raw GDSII file with exactly one top cell named `multifinger_mos` and labeled pins `d`, `g`, `s`, `b`. The judge runs the pinned IHP maximal DRC deck without density, then strict LVS against a private reference. Score is `1000 / bounding-box area in um^2`. For matching-oriented challenges, DRC/LVS verifies legality and connectivity; geometric common-centroid quality is a documented design objective, not yet a scored proof.
