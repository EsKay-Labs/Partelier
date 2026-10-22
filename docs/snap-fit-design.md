# Exterior cantilever snap-fit (0.6.0)

The first snap-fit family adds an exterior clasp to an existing base and cuts a
blind receiving recess in its lid. It uses the same two root-component bodies;
Create adds no final bodies. A hook at the free end points into the lid. Its
inclined lead-in guides insertion; a shoulder retains against the recess edge.
The source seam is preserved. The two parts are printed separately.

## Supported selection

Use a parametric Design with the root active and history marker at the end.
Select a planar exterior wall on base A, a coplanar wall on lid B with the same
outward normal, and a complete straight boundary edge of A at their seam. A
coincident edge on B is accepted. Body A lies entirely on one side of that seam;
B lies on the other. Both bodies stay behind their common exterior wall plane.
These bounded conditions permit enclosure walls as well as the reference boxes;
curved, offset, nested or crossing selections are refused.

Local X points out of the wall, Y follows the rim and Z points from A toward B.
The adapter checks bounds after transforming detached copies into that frame,
so rotating the design does not change the intended geometry checks. Native
intersection coverage proves that A contains the complete embedded root and B
contains the recess plus a clearance-sized border/back wall. Invalid dimensions
are reported without shrinking a requested feature or skipping a cut.

## Dimensions and workflow

| Setting | Default | Meaning |
| --- | --- | --- |
| Width | 8 mm | Width along the seam |
| Thickness | 1.5 mm | Flexible arm thickness outside the wall |
| Reach | 16 mm | Free end above the seam |
| Clearance | 0.3 mm | Arm/wall gap and clearance around the receiving recess |
| Hook engagement | 1 mm | Hook penetration behind the exterior plane |
| Lead-in | 3 mm | Axial length of the insertion ramp |
| Count | 1 | One centered clasp or 2–20 equally spaced clasps |
| Start / end margins | 5 / 5 mm | Rim ends to outer receiving envelopes |
| Root length | 4 mm | Attachment height below the seam |
| Attachment overlap | 0.5 mm | Root penetration into A |

The HTML form keeps size and fit visible; Advanced contains placement and root
construction. Direct picking creates no second parameter panel. Preview shows
the full paired solids in their current Fusion appearances and temporarily hides
the selected originals. Cancel restores their exact prior light-bulb settings.
Camera movement does not dispose the graphics. Failed refreshes retain the last
valid view, marked stale; Create requires a current successful preview.

Edit existing accepts an owned A/B body, face, edge, BaseFeature or a root Part
containing exactly one snap-fit. It restores the complete saved dimensions.
Create/Rebuild runs in a zero-input native command transaction. Failures request
rollback. Saved sources are read before the owned history block; the marker is
restored even on error.

## Persistence and boundaries

`solid_pair.py` stores two exact final tool shapes in an owned BaseFeature and
uses four native Combines (Join/Intersect for A and B). The selected bodies keep
their identities, names and visibility, and tools are consumed at the end of
history. Rebuild updates the same two BaseFeature sources and retains the four
Combine references. It does not append another result pair or hide backups.

Ownership, native feature definitions, contiguous history and output fingerprints
are checked before editing. Downstream edits that change either target are
refused. Later independent history is allowed. An additional independent clasp
operation on already-owned targets is refused; use Count and Edit/Rebuild.
Stacking different Partelier operations on the same targets may guard an earlier
result against rebuilding. Upstream changes require explicit Rebuild; the stored
tool solids do not automatically regenerate when source features change.

This family defines geometry, not a material model. Default dimensions do not
establish safe strain, fatigue life or printer fit. Motion, assembly force,
orientation, save/reopen and manual Undo/Redo require further acceptance. There
is no hidden FEA, automatic stress optimization, print-in-place mode or alternate
snap family behind this first tool.

For a disposable manual example, add/run `tools/fusion/SnapFitFixture` as a
Fusion script. It creates a new unsaved two-body document and gives the picks.
The fixed `snap_fit` native validation scenario uses its own rollback-only
fixtures; see [native checks](fusion-validation.md).
