# Grilles on existing bodies — 0.14.1

The user selected integrated openings in the existing body. Grilles remains the
third entry under Patterns. It shares the user-accepted 0.13.4 additive face
selection, preview-after-Done and in-place Create/Edit/Rebuild workflow.

## Use

1. Choose **Patterns > Grilles** and a grille type.
2. Set **Opening width**, **Rib width · on face**, and **Border**. Defaults are
   5 mm opening, 2 mm rib and 7 mm border. Repeat distance is opening plus rib.
3. Set **Direction** using 0° / 45° / 90° or any supported custom angle. Direction
   follows each face's local surface axes. It is separate from louver tilt.
4. **Select faces**, click each required side of the same body, then **Done**.
   No geometry preview is computed during selection. Clear selection starts over.
5. Review the real Fusion preview, then **Create grille**. Use **Edit existing**
   to change the saved dimensions/type and **Rebuild grille** on the same body.

| Type | Result |
| --- | --- |
| Parallel bars | Long through openings separated by continuous ribs |
| Crossed grid | Square through openings with connected ribs; rotate for diagonals |
| Louvers · inclined channels | Channels sheared within the wall, initially tilted 45° from the normal |

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
constant-thickness plate at the existing sampled wall witnesses. Tilt is 0–60°.
The existing first-wall isolation and border clipping remain in force. Curved
grilles and separate removable inserts are not introduced by this release.

New grilles use one owned cutter BaseFeature and one native consuming Cut
(solid record version 2). The cutter is the exact difference between an owned
copy of the historical input and the reviewed result; its volume must match the
removed material. Disconnected cutter lumps are allowed, while the final body
must stay one connected solid. Rebuild updates the same cutter source.
All three grille types can be interchanged through Edit.

Existing version 1 records retain their full-shape Join/Intersect history and
remain editable. They are not automatically migrated to Cut history; large dense
Rebuilds of legacy records have not been revalidated. The pattern settings recipe
remains version 5, and generic Patterns keep their existing persistence route.

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
