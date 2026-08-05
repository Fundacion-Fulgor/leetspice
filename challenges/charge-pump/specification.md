# Matched Charge Pump

Design and optimize an IHP SG13G2 matched charge pump across server-owned checks.

Submit exactly one `.subckt charge_pump up dn out vdd vss` using SG13G2 low-voltage MOS devices, resistors, and capacitors. Server-owned profile checks enforce circuit-family structure, device mix, and sizing bounds. Fewer devices and smaller total gate width improve score after all hard limits pass.
