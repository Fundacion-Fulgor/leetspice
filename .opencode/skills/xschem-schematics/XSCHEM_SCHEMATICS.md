# Xschem Schematic Engineering

This reference captures the failure modes and verification practices learned while creating the LeetSpice IHP SG13G2 inverter-layout starter schematic.

## Core Rule

Xschem connectivity is geometric. A wire is connected to a symbol terminal only when a wire endpoint or segment reaches the terminal's exact transformed coordinate.

Visual proximity is not connectivity. A net label on a nearby wire does not connect it to a terminal. The component placement coordinate is not generally a terminal coordinate.

## Read Symbols First

Never draw wires from memory or by estimating the visible symbol shape. Read the exact `.sym` files installed with the active PDK revision.

For the pinned IHP SG13G2 checkout, the symbols are under:

```text
$PDK_ROOT/ihp-sg13g2/libs.tech/xschem/sg13g2_pr/
```

Relevant files:

```text
sg13_lv_nmos.sym
sg13_lv_pmos.sym
```

The terminal boxes are represented by `B 5` records. For the unrotated low-voltage NMOS symbol, local terminal centers are:

```text
G = (-20,   0)
D = ( 20, -30)
S = ( 20,  30)
B = ( 20,   0)
```

For the unrotated low-voltage PMOS symbol, local terminal centers are:

```text
G = (-20,   0)
S = ( 20, -30)
D = ( 20,  30)
B = ( 20,   0)
```

The PMOS source and drain orientation differs from the NMOS symbol. Do not assume the same vertical pin meaning for both.

For an unrotated instance at `(x, y)`, add `(x, y)` to each local coordinate. For example, an NMOS at `(20, 50)` has:

```text
G = ( 0, 50)
D = (40, 20)
B = (40, 50)
S = (40, 80)
```

A PMOS at `(20, -50)` has:

```text
G = ( 0, -50)
S = (40, -80)
B = (40, -50)
D = (40, -20)
```

Apply rotation and mirror transforms before translation when an instance is not `0 0`. If there is any uncertainty, use a known-good PDK schematic with the same transform rather than deriving it informally.

## Xschem File Records

The records most relevant to connectivity are:

```text
C {symbol/path.sym} x y rotation mirror {properties}
N x1 y1 x2 y2 {lab=net_name}
```

`C` places a symbol. `N` creates a wire segment. A wire must touch the transformed center of the terminal box from the symbol.

The `lab=` property describes the wire's intended net name. It does not rescue a wire that misses the pin.

Top-level port symbols also attach at their transformed terminal coordinate. Read `ipin.sym`, `opin.sym`, and `iopin.sym` when using rotations or mirrors.

## Use PDK-Proven Topology

For SG13G2 standard-cell-style inverters, start from the PDK-maintained schematic:

```text
$PDK_ROOT/ihp-sg13g2/libs.tech/xschem/sg13g2_stdcells/sg13g2_inv_1.sch
```

Adapt only what the challenge requires, such as:

```text
A   -> in
Y   -> out
VDD -> vdd
VSS -> vss
```

Do not redraw an equivalent-looking inverter from scratch when a qualified topology exists. The PDK schematic includes the correct gate, drain, source, and bulk endpoint geometry.

## Required MOS Properties

IHP low-voltage MOS symbols use an `X` SPICE prefix for simulation netlists. Preserve explicit properties on instances:

```text
model=sg13_lv_nmos
spiceprefix=X
l=130.00n
w=740.00n
ng=1
m=1
```

and:

```text
model=sg13_lv_pmos
spiceprefix=X
l=130.00n
w=1.12u
ng=1
m=1
```

Omitting `spiceprefix=X` can produce the wrong element form or inconsistent netlisting across Xschem/PDK versions.

For KLayout LVS reference netlists, the same devices may need `M` primitive syntax rather than the ngspice-facing `X` syntax. Simulation netlists and LVS references are different contracts; qualify each against its tool.

## Correct Inverter Geometry

The known-good challenge topology places:

```text
NMOS at (20,  50), rotation=0, mirror=0
PMOS at (20, -50), rotation=0, mirror=0
```

Critical terminal-touching wire segments include:

```text
N 0 0 0 50 {lab=in}
N 0 -50 0 0 {lab=in}

N 40 0 40 20 {lab=out}
N 40 -20 40 0 {lab=out}

N 40 -100 40 -80 {lab=vdd}
N 40 -50 50 -50 {lab=vdd}

N 40 50 50 50 {lab=vss}
N 40 80 40 100 {lab=vss}
```

These endpoints are not stylistic. They correspond directly to transformed MOS terminals.

The original broken schematic placed MOS devices at `(120, 40)` and `(120, -80)` but stopped input wires at `x=90` even though gates were at `x=100`. Output wires stopped at `x=150` while the right-side terminals were at `x=140`, and supply wires targeted the symbol origin instead of source/body terminals. The schematic looked close but had disconnected terminals.

## Verification Layers

Use multiple checks. No single check is sufficient.

### 1. Geometry Inspection

For every instance:

