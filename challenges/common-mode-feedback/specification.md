# Common-Mode Feedback

Design and optimize an IHP SG13G2 common-mode feedback across server-owned checks.

Submit exactly one `.subckt common_mode_feedback outp outn vcm ctrl vdd vss` using SG13G2 low-voltage MOS devices, resistors, and capacitors. A private, server-owned ngspice testbench loads the pinned SG13G2 compact models and measures the documented public-terminal operating point. The checked-in private reference passes these limits in the production image. The score is calculated from measured quantities after all hard limits pass.
