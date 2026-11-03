# Offset four-bar hinge

This experimental assembly gives a swinging output plate. Two unequal arms connect
a fixed plate to a shorter rotating mounting plate. The output rotates 0–90 degrees
and translates outward. It is a mechanism building block, not a drop-in European
cup hinge or a verified cabinet installation. Surrounding door/frame collision is
not evaluated.

Select Mechanical pairs → Offset four-bar hinge. Hinge opening is the actual
rotation of the moving plate relative to its closed pose. The default short arm
is 30 mm, fixed pivot spacing 40 mm, and plate width 16 mm. Coupler and long arm
lengths are fixed ratios (2/3 and 7/6 of the short arm). Custom arm length and pivot
spacing must retain the complete monotonic 90-degree branch; invalid proportions
are refused. No scaling or angle clamping happens silently.

The solver uses circle intersections and bisection of a bounded crank interval.
The four link lengths remain constant. Assembled output contains eight parts:
fixed plate, rotating plate, two arms and four spacer collars. Arms occupy separate
axial planes, with collars at the four pivots. Mounting holes are provided between
the pivot holes of both plates. Source bodies are unchanged.

Use Assembly layout → Print layout to lay every broad back on the bed. Assemble
with four external shoulder screws/pins and retainers through the aligned pivot
holes; choose their lengths from the actual stack. Do not clamp the moving links
with ordinary screw threads. Mount both plates using their additional holes.
There are no generated Fusion revolute joints or animation constraints.

Native validation passed eight solids, 19 poses from 0 to 90 degrees, all 28 body
pairs per pose (532 checks), invariant link lengths and actual output rotation.
The flat print layout passed bed contact and a 45-degree underside face normal
bound over 44 faces. See `tools/fusion/SwingHingeValidation.py` and
[native report](validation/swing-hinge-0.29.0.json). The common mechanism fixture also passed cached
preview, Create, saved recipe read and Rebuild for all eleven families.

This is discrete geometry evidence, not a continuous sweep, physical print/fit
test, strength rating, or surrounding cabinetry check. Unlike Parallel lift, this
family rotates its mounting plate; the existing recessed single-axis hinge remains
a separate option.
