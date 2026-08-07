# Basic Current Mirror

## Objective

Design `.subckt basic_current_mirror iref out vss` to copy a 50 uA current forced into `iref`. The server tests output voltages of 0.20 V, 0.60 V, and 1.00 V at TT and 27 C. It also estimates output resistance at 1.00 V from a 1 mV finite difference.

## Hard limits

- output current must remain between 40 uA and 60 uA at all three voltages;
- worst relative current error from 50 uA must be at most 20%;
- output resistance at 1.00 V must be at least 50 kohm.

After feasibility, the equally weighted geometric-mean score minimizes worst current error normalized to 5% and maximizes output resistance normalized to 200 kohm. Longer channels improve output resistance but require more width and voltage headroom for the same current. The exact sampled deck is private; the current, voltage points, equations, limits, and score are public.
