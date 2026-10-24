# Grilles on existing bodies — 0.14.0

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

## Supported geometry

This release supports planar faces on one root-component solid. Faces may be on
different sides of the body. Per-face repeat grids are centered independently.
Louvers require a straight, rectangular, chart-aligned face without holes and a
constant-thickness plate at the existing sampled wall witnesses. Tilt is 0–60°.
The existing first-wall isolation and border clipping remain in force. Curved
grilles and separate removable inserts are not introduced by this release.

Create modifies the selected body instead of adding a replacement copy. The
existing single-owned-pattern-per-body and timeline-end Edit contract remains;
independent Pattern and Grille layouts cannot be stacked on that same body.

## Efficiency and evidence

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
