# Cascode Current Mirror

## Objective

Design `.subckt cascode_current_mirror iref out vss` to copy a server-forced 50 uA reference while shielding the output branch from output-voltage changes. The server holds `out` at 0.50 V, 0.75 V, and 1.00 V, then estimates output resistance at 1.00 V with a 1 mV finite difference. It evaluates TT, SS, and FF at -40 C, 27 C, and 125 C.

## Hard limits

- output current: 47 uA to 53 uA at all three voltages;
- worst current error from 50 uA: no more than 5%;
- output resistance: at least 1 Mohm.

The output-resistance requirement is approximately ten times the qualified basic-mirror baseline and is the defining lesson. After feasibility, the score minimizes worst current error normalized to 5% and maximizes worst output resistance normalized to 1.3 Mohm using an equally weighted geometric mean. Cascoding improves current stability but costs compliance voltage and requires valid internal gate biasing.
