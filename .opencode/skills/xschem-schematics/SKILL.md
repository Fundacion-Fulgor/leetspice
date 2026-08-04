---
name: xschem-schematics
description: Xschem .sch/.sym creation, editing, connectivity, and netlisting for IHP SG13G2. Use when creating or modifying Xschem schematics, symbols, MOS wiring, starter design files, or diagnosing undriven/open nets.
---

# Xschem Schematics

Read [XSCHEM_SCHEMATICS.md](XSCHEM_SCHEMATICS.md) before creating or editing an Xschem schematic.

Mandatory workflow:

1. Read the exact installed symbol files and record every pin coordinate.
2. Apply the instance translation, rotation, and mirror to those coordinates.
3. Terminate wires exactly at transformed pin coordinates. Never infer pins from the drawing origin or appearance.
4. Prefer adapting a known-good schematic from the pinned PDK over drawing an equivalent topology from memory.
5. Preserve required instance properties such as `model`, `spiceprefix`, `w`, `l`, `ng`, and `m`.
6. Verify geometry against all gate, drain, source, bulk, and top-level port attachment points.
7. Netlist with an Xschem version compatible with the pinned PDK symbols and inspect the generated device node order.
8. Add a regression test for critical wire endpoints before publishing a downloadable `.sch`.

Do not claim a schematic is verified merely because it opens, looks connected, or contains net labels.
