# Grilles on existing bodies

Shared storage update in 0.17.0: settings recipe 10 adds only the dormant
truss_bays/truss_axis defaults to old grille recipes. Grille geometry is unchanged;
reading legacy settings performs no writes. See [Planar truss](planar-truss.md).

The user selected integrated openings in the existing body. Grilles remains the
third entry under Patterns. It shares the user-accepted 0.13.4 additive face
selection, preview-after-Done and in-place Create/Edit/Rebuild workflow.

## Use

1. Choose **Patterns > Grilles** and a grille type.
2. Set **Opening width**, **Rib width · on face**, and **Border**. Defaults are
   5 mm opening, 2 mm rib and 7 mm border. Repeat distance is opening plus rib.
3. Set **Direction** using 0° / 45° / 90° or any supported custom angle. Direction
   follows each face's local surface axes. It is separate from louver tilt.
   Choose **Profile**: Flat, Raised, or Raised + chamfer. Raised profiles add
   **Height above face**, initially 3 mm. Their plate back is the bed-facing side.
   For Louvers, **Louver tilt** is adjustable from **0° to 45°**, default **45°**,
   in all three profiles. It is measured from the plate normal: 0° is vertical
   when the back rests on the bed. Direction presets rotate the grille on the
   face and are independent of this tilt limit.
4. **Select faces**, click each required side of the same body, then **Done**.
   No geometry preview is computed during selection. Clear selection starts over.
5. Review the real Fusion preview, then **Create grille**. Use **Edit existing**
   to change the saved dimensions/type and **Rebuild grille** on the same body.

| Type | Result |
| --- | --- |
| Parallel bars | Long through openings separated by continuous ribs |
| Crossed grid | Square through openings with connected ribs; rotate for diagonals |
| Louvers · inclined channels | Channels sheared within the wall, initially tilted 45° from the normal |

## Raised profiles for back-to-bed printing

Version 0.26.1 makes the **external frame** in Raised + chamfer slope all the way
from the selected face to its raised top, with no vertical step below a small
cap bevel. The sloped transition covers the whole Height. Its horizontal run
equals that height. The top footprint stays where possible and the root widens
inside the original plate; a taller frame can move the top inward. Incompatible
openings/borders fail explicitly rather than silently changing dimensions.
Mounting recesses also slope through the whole height, avoiding new vertical
steps around their clearance regions. The plate thickness/flat back stay intact.

**Rib top bevel (mm)** is separate: it finishes only the thin fins' upper edges,
not the external frame. Zero uses Auto:
`min(0.6 mm, Height/2, Rib width/4, Border/4)`. A positive value gives equal
vertical and horizontal bevel distances, and must be smaller than Height and
half Rib width. Geometry that does not fit is refused without shrinking it.
The fin shear stops at the start of the bevel so it cannot distort its45° angle.
This changes only the top segment; the main fin still has the selected tilt.

Recipe15 retains the28-field snapshot. Exact versions1–14 remain readable
without changing the saved geometry or metadata. Versions1–13 gain the absent
rib-bevel field only in memory. An Edit notice explains the new full-height
frame before explicit Rebuild. The original plate perimeter is not rounded.
Auto screw positions retain the0.26.0 inward shift; custom insets stay exact.

Validation for0.26.1 passes1110 Python tests, five Node UI suites and browser
checks at300/380/520px, including the380×513 docked layout. Six isolated Fusion
2705.1.30 cases cover all five families plus a refusal. Full-height analytic
faces and inside/outside samples at10/50/90% of Height establish a root-to-top
slope, independently of top-cap angles. Create/Edit/Delete preserve the same
body/history and restore the caller. See
[grille-ramp-0.26.1.json](validation/grille-ramp-0.26.1.json).

Parallel bars, Crossed grid and Louvers each support **Raised** and **Raised +
chamfer**, six new combinations. The original Flat profile remains the default.
Raised parallel bars/grid extend above the selected face; raised louvers shear
sideways by `height × tan(tilt)`, up to their height at 45°. Their original
plate openings are vertical. The same Louver tilt control applies to Flat and
external louvers. Height is 0.2–20 mm above the
original face, independent of plate thickness. Taller louvers require more Border.