1. List symbol-local pin centers.
2. Transform them using instance rotation/mirror/translation.
3. Confirm a wire endpoint or segment contains each transformed coordinate.
4. Confirm the intended net label is on that connected wire component.

Check all four MOS terminals, not only gate and drain. Bulk must be explicitly tied to the intended source rail unless the symbol/device contract says otherwise.

### 2. Known-Good Structural Comparison

Compare the schematic against the corresponding PDK schematic. Device coordinates and critical wire endpoints should match unless a deliberate change is documented.

### 3. Xschem Netlisting

Use the configured PDK environment:

```sh
PDK_ROOT=/opt/IHP-Open-PDK
PDK=ihp-sg13g2
xschem -n -q -x -s \
  -o /tmp/netlist \
  -N inverter.spice \
  path/to/inverter.sch
```

Inspect the generated device lines. For the LeetSpice inverter, expected connectivity is logically equivalent to:

```spice
XMN0 out in vss vss sg13_lv_nmos ...
XMP0 out in vdd vdd sg13_lv_pmos ...
```

The exact textual pin order emitted by Xschem follows the symbol's pin ordering. Verify meaning against the symbol and tool, not only string position.

### 4. Hierarchical Netlist Test

A standalone subcircuit schematic can legitimately produce ERC messages such as an undriven output or open top-level input/supply ports. To distinguish expected standalone ERC from broken connectivity, instantiate the cell in a small server-owned testbench that drives `in`, `vdd`, and `vss` and loads `out`, then netlist the hierarchy.

Do not suppress all warnings globally. A missing MOS connection and an intentionally open top-level port are different conditions.

### 5. Regression Test

Add a source-level test for critical endpoint records. This does not replace Xschem, but it prevents accidental movement back to known-bad coordinates.

Example assertions should cover:

```text
both gate endpoints
both output drain endpoints
PMOS source and bulk to vdd
NMOS source and bulk to vss
```

## Version Compatibility

The pinned IHP symbols and standard-cell schematic were authored with Xschem `3.4.6`, while Ubuntu 24.04 supplies Xschem `3.4.4`.

This matters:

- A schematic may display correctly while the older CLI reports ERC warnings differently.
- Symbol parsing or netlisting behavior can differ across versions.
- The PDK's authored version is the preferred qualification version.

When shipping downloadable Xschem assets:

1. Match or exceed the PDK's Xschem authoring version where practical.
2. Record the qualified Xschem and PDK versions.
3. Test with the exact runtime image.
4. Do not interpret every standalone ERC warning as disconnected geometry.
5. Do not ignore warnings without inspecting transformed terminal coordinates and generated netlists.

## Common Failure Modes

### Wiring to the Symbol Origin

The placement coordinate is not necessarily a source, drain, gate, or bulk pin. Read the symbol.

### Stopping Near a Pin

A wire ending 10 database units from a gate is disconnected even if it visually overlaps at a coarse zoom.

### Assuming NMOS and PMOS Vertical Pins Match

The unrotated SG13G2 PMOS symbol has source at local `(20,-30)` and drain at `(20,30)`; NMOS has drain at `(20,-30)` and source at `(20,30)`.

### Forgetting Bulk

The bulk pin is at local `(20,0)`. A vertical rail through the symbol does not automatically connect bulk unless it reaches that exact coordinate.

### Trusting Net Labels Alone

`{lab=in}` on a wire does not connect that wire to a gate it misses.

### Omitting `spiceprefix=X`

IHP simulation symbols expect the subcircuit form. Preserve the PDK template properties explicitly.

### Using a Simulation Reference for LVS Unchanged

The IHP ngspice flow uses `X... sg13_lv_*`; the KLayout LVS schematic reader is qualified with `M... sg13_lv_*`. Keep separate server-owned references where tool contracts differ.

### Treating a Pretty Schematic as Verified

Opening without visible errors is not a connectivity test. Always inspect coordinates and netlist.

### Treating Old-Xschem ERC as Definitive

Standalone ports can be intentionally open. Verify in hierarchy and inspect generated devices before classifying a warning.

## Shipping Checklist

Before publishing or attaching an `.sch`:

- [ ] Exact PDK revision is known.
- [ ] Exact Xschem version is known.
- [ ] All used `.sym` files were read directly.
- [ ] Every transformed terminal coordinate was calculated or copied from a PDK-qualified topology.
- [ ] Every MOS gate, drain, source, and bulk is touched by the intended wire.
- [ ] Top-level pin symbols touch their nets.
- [ ] `spiceprefix`, model, dimensions, gate count, and multiplicity are explicit.
- [ ] Xschem netlisting was attempted in the qualified environment.
- [ ] Generated device connectivity was inspected.
- [ ] Standalone ERC warnings were distinguished from actual disconnects.
- [ ] A hierarchical driven test was used when standalone ERC was ambiguous.
- [ ] Critical endpoint regression tests pass.
- [ ] The downloadable/live asset matches the verified source byte-for-byte.

If any item is unknown, do not claim the schematic is netlist-qualified.
