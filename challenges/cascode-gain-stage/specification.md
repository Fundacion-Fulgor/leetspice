# Cascode Gain Stage

Design and optimize an IHP SG13G2 cascode gain stage across server-owned checks.

Submit exactly one `.subckt cascode_gain_stage in out bias vdd vss` using SG13G2 low-voltage MOS devices, resistors, and capacitors. A private, server-owned ngspice testbench loads the pinned SG13G2 compact models and measures the documented public-terminal operating point. The checked-in private reference passes these limits in the production image. The score is calculated from measured quantities after all hard limits pass.