The raised frame can leave a flat reveal within the original border. Its footprint
never expands outside the original plate. Rib top bevel narrows the upper ribs
(Auto is bounded by height/rib/border); Opening
width and Rib width still describe the roots on the original face. The local
section diagram shows the back against the bed and responds to profile/height.
Both new fields have illustrated help. Slots are covered by Parallel bars;
no redundant slot family or HVAC nozzle simulator is added.

Raised profiles require **one selected rectangular planar face of a uniform
solid plate**, a flat back, Border >= 0.5 mm and at most 200 openings. Whole-body,
multi-face, curved and stepped-back raised output is refused. Full plate material
and volume checks prove the back is flat, rather than assuming this from a few
rays. The intended print-up direction is the selected outward face normal;
the add-in does not rotate the model. Geometry bounds do not prove printing on
every material/printer, airflow or mechanical strength.

New raised geometry uses one perforated plate and one or two multi-loop profile
segments; no native cutter Boolean or history feature is made per opening.
Corresponding convex loops are validated at bottom/mid/top, with planar shared
sides, exact closed volume and every downward side limited to 45 degrees for
this print direction. Unsupported height/frame collisions are refused without
changing dimensions. These rectangular profiles use an exact numeric border
inset, avoiding the general surface-boundary capsule's decomposed fragments.

Raised output adds material, so it uses full-shape Join/Intersect history, three
owned features. Flat-to-raised Edit converts a validated end-of-history Cut:
the original target, BaseFeature and ownership UUID are retained; only the last
owned Cut is replaced by owned Join/Intersect. The enclosing native command owns
rollback on failure. Later features must first be preserved. Subsequent height,
profile and raised-to-flat Rebuilds retain that full-shape history. No user body
is replaced, renamed or duplicated. Settings recipe 9 reads versions 1–8 without
rewriting a saved recipe until Rebuild. Old raised louvers load at their actual
original fixed 45°, regardless of the old dormant angle value. Old Flat angles
above 45° propose 45° for the next Rebuild and show an explicit notice; reading
Edit does not modify their existing geometry. Malformed old angles are refused.

Fusion 2705.1.30 passes ten isolated MCP cases: all six raised/profile combinations,
conversion to/from Flat and three guard refusals. Preview mesh upload/cleanup is
checked for bars and external louvers. Original caller documents are unchanged.
Local checks pass 974 Python tests, three Node UI suites and headless Edge layouts
at 300/380/520 px. Source hashes and case measurements:
[raised-grilles-0.15.0.json](validation/raised-grilles-0.15.0.json).

## 0.16.1 adjustable tilt validation

Local checks pass 988 Python tests, the three Node UI suites, compilation and
whitespace checks. Headless Edge at 300/380/520 px checks the control in all
three profiles, default/maximum 45°, valid zero, blocked 46°, changing section
drawings, illustrated help, mounting summary and no horizontal overflow.

Fusion 2705.1.30 passes ten isolated MCP cases. Actual analytic wall normals
confirm 0°, 20° and 45°; clipped ends of rotated fins have smaller projected
angles. Flat, Raised and Chamfered Edit cycles retain target/name/body count and
owned history, including mounting bores/seats. Cached previews clean up their
graphics. An old raised recipe with dormant angle 0° reads at its original
actual 45°, leaving geometry and saved recipe unchanged until explicit Rebuild.
Every temporary document is discarded and the original caller is restored.
The tilt change uses the same one/two loft segments and Boolean budget;
it does not add a feature or cutter per opening. These small fixtures do not
repeat dense-grid, physical-printing, pointer/orbit, save/reopen or Undo/Redo proof.

Evidence: [grille-tilt-0.16.1.json](validation/grille-tilt-0.16.1.json).

## Optional mounting holes

