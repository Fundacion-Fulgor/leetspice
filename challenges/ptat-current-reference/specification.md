# PTAT Current Reference

Design and optimize an IHP SG13G2 ptat current reference across server-owned checks.

Submit exactly one `.subckt ptat_current_reference vdd vss out` using SG13G2 low-voltage MOS devices, resistors, and capacitors. A private, server-owned ngspice testbench loads the pinned SG13G2 compact models and measures the documented public-terminal operating point. The checked-in private reference passes these limits in the production image. The score is calculated from the measured electrical quantities after all hard limits pass.
