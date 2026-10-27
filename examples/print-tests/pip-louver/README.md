# Experimental print-in-place louver

Open **Partelier-PIP-louver-clearance.3mf** in Bambu Studio as one assembly with
nine parts. The STL is an alternative with the same positions and millimetres.
Keep their coordinates together: do not centre/arrange the individual parts.
The file is already oriented with every frame and blade touching Z=0.

Three small coupons are arranged from left to right:

| Printed marks on frame | Model clearance | Contents |
| --- | --- | --- |
| 1 notch | 0.25 mm | Frame + two captive blades |
| 2 notches | 0.35 mm | Frame + two captive blades |
| 3 notches | 0.45 mm | Frame + two captive blades |

The overall footprint is 132 × 26 mm and the height is 7.472 mm. Each frame is
40 × 26 mm. Pivots start on the bed as pointed diamond sections and turn inside
roofed sockets. The narrow bed opening is smaller than the pivot's minimum
width, retaining the blades without a floating socket floor. The blades print
upright and can be angled after removal from the bed. They have no detent,
linking bar, position lock or sealing function; this is a release/motion test,
not a finished adjustable register.

For an initial 0.4 mm nozzle trial, use a 0.2 mm layer profile and your calibrated
material settings. Keep supports and raft off. Keep brim out of the moving gaps;
an external frame-only brim can be used if needed. Inspect the slice to check
that the frame, pivots and two blades remain distinct. Do not scale the model:
scaling changes the clearances too.

Let it cool, remove it from the bed and gently try each blade. Record which of
the three clearances releases, turns freely and still feels acceptably retained.
Do not force a fused blade. The useful result is the clearance that works for
your printer/material/profile; the geometric check does not measure printing
shrinkage, friction, release force or durability.

Native Fusion validation checks nine connected solids, positive volume, bed
contact, downward-facing sides no steeper than 45°, and 156 sampled intersection
tests across −90° to +90° in 15° increments. Conservative swept-envelope spacing
between the blades is 3.858 mm. The exported meshes also have closed edge counts
and positive volumes. No physical print has been performed.

Source: `tools/fusion/PipLouverCoupon.py`. The generator owns a disposable Fusion
document and restores the caller unchanged. It is separate from the production
Grilles dropdown until a print validates the mechanism.
