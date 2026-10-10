# PTAT Current Reference

## Objective

Design `.subckt ptat_current_reference vdd vss out` using SG13G2 low-voltage MOS devices, resistors, capacitors, and the four-terminal `npn13G2` HBT. The HBT pin order is collector, base, emitter, buried/substrate node; `Nx` is the only allowed HBT parameter.

The server applies 1.2 V supply, holds `out` at 0.6 V, and measures output and supply current at -40 C, 27 C, and 125 C using the TT MOS and typical HBT models.

## Hard limits

- cold output current: 2 uA to 8 uA;
- nominal output current: 10 uA to 20 uA;
- hot output current: 30 uA to 55 uA;
- supply current: no more than 50 uA cold, 80 uA nominal, and 200 uA hot.

These separate windows enforce positive temperature behavior: a flat or CTAT source cannot pass. The score targets 15 uA nominal output with 5 uA normalization and minimizes hot supply current normalized to 150 uA. A useful architecture develops `Delta VBE` from unequal HBT emitter multiplicities and converts it to current through a resistor.
