# Exterior cantilever snap-fits (0.7.0)

The snap-fit tool adds an exterior clasp to an existing base and cuts a
blind receiving recess in its lid. It uses the same two root-component bodies;
Create adds no final bodies. A hook at the free end points into the lid. Its
inclined lead-in guides insertion; a shoulder retains against the recess edge.
The source seam is preserved. The two parts are printed separately.

## Types and printing details

The same selection workflow offers three actual geometries:

| Type | Geometry |
| --- | --- |
| Straight | Constant-thickness cantilever arm and retaining hook |
| Tapered | Arm thickness decreases from the root to 65% at its free end |
| Twin | Two parallel flexible arms and hooks, with a shared attached root |

Type changes retain the selected source geometry and the requested outer width,
reach and placement. Twin divides that width between its two arms; the derived
central gap also leaves material between the receiving regions. These geometry
choices do not calculate force, permissible strain or material fatigue.
Twin's central gap is max(thickness, 4 clearances + 0.2 mm); each arm gets half
the remaining outer width. Additional chamfer constraints protect the receiving
web between the two slots.

New snaps enable print-friendly shape and a 0.3 mm edge chamfer. Print-friendly
adds a 45-degree ramp below the external root and a 45-degree roof to the
receiving recess. Their build-up direction is local +Z, from base A toward lid B.
It does not infer the slicer's actual bed orientation. The retaining shoulder
keeps its locking surface; automatic finishing must not remove the catch.
Requested chamfers are applied to the generated detail, preserving its joined
connections and unrelated source edges. Invalid sizes are refused rather
than silently reduced. Finishing occurs after the generated root, arms, hooks
and ramp are joined. It targets their specified exposed edges and the receiving
entry sides; it does not chamfer the internal joins or the flat retaining lip.

**Print-friendly** and **Chamfer edges** are separate settings. A cosmetic bevel
alone cannot remove every unsupported shelf. Check the chosen orientation and
layer preview before printing; these are shape changes rather than a slicer or
material simulation. Prusa's [modeling guide](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135)
discusses chamfers and overhang limits, which depend on nozzle and print settings.
Formlabs' [snap-fit guide](https://formlabs.com/global/blog/designing-3d-printed-snap-fit-enclosures/)
discusses cantilever geometry and material constraints.

## Supported selection

Use a parametric Design with the root active and history marker at the end.
Select a planar exterior wall on base A, a coplanar wall on lid B with the same
outward normal, and a complete straight facing rim on either wall. A gap between the rims is
supported. A pick on B is mapped to A's actual edge only when both complete
projected spans match, the walls are coplanar, and their facing boundaries are
unambiguous. A's real edge remains the saved reference. Partial, shifted,
diagonal, nonboundary and far-side picks are refused.

The selected exterior faces lie on opposite sides of the seam; internal tongue
and groove lips may cross it. Both bodies stay behind the common exterior wall
plane. Whole-body bounds along the assembly direction do not restrict an inner
lip; exact attachment coverage and solid clearance checks apply instead.

Local X points out of the wall, Y follows the rim and Z points from A toward B.
The adapter checks exterior-plane bounds after transforming detached copies
into that frame, so rotating the design does not change the geometry checks. Native
intersection coverage proves that A contains the complete embedded root and B
contains the recess plus a clearance-sized border/back wall. Invalid dimensions
are reported without shrinking a requested feature or skipping a cut.
A checked temporary difference must preserve the complete final A volume after
subtracting B; failed boolean calculations are refused. The inward hook is also
checked against the original A, so a tall lip cannot fuse its free end back into
the base. Ordinary seam contact and noninterfering internal lips are supported.

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
| Start / end margins | 5 / 5 mm | Rim ends to complete receiving openings, including chamfers |
| Root length | 4 mm | Attachment height below the seam |
| Attachment overlap | 0.5 mm | Root penetration into A |
| Type | Straight | Straight, tapered or twin arms |
| Chamfer edges | On | 45-degree finish of supported generated edges |
| Chamfer size | 0.3 mm | Explicit bevel size; invalid combinations are refused |
| Print-friendly shape | On | Root ramp and receiving roof for the stated build direction |

The HTML form keeps type, size and fit visible; Advanced contains placement,
root construction and print/edge finishing. Direct picking creates no second parameter panel. Preview shows
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
Stored version 1 snap-fit recipes load with Straight, chamfers off and printing
ramps off. Reading old dimensions does not change their saved geometry. Explicit
Rebuild writes the new version 2 recipe; it enables a different shape only when
the user chooses it. Current version 2 recipes store all fifteen fields.

Stacking different Partelier operations on the same targets may guard an earlier
result against rebuilding. Upstream changes require explicit Rebuild; the stored
tool solids do not automatically regenerate when source features change.

This family defines geometry, not a material model. Default dimensions do not
establish safe strain, fatigue life or printer fit. Motion, assembly force,
orientation, save/reopen and manual Undo/Redo require further acceptance. There
is no hidden FEA, automatic stress optimization, print-in-place mode or alternate
annular, ball-detent or torsion family behind these cantilever types.

For a disposable manual example, add/run `tools/fusion/SnapFitFixture` as a
Fusion script. It creates a new unsaved two-body document and gives the picks.
The fixed `snap_fit` native validation scenario uses its own rollback-only
fixtures; see [native checks](fusion-validation.md).
