# Mechanical pairs — experimental generated parts

This increment generates independent mating bodies, located at document origin
with optional XYZ offsets. It does **not** integrate into selected source bodies,
cut mounting pockets in an enclosure, or create assembly joints. The generated
pair can be deliberately positioned/attached later. Rebuild guards refuse later
external modifications; finish parameter changes before attaching the output.

| Family | Generated result | Limit |
| --- | --- | --- |
| Straight guide | Rail, open-bottom carriage, optional far stop | Travels along Y; carriage is 55% of rail length; can lift off |
| Dovetail guide | Retained sloped rail and matching clearance groove | Angle from vertical; insertion from the open end; no latch |
| Bayonet | Hollow male tube with radial lugs, sleeve with axial entry and circumferential slots | Shown engaged; reverse the turn to align entry slots; no spring detent or sealing |
| Clevis | Fork, tongue and separate pin | Z axis; one bounded fork geometry, no assembly joint |
| Barrel mounting hinge | Alternating knuckles, continuous leaves with cylindrical mounting tails, separate pin | Single axis; no mounting pockets are cut |
| Recessed single-axis hinge | Compact straight mounting leaves and knuckles, separate pin | Intended for deliberate recessed installation; not a hidden multi-link mechanism |
| Captive hinge print trial | Alternating knuckles with integral captive axle | Geometric prototype only; no support-free/45° or printed-release claim |
| Moving louver print trial | One frame and independently captured vanes, printed upright | Adapted from the earlier coupon; no linkage/register damper or physical release claim |

No geometry needs to be drawn first. Choose a family, set dimensions and click
New mechanism. Dimensions update the cached opaque preview. Create stores one
owned BaseFeature; Saved features provides Edit/Rebuild/Delete. Cancel and Close
discard the preview. Separate output never hides or replaces unrelated bodies.

Length follows the rail Y direction or hinge Z axis. Height means rail rise,
bayonet engagement, clevis height, or **outside barrel radius** depending on the
family. Clearance is per side; pin holes add twice clearance to the diameter.
Knuckle end gap equals the clearance. Bayonet coupling slots use angular and
axial clearance derived from the same value. No requested size is silently reduced.

Finite bounds, dovetail root material, bayonet slot spacing, fork back-wall and
pin-wall sizes are checked before native geometry. Preparation uses temporary
analytical cylinders, boxes and convex prisms. No persistent feature is created
for each part segment. Pairwise subtraction witnesses refuse volume loss, and every
output must be one solid lump. Cached mesh rendering avoids per-orbit geometry.

Local tests cover schema/layout/dimensional refusals. Native result evidence is
reported separately by the overnight validation runner. Physical print fit,
release, travel clearance under rotation, strength and wear remain for actual
tests. Captive hinge must be reviewed in the slicer and printed as a coupon before
any production or support-free claim.

## Sampled motion and moving louvers

The opt-in native fixture checks nine guide positions to the end stop, nine
bayonet twist positions followed by eight withdrawal positions, thirteen clevis
positions from -60 to +60 degrees, and thirteen hinge positions from 0 to 150
degrees. Every moving body is copied before transforming; subtraction witnesses
must retain its full volume. This is sampled geometry, not a continuous sweep.

Moving louvers reuse `tools/fusion/PipLouverCoupon.py` geometry: diamond pivots in
bed-open teardrop sockets, all parts touching the bed at local Z=0. Width and
count must reserve the complete rotating vane envelope; the bed opening must
remain narrower than the pivot's minimum caliper. The fixture rotates each vane
about its own X axis through -90 to +90 degrees in 15-degree steps and checks all
other bodies. It also checks every above-bed face against the coupon's 45-degree
underside normal bound. Actual printing, release and friction remain untested.
Vanes move independently; no linked register or sealing damper is supplied.