**Mounting · optional** defaults to Off. Choose **4 plain holes** or **4
countersunk holes · 90°**, then M3/M4/M5/M6. Hole allowance defaults to **0.3 mm
added to the diameter**, so M4 creates a 4.3 mm through hole. This is a chosen
modelling allowance, not a claim to a particular ISO 273 fit or printed fit.

The initial countersink head envelope uses the maximum catalogue diameters
6.72 / 8.96 / 11.20 / 13.44 mm for M3 / M4 / M5 / M6 from the
[Böllhoff ISO 10642 data sheet](https://eshop.boellhoff.de/out/media/pdf/ISO_10642_Stahl_10.9___en.pdf).
Head allowance defaults to **+10% on diameter**, independently of bore clearance.
For M4 this gives head seat diameter 9.856 mm and 90-degree depth
`(9.856 - 4.3) / 2 = 2.778 mm`. The plate must retain at least 0.2 mm of straight
bore below the cone; this geometrical margin is not a strength rating.

Under **Advanced → Mounting holes**, **Screw inset (mm)** is beside Screw size.
Larger values move the four centres inward, measured from both outer edges.
Zero uses Auto. In0.26.0 Auto sits0.8mm farther inward; M4 defaults to7.428mm,
previously6.628mm. Explicit insets keep their original exact distances and
minimum safety bounds. The solid border is recalculated before the pattern.

In the closed **Mounting settings**, **Head Ø = 0** uses the catalogue preset.
Enter a measured head diameter for another screw before applying the percentage:
8 mm with +10% gives an 8.8 mm seat. An M-size alone does not identify every head
shape. Countersunk here means a flat 90-degree head; cylindrical heads use Plain,
without a counterbore. **Screw inset = 0** calculates symmetric corner insets;
an explicit value is measured from both outer edges to each hole centre.
Every control has illustrated help and the summary shows resulting dimensions.

### Automatic border before preview — 0.16.2

With mounting enabled, **Minimum border** remains the user's requested minimum.
Before plate inspection, repeat layout, cell sizing, cutters or preview geometry,
the host resolves the effective solid perimeter from the screw/head envelope:

`rim radius = head diameter with allowance / 2 + 1.2 mm`

`automatic inset = rim radius + 0.5 mm + 0.8 mm` (since0.26.0)

`border used = max(requested minimum, inset + rim radius)`

This reserves the whole head plus surrounding material inside a continuous
perimeter, rather than filling only four corners after making a pattern.
Plain and Countersunk both reserve head access. A custom measured head or explicit
centre inset also updates this calculation; a larger requested border is retained.
The UI summary and diagram show the effective border before selecting a face.
Switching to a smaller screw recalculates from the original requested minimum,
so a previous automatic enlargement does not become a permanent user setting.
No extra toggle or setting is added. Off uses the original requested border.

| Screw | Border with catalogue head, +10%, Auto inset and 7 mm minimum |
| --- | ---: |
| M3 | 11.092 mm |
| M4 (default) | 13.556 mm |
| M5 | 16.020 mm |
| M6 | 18.484 mm |

Plate/head/inset/thickness and remaining grille area are checked before repeat
construction. Unsupported dimensions are refused rather than shrinking a screw
or changing an opening width. The full-border route skips four restoration
intersections and four unions previously needed for the corner lands.
Settings recipe 9 retains the requested minimum separately from the resolved
border recorded in preview diagnostics. Old mounted recipes show a notice about
the new border calculation before Rebuild; simply reading Edit leaves their
saved geometry and settings unchanged.

This increment passes **993 Python tests**, three Node UI suites, compilation,
whitespace checks and headless Edge at 300/380/520 px. Fourteen isolated MCP cases
on Fusion 2705.1.30 cover plain/countersunk M4, raised and chamfered louvers,
M3/M6, a custom head/inset, a larger requested minimum, zero requested minimum,
256 dense-grid openings and early border/thickness refusals. Independent material
witnesses sample all four inner border limits at three plate depths, excluding
the head envelopes. Bore/seat witnesses, cached preview cleanup, same body/name/
history, and original caller restoration pass. An M3→M6→M4 Edit cycle resolves
10.292→17.684→12.756 mm and returns to exactly the original volume, with no stale
holes. Old mounted settings read without writing geometry or recipes.

Evidence: [grille-auto-border-0.16.2.json](validation/grille-auto-border-0.16.2.json).
These geometric checks do not prove physical screw fit, strength, printing,
pointer/orbit behavior, save/reopen or Undo/Redo.

Both mounting modes reserve four solid corner blocks within the original plate,
with at least 1.2 mm material beyond the selected head envelope. Hole positions
leave an additional 0.5 mm to the exterior; the blocks reach the exterior corners
and join a frame with Border >=1 mm. Blocks must be separated from one another.
The automatic perimeter already contains the original plate material in these
regions. A fallback for internal narrow-border callers retains corner restoration.
Raised fins/frame above the blocks are cleared
to the original front face, so the head has access and a flat seating plane.
Neither the plate footprint nor its back is enlarged. Four analytic cylinders
and optional conical seats cut the holes; no feature is created per hole.

Mounting requires one rectangular uniform solid plate face. An excessive minimum
border, inadequate plate size, invalid inset or excessive countersink depth is
refused before pattern construction. Plain holes also work on thinner plates.
Mounting works with Flat, Raised and Chamfered profiles, including the dense
Flat Crossed grid path. Off adds no plate inspection or mounting geometry work.
All changes share the existing preview/Create/Edit/Rebuild transaction. Editing
between Off/Plain/Countersunk reconstructs from the original plate, leaving no
old holes or duplicate bodies. Settings recipe 9 reads versions 1–6 with mounting
Off and rewrites only on successful Rebuild.

The type dropdown and Direction occupy full rows. Direction presets are disabled
while selecting faces or creating geometry. Local illustrated help explains the
dimensions. The sample diagram follows opening/rib/border/direction changes and
adds a separate section view for louver tilt; it is not a model preview.

## Dense Crossed grid

The original square-per-opening route hit the generic 200-cell face limit on
large plates, even at a normal 5 mm opening and 2 mm rib. Version 0.14.1 adds a
specialized single-solid construction when Crossed grid exceeds that generic
budget. Opening, rib, border, rotation and offset dimensions are preserved.
Small grids continue through the original path.

The new route defines one perforated prism with shared edges and multi-loop
caps, rather than thousands of individual cutter Booleans. The original border
trim allowance is retained, including partial openings at the border. The frame
is connected to a temporary source copy before the normal in-place history
operation; the selected body is not replaced or duplicated.

The dense path requires rectangular, chart-aligned planar first-wall regions,
clipped edge openings and at least 0.1 mm border. Nine rays locate a candidate
wall; full-region material and back-clearance volume checks must then prove the
constant-thickness region, including spaces between the rays. Dense masks on
different selected faces must not overlap. Unsupported complex faces are refused
instead of silently enlarging openings or omitting rows.

Work is bounded to 4,096 openings per face, 8,192 in total, 10,000 numeric
candidates and 256 row/column bands per face. The existing 200,000-triangle
display budget still applies. These limits do not change general Patterns or
promise a particular computation time. The settings recipe version and source
body ownership remain unchanged.

Edit checks inspect owned features in timeline order and restore the history
marker once, after all checks. Restoring between checks recomputed the dense
Combines repeatedly. Ownership, operation, tool, target and original-input
validation are retained, including marker restoration if inspection fails.

New Cut records inspect the unchanged original target immediately before Cut,
keeping the tool BaseFeature active. They also read fingerprint vertices in one
native SMT export with a bounded reference parser. Coordinate multiplicity,
rounded geometry, volume, bounds and topology counts are retained in the digest.
Unsupported export formats or non-identity exported transforms use the existing
SDK fingerprint; that fallback can be slower on large bodies. Generic Patterns
and old full-shape records keep their original fingerprint path.

## Supported geometry

This release supports planar faces on one root-component solid. Faces may be on
different sides of the body. Per-face repeat grids are centered independently.
Louvers require a straight, rectangular, chart-aligned face without holes and a
constant-thickness plate at the existing sampled wall witnesses. Tilt is 0–45°.
The existing first-wall isolation and border clipping remain in force. Curved
grilles and separate removable inserts are not introduced by this release.

New Flat grilles use one owned cutter BaseFeature and one native consuming Cut
(solid record version 2). The cutter is the exact difference between an owned
copy of the historical input and the reviewed result; its volume must match the
removed material. Disconnected cutter lumps are allowed, while the final body
must stay one connected solid. Rebuild updates the same cutter source.
All three grille types can be interchanged through Edit.

Existing version 1 records retain their full-shape Join/Intersect history and
remain editable. They are not automatically migrated to Cut history; large dense
Rebuilds of legacy records have not been revalidated. The pattern settings recipe
is now version 9, and generic Patterns keep their existing persistence route.

Create modifies the selected body instead of adding a replacement copy. The
existing single-owned-pattern-per-body and timeline-end Edit contract remains;
independent Pattern and Grille layouts cannot be stacked on that same body.

## Efficiency and evidence — 0.14.0 foundation

Louver rectangle validation, surface mapping and inner-border coordinates are
prepared once per selected face, within one preparation. No persistent cache or
new recipe fields are added. The existing wall-depth pass also checks louver
thickness; cutter construction does not repeat its rays. In the native three-slot
fixture this uses 27 wall queries instead of the prior path's two passes of 27,
and one face setup instead of three. This does not imply a universal time ratio.

Fusion 2705.1.30 request `c6830fbb-9e71-428c-8b0e-917e3001b662` passes 16 focused
cases: all three families, louver angles 0/30/45/60°, rotated parallel bars,
Create/Edit/Rebuild without duplicate bodies, six-side box grilles, and the shared
preview/selection/Cancel/rollback lifecycle. Native query counts equal the number
of original wall witnesses. Source references and the original document snapshot
are preserved. The unchanged full surface/polygon matrices were not repeated.

Local validation passes 929 Python tests, three Node UI suites and headless Edge
checks at 300/380/520 px. The browser check verifies the full-row dropdown,
direction presets, visible tilt and all three diagrams without horizontal overflow.
Using CSS classes replaces inline layout attributes blocked by the palette's CSP.
Evidence and source fingerprints: [grilles-0.14.0.json](validation/grilles-0.14.0.json).
Physical pointer/CEF acceptance of the new controls remains separate from scripted
proof. Native printing, airflow, strength and line-of-sight behavior are not tested.

## 0.14.1 validation

The staged 961-opening fixture on Fusion 2705.1.30 passed Create, Edit and Rebuild
with the same body and exactly two owned features. Observed Create / complete
Edit-and-Rebuild times changed from about 33 / 133 seconds in request
`1d5f57e4-0273-4974-b979-244aea1c706f` to 6.5 / 21 seconds in request
`7fff25e0-7c8c-4ae3-a6b4-90789f4ec48f`. These are fixture observations, not a
universal performance ratio. The original document snapshot was unchanged in
both requests. The latter request passed 16 focused native cases.

Final request `15df7954-633f-49a8-a56c-9d726e6b95cc` passes all 17 focused cases,
including 225, 961 and 3,025 openings, two perpendicular faces, legacy Edit,
three-family conversion, exact bulk fingerprints and the production selection,
preview, cached Create and rollback lifecycle. The original caller document,
component, camera and references are restored. The 3,025-opening fixture measured
10.9 seconds preparation, 24.2 seconds Create and 80.5 seconds for complete
Edit-and-Rebuild; its 5 mm openings and 2 mm ribs were retained. The final
961-opening case measured 6.3 seconds Create and 20.8 seconds Edit-and-Rebuild.

Local checks pass 962 Python tests, three Node UI suites, compilation and the
same headless Edge layout checks at 300/380/520 px. Evidence and source hashes:
[dense-cross-grid-0.14.1.json](validation/dense-cross-grid-0.14.1.json).
The dense route remains restricted to the proven planar rectangular wall geometry
described above. Physical pointer/CEF acceptance, orbit performance at this density,
save/reopen, Undo/Redo and printing remain untested.
