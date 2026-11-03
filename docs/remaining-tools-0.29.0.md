# Partelier 0.29.0: remaining tools and acceptance guide

The remainder of the 0.28 implementation list now has working CAD paths. Hardware
pockets remain excluded by request. Physical fit, release, durability and airflow
still require actual prints; CAD and headless checks do not establish those.

| Area | What is available | Where to start |
| --- | --- | --- |
| Attached mechanical pairs | Guides, dovetail, bayonet, clevis and three single-axis hinge families join the two selected original solids | Mechanical pairs → Output → Attach to two bodies |
| Linked louvers | Common link moves all vane cranks; split frame, access holes, assembled and flat print layouts | Mechanical pairs → Linked louvers |
| Parallel lift | Equal-arm four-bar keeps its moving mounting plate parallel | Mechanical pairs → Parallel lift |
| Offset four-bar hinge | Unequal arms rotate and offset the moving mounting plate, opening 0–90° | Mechanical pairs → Offset four-bar hinge |
| Blower housing | Scroll housing, tangential outlet and removable inlet lid around the rotor; optional mounting holes | Fans & Propellers → Radial blower → Housing |
| General lid outlines | Closed planar concave and mixed-curve/spline outlines, plus existing rectangle/circle/convex fast paths | Lid lip & groove → Continuous perimeter |
| Automatic updates | Saved features follow resolvable source edits in history order, with ownership guards and transactional rollback | Saved → Update features after source edits |
| Startup recovery | One fresh floating-palette retry if Fusion reports a broken native dock area (`pArea`) | Automatic on launch |

## What to prepare and try

1. **Attachment:** two separate root-level solid bodies with planar support faces.
   Face A supplies placement; Face B identifies the other target. An optional
   straight edge sets direction. Both generated mounting backs must intersect
   their own support, and the complete results must remain separate. Choose a
   small fixture first. [Placement examples](mechanical-pairs.md) give default
   mounting gaps. Create, change a dimension through Saved/Edit, then Delete;
   the original body identities should stay and Delete restores their geometry.
2. **Linked louvers:** no source geometry is needed. Start at the preset, try
   several vane angles, then choose Print layout. Print the separate frame,
   vanes and common link flat. This design requires external assembly fasteners;
   the independent captive-louver print trial remains a different option.
   [Assembly notes](linked-louvers.md).
3. **Parallel lift and swing hinge:** generate the preset before customizing.
   Each has eight printable parts and four external pivot fasteners. The lift
   retains a parallel mounting plate; the swing produces a rotating plate.
   Check the surrounding box/lid clearance in your own assembly before printing.
   [Lift](parallel-lift.md) · [Swing hinge](swing-hinge.md).
4. **Blower:** choose the radial blower, enable housing, then inspect the inlet,
   outlet, motor opening, radial/axial gaps and lid fasteners. The rotor is a
   separate body. Edit housing dimensions without changing the rotor; then test
   Saved/Delete. Start with a shaft-fit coupon. No rated speed, balance or airflow
   performance has been established. [Parameters](fans-and-propellers.md).
5. **Lid outline:** prepare two mating solids with facing planar outlines, enough
   floor material and a closed perimeter. Try a concave L or a smoothly curved
   outline. Native offsets preserve the selected curve geometry; collapsed or
   split offsets are rejected instead of silently changing the outline.
   [Lid requirements](small-details.md).
6. **Automatic updates:** make a new saved feature, finish the tool session and
   edit its upstream sketch/extrusion while Partelier stays open. Check the
   Saved message and geometry. Older features need one deliberate Rebuild to
   enroll. Ambiguous references or manually changed generated tools stop the
   automatic update. [Behavior and limits](automatic-updates.md).

## Efficiency and compatibility

Geometry is bounded, reusable preview meshes remain opaque and cached, and all
Fusion API operations stay on its main thread. Automatic updates use command
events and body revisions, without a timer or orbit-driven recomputation.
Attached edits update owned tools in place; they do not duplicate the original
source bodies. Prior exact recipes remain readable and migrate only after an
explicit successful Rebuild. No extra Python or web dependencies were added.

## Validation

All 1,195 Python tests and six Node UI suites pass, along with compilation and
whitespace checks. The previously missed Saved/Edit route for face details is
covered alongside the other new managers.

Native Fusion 2706.1.14 checks cover create/cache/edit/delete, body identity,
source restoration and sampled mechanism movement in disposable documents.
Separate print-layout checks cover the new multi-part assemblies. Motion tests
sample angles; they are not continuous swept-volume proof. The production
automatic service was exercised with a real external source-edit command.
Its second-operation conflict test confirms complete native rollback, retained
upstream edits and one attempt before pausing. Baseline renewal is mandatory
inside an automatic transaction; a failed save also aborts that transaction.
The `pArea` fallback was fault-injected against real native palettes, including
Close/reopen. Reports are in [validation](validation/).

Headless browser checks cover every tool at 300/320/380/520 px plus the mechanism
families and volute controls. Actual pointer use, printing and mechanical
performance remain the user's acceptance tests.
