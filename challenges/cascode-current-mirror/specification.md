# Cascode Current Mirror

Design and optimize an IHP SG13G2 cascode current mirror across server-owned checks.

Submit exactly one `.subckt cascode_current_mirror iref out vss` using SG13G2 low-voltage MOS devices, resistors, and capacitors. Server-owned profile checks enforce circuit-family structure, device mix, and sizing bounds. Fewer devices and smaller total gate width improve score after all hard limits pass.
