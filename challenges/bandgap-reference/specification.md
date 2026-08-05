# Bandgap Reference

Design and optimize an IHP SG13G2 bandgap reference across server-owned checks.

Submit exactly one `.subckt bandgap_reference vdd vss vref` using SG13G2 low-voltage MOS devices, resistors, and capacitors. Server-owned profile checks enforce circuit-family structure, device mix, and sizing bounds. Fewer devices and smaller total gate width improve score after all hard limits pass.
