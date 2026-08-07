# Supply-Independent Bias

Design and optimize an IHP SG13G2 supply-independent bias across server-owned checks.

Submit exactly one `.subckt supply_independent_bias vdd vss out` using SG13G2 low-voltage MOS devices, resistors, and capacitors. A private, server-owned ngspice testbench loads the pinned SG13G2 compact models and measures the documented public-terminal operating point. The checked-in private reference passes these limits in the production image. The score is calculated from the measured electrical quantities after all hard limits pass.
