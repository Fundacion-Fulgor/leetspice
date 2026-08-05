# Common-Mode Feedback

Design and optimize an IHP SG13G2 common-mode feedback across server-owned checks.

Submit exactly one `.subckt common_mode_feedback outp outn vcm ctrl vdd vss` using SG13G2 low-voltage MOS devices, resistors, and capacitors. Server-owned profile checks enforce circuit-family structure, device mix, and sizing bounds. Fewer devices and smaller total gate width improve score after all hard limits pass.
