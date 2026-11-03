# Fans & Propellers

Version 0.27.0 adds an independent tool under **Mechanisms → Fans & Propellers**.
The first release implements the approved A–G families. The additional H family now generates a straight radial blower impeller; an optional scroll housing and removable inlet lid are implemented. These are original geometric rotors, not copies of commercial blades
or a simulation of cooling, pressure, noise, balance or strength.

## Start without drawing anything

1. Open a parametric Fusion Design, activate its root and move the timeline to
   the end. Choose **Fans & Propellers** in Partelier.
2. Choose **PC axial**, **Wide blade**, **Slim rotor**, **Tip-ring rotor**, or a
   **2 / 3 / 4-blade propeller**, then a size preset. Press **New fan**.
3. Set the real shaft diameter and allowance. Expand **Hub & shaft fit** for a
   D-shaped hole, hub height or an optional radial set-screw pilot bore.
4. Review the live Fusion preview, then **Create fan**. The saved operation
   appears in **Saved features** in this section, with Edit and Delete.

The default rotor is centred on the document origin with its axis along Z.
Rotation labels mean viewed from local +Z. A preview adds no lasting bodies or
timeline entries. Cancel, the main palette Close/X and a document change cancel
the session. Root material appearance is used when available, otherwise a solid
neutral Fusion-style colour. The shaded preview is an approximation; saved CAD
uses smooth surfaces.

## Dimensional presets

| PC nominal frame | Mounting pitch | Preset frame depth |
|---|---|---|
| 40 mm | 32 mm | 10 mm |
| 60 mm | 50 mm | 25 mm |
| 80 mm | 71.5 mm | 25 mm |
| 92 mm | 82.5 mm | 25 mm |
| 120 mm | 105 mm | 25 mm; Slim 15 mm |
| 140 mm | 124.5 mm | 25 mm |

