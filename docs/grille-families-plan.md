# Grille families and print-in-place trial

The user's reference includes static grille faces and adjustable HVAC assemblies.
For Partelier, angle adjustment in the UI is the first delivery. A moving printed
louver is a separate experimental coupon, pending a real print before promotion
to the app. The existing flat back rests on the bed; retained geometry checks
limit downward-facing slopes to 45 degrees in that print frame.

1. Keep Linear bars, Standard crossed grid and fixed Louvers on their current
   geometry paths. Add Two-way deflection (opposed banks with a central rib) and
   Four-way diffuser (concentric rectangular apertures with diagonal supports).
   Reuse Opening width, Rib width, Border, Tilt, height/profile, fillet and optional
   screw mounting. Do not create duplicate cosmetic aliases for existing types.
2. Use bounded convex aperture plans and per-aperture direction vectors. Raised
   shapes share one perforated base and at most two supported loft segments,
   without a feature or Boolean per rib/corner. Preserve source identity and
   current Preview/Cancel/Edit/Delete history contracts; write recipe 13 with the
   same27 settings fields and read exact older versions without mutation.
3. Verify spacing, symmetry, borders, direction, overhang bounds and refusal
   cases locally, then native Create/Edit/Delete on disposable Fusion plates.
   Check the HTML controls and illustrations without adding another native panel.
4. Produce a small print-in-place louver coupon with retained pivots, a clearance
   ladder and a printable bed orientation. Validate solids, gaps and swept motion
   numerically/native, and supply the print file and instructions. Physical
   release/friction remain a user print test. A register requires a real moving
   damper; a static grille is not labelled an adjustable register.

Manufacturer references used for terminology: [Price linear bars](https://priceindustries.com/product/lbp-linear-bar/)
and [Titus adjustable double deflection](https://www.titus-hvac.com/products/Grilles/122RS).
These references are not airflow ratings or print validation for Partelier.

Delivered in 0.25.0: the two fixed families, recipe 13 compatibility, local/browser
checks, 11 disposable native cases and the three-clearance 3MF/STL coupon. The
remaining gate is a physical print, release and friction test. The moving
mechanism is deliberately not exposed as a production Grilles option yet.
