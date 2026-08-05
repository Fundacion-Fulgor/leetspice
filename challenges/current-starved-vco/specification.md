# Current-Starved VCO

Design and optimize an IHP SG13G2 current-starved vco across server-owned checks.

Submit exactly one `.subckt current_starved_vco vctrl out vdd vss` using SG13G2 low-voltage MOS devices, resistors, and capacitors. Server-owned profile checks enforce circuit-family structure, device mix, and sizing bounds. Fewer devices and smaller total gate width improve score after all hard limits pass.