References: Noctua dimensional specifications for
[40](https://www.noctua.at/en/products/nf-a4x10-flx/specifications),
[60](https://www.noctua.at/en/products/nf-a6x25-pwm/specifications),
[80](https://www.noctua.at/en/products/nf-a8-pwm/specifications),
[92](https://www.noctua.at/en/products/nf-a9-pwm/specifications),
[120](https://www.noctua.at/en/products/nf-a12x25-pwm/specifications),
[120 slim](https://www.noctua.at/en/products/nf-a12x15-pwm/specifications), and
[140](https://www.noctua.at/en/products/nf-a14x25-g2-pwm/specifications).
The rotor diameter is smaller than the nominal frame. These starting dimensions
do not specify motor hubs, PCB mounts, bearings or OEM replacement compatibility.
Blade counts and shapes are Partelier choices, not manufacturer data.

Air-propeller presets are **5×3**, **6×4**, **8×4** and **10×4.5 inches**.
The first number is diameter, the second geometric pitch. The tool stores mm.
See [APC nomenclature](https://www.apcprop.com/wp-content/uploads/2023/05/APC-Propeller-Nomenclature.pdf).
Pitch does not predict actual advance or thrust. Presets apply only after an
explicit style/size selection; dimension changes switch the label to Custom.
Changing style while Custom is selected starts that family's default preset;
selecting Custom alone retains the current dimensions.

## Shapes and outputs

**Blade shape & twist** exposes exact root/middle/tip chord widths and angles,
or constant geometric pitch. The latter derives each local angle from
`atan(pitch / (2π × radius))`. Sweep, camber, root/tip thickness, root fillet,
optional tip-edge rounding and handedness remain adjustable. The original
rounded cambered section is a geometric profile, not an imported rated airfoil.
Overlapping blades or unsupported fillets are refused without changing values.

**Tip-ring** joins a rotating annulus to the tips; its width and height are
adjustable. It is part of the rotor. **Rotor + frame** adds an independent square
frame with a circular opening and four mounting bores. **Rotor + frame + guard**
adds a separate front guard with radial spokes. Clearance and frame depth must
fit the actual blade envelope. These bodies do not contain a motor mount or
bearing mechanism. Set-screw bores are plain holes, without threads.

**Hub fit coupon** produces only the hub and shaft/set-screw holes, allowing a
small physical fit check before printing a whole rotor. No support-free print
orientation is asserted for the twisted blades. Inspect supports in the slicer
and validate fit, balance and strength before operation.

## Optional existing geometry

**Fit circular opening**: start with a complete circular BRep edge in the root
component, for example an extruded circular opening. It defines the centre and
axis. Rotor diameter becomes `opening diameter − 2 × Tip gap`. Updating Tip gap
refits that diameter. The referenced body is never modified.

**Use sketch outline**: draw one closed root-component sketch profile, with the
blade root on the left and tip on the right in sketch coordinates. A simple
20×4 mm rectangle is a valid first example. It must have finite root/tip widths,
one width at every span and no holes. Planform length scales to the blade span;
Outline width scale changes its width. Twist and section thickness are applied
separately. Root/middle/tip generated width fields are hidden in sketch mode.
This samples nine span stations; it does not preserve arbitrary outline details
between those stations. Pointed ends, multiple intervals and complex profiles
over 256 sampled points are refused. Reset references returns to the origin.

## Persistence and efficiency

The engine lofts one prototype from nine smooth sections, finishes its hub root
once and repeats the finished blade. A one-entry session cache stores the
unbored rotor. Shaft/fit and frame/guard changes reuse it; blade/outline changes
invalidate it. The preview uses a bounded coarse STL mesh, full opacity and
cached outlines. It never runs a mesh calculator or creates graphics BRep bodies
while orbiting. Native scratch features are removed inside the rollback compute
command; Create saves one owned BaseFeature, without per-blade history.

An exact version-3 recipe stores all 50 fields, references, output mappings and
body signatures. Rebuild updates the same rotor body, preserving names and
visibility. Optional frame/guard outputs can be added or removed. External body
edits, changed references and later timeline dependencies are guarded. Delete
removes only the operation's owned feature; unrelated bodies remain.

Validation and its limits are recorded in
[fans-0.27.0.json](validation/fans-0.27.0.json). Physical printing, operating RPM,
cooling/thrust/noise, balance, fatigue, save/reopen and Undo/Redo are not verified
by these geometry tests.

## Radial blower impeller (H)

Choose **Radial blower impeller**, a size reference or Custom, then New fan.
The result is one solid containing a full circular backplate, the central bored
hub, and equally spaced straight radial vanes. Rotor diameter is exact, including
vane tips; the shared shaft options and circular-opening placement still apply.
The PC size menu is a dimensional reference only, not blower motor compatibility.

Three dedicated controls set **Vane height**, **Backplate thickness** and
**Vane thickness**. Hub height stays independent; the backplate starts at the
bottom of the hub. The flat backplate can face the print bed. Twist, chord,
camber, sketch outline, rotation and root finishing controls are hidden because
this symmetric radial geometry does not use them. Supported outputs are Rotor only, Hub fit coupon and Rotor + volute + lid. An axial square frame is not a blower volute and is
therefore explicitly refused, as is a sketch vane outline. No aerodynamic or
physical printing result is inferred from the geometry.

The generator unions temporary primitives and trims the diameter once; it does
not add native features per vane. The unbored impeller uses the existing geometry
cache, so shaft changes can reuse it. Create/Edit/Delete retain the shared fan
ownership contract. Exact old 40-field recipe-1 fans remain read-only compatible;
new writes use recipe 3 with 50 fields; exact 43-field recipe-2 records also remain readable. Legacy data cannot claim the new style.

Local planner/recipe and simulated UI tests cover the added scope. The isolated
Fusion test passed preparation (71 ms on the tested PC60 fixture), cached-mesh
creation/cleanup, same-body shaft and vane Rebuild, and exact owned Delete,
restoring the caller. See [native evidence](validation/blower-impeller.json).
Physical fit, balance and operation remain user tests.


## Blower scroll housing and removable lid

Choose **Rotor + volute + lid** for three independently owned bodies. The housing
has a flat floor, a growing Archimedean scroll chamber, a central motor-shaft
opening, and a tangential outlet pointing along local -Y. The separate lid has a
central axial inlet. **Scroll expansion** also defines the outlet width;
**Outlet extension** controls its projection beyond the large scroll radius.
**Housing wall / lid** controls the radial wall allowance and floor/lid thickness.

Radial tip gap and axial clearance keep the rotor separate from the housing;
Lid separation additionally keeps the removable lid off the top wall. Inlet0
means hub diameter plus twice the housing wall. The motor opening is a clearance
hole, not a bearing or motor mounting seat. Optional four peripheral bosses have
matching through-bores in the lid and housing; Mount hole diameter is exact.
There are no threads, screw-head seats or sealing claims.

The scroll is explicitly polygonal: a bounded 64–256-segment approximation, with
a 0.02 mm chord-sag target (less than 0.03 mm at the largest allowed size). Radial
inflation protects minimum rotor clearance between vertices. No native feature
is created per segment. The housing uses temporary solids and cached display
meshes; edits to housing dimensions reuse the cached unbored rotor.

Native PC60 fixture passed in 274 ms, using 93 scroll segments and 3000 display
triangles. It checked three disjoint solids, open inlet/outlet/motor/screw paths,
preview cleanup, same-body housing edits, removal of optional bodies and exact
owned Delete, restoring the caller. See [volute evidence](validation/blower-volute.json).
These timings are fixture observations; print fit, motor installation and airflow
remain physical tests. The lid/housing need separate print orientations.


In the 0.29.0 upstream-update fixture, changing the real source sketch circle
from radius 30 to 35 mm regenerated the referenced rotor diameter from 58.8 to
68.8 mm. The update retained owned body identities and timeline size; a repeated
refresh was a no-op (observed refresh 139 ms). A separate sketch-only blade-outline
edit was detected by the revision gate and rebuilt the same rotor (2.42 s), without
adding bodies or timeline steps. See
[family update evidence](validation/auto-update-families.json).

Headless full-palette checks at 300, 380 and 520 px verified visible volute fields,
mounting-hole toggles, field/help separation, and scroll/lip help dialogs without
horizontal overflow or browser errors. Screenshots were inspected at the compact
width. The bridge was mocked; this is layout evidence, not native Fusion execution.
See [UI evidence](validation/volute-ui.json).
