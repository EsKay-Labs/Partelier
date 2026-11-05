# Knurling for knobs

Dedicated knob grips live separately from the older Surface patterns → Grip
texture preset. Select one complete **external cylindrical face** on an existing
solid knob in a root, history-enabled Fusion design. The tool removes material
inside the original diameter; it does not add a second knob or change the bore.

Available styles: Diamond, Straight V grooves, Helical, Chevron, Waves, Rounded
flutes, Scallops, Dimples, Pyramids and Rings. The angle control appears only for
angled styles; rotating Rings is irrelevant and is hidden.

## Workflow

1. Create the knob cylinder and any shaft bore first.
2. Open Knob knurling, choose a style and inspect its illustrated `?` help.
3. Select the outside cylinder. The entire height of this cylindrical face is
   used, with untextured borders at both ends.
4. Adjust spacing and depth, review the opaque preview, then Create.
5. Use the section's Saved features to Edit or Delete the owned operation.

Preview and Cancel leave the design unchanged. Edit rebuilds the owned cutting
tool and retains the original source body. As with the other attached tools,
editing earlier features is subject to ownership and timeline guards.

## Printing orientation and geometry

Print with the **cylinder axis perpendicular to the bed**, standing on either
flat end. The relief and its end transitions are checked against a maximum
45-degree slope from that axis. Turning the part onto its side invalidates this
assumption. This check applies to the new grip surface, not to other geometry
already present on the knob.

Defaults are 6 mm target pitch, 0.6 mm maximum cutting depth and 1 mm solid end
borders. The integer repetition count fits the full circumference without an
open seam. The actual pitch is shown by the planner; target spacing is not an
exact count request. Incompatible depth, spacing or available height is refused
instead of silently reducing the requested depth.

The native relief uses a bounded faceted solid. The nominal circular ring's
circumscription excess is limited to 0.04 mm; this is not a tolerance on the whole
groove waveform. Circumscribed border rings protect the original smooth cylinder.
Exact curved surface styling is not claimed. Geometry has a bounded
face budget: excessively dense requests ask for a larger pitch rather than
creating thousands of native features or unbounded computation.

A complete annular material check requires the relief depth plus 0.8 mm of
continuous material beneath the selected cylindrical surface. A bore is allowed
when enough wall remains; intersecting openings and thin walls are refused.
Other material immediately outside the selected cylinder is also checked: the
0.1 mm outer carrier used to connect cutters may not remove adjacent features.

The 45-degree criterion is a conservative design constraint, not a guarantee
of grip, strength or successful printing on every machine. Actual overhang
quality depends on the printer, material, cooling and layer settings; see
[Prusa's design guidance](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135).

## Runtime contract

The strict six-field KnurlSettings record belongs to `tools/knurl`; saved recipes
start at version 1. Alias `knurling` has its own Saved section and does not change
older `knurl` pattern records. Pure geometry planning is independent of Fusion;
native temporary geometry, source validation and persistence remain on the main
thread. Preview draws a cached opaque lit mesh. It never draws custom-graphics
BRep bodies or scans geometry during orbit.

`tools/fusion/KnurlValidation.py` runs one bounded fixture per invocation in a
disposable document and restores the caller. Local planner tests and native
validation are reported separately; physical print acceptance remains pending.

## Validation in Fusion

All ten styles passed temporary preview, same-body Create/Rebuild and Delete
restoring the source. Additional cases cover a hollow knob, refusal of thin
walls and nearby outside material, and a Ø30 × 20 mm diamond knob. Its measured
preparation was about0.49s and Create about1.57s on the test machine. Registered
command tests cover preview cancellation, invalid-dimension recovery without
repicking, Create, Saved Edit cancellation and deletion. The caller document
and camera were restored. The final source passes1,243 Python tests and8 Node
UI suites; the Windows installer passed isolated install/upgrade/uninstall.
See [native evidence](validation/knurling-0.33.0.json).
