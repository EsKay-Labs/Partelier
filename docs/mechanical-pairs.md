# Mechanical pairs — experimental generated parts

Choose **Separate mating parts** at document origin or **Attach to two existing
bodies**. Attached mode preserves both selected source bodies, names and visibility;
only a separate pin adds an output body. It does not create assembly joints or
silently cut away source material to make room. Moving louver assemblies remain
separate outputs. Rebuild guards retain exact feature/tool ownership.

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
| Linked adjustable register | Split frame, vanes with crank eyes, common translating link | Assembled/flat print layouts; external fasteners required, not print-in-place |
| Parallel-lift linkage | Fixed/moving mounting plates, two equal arms and four spacer collars | Moving plate stays parallel; external joint fasteners; not a swinging concealed hinge |

Separate mode needs no starting geometry. Attached mode needs two existing solids
with planar mounting faces. Choose a family, set dimensions and click New mechanism.
Dimensions update the cached opaque preview. Saved features provides Edit/Rebuild/
Delete. Cancel and Close discard the preview and restore hidden source visibility.

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

The separate **Linked adjustable register** adds a true common link and crank
eyes; its fastener-based assembly and print layout are described in
[Linked louvers](linked-louvers.md). It is a separate family from the captive
print trial above.

The **Parallel-lift linkage** is a separate true four-bar mechanism. Its visible
Arm length, Pivot spacing and Lift angle controls preserve parallel mounting
plates. See [Parallel lift](parallel-lift.md) for hardware, assembled/flat printing
layouts and sampled native verification. It is deliberately not labelled a
concealed door hinge.

## Attachment and reference placement

1. Select **Attach to two existing bodies**, then New mechanism. Pick planar Face A;
   selection advances to Face B on the other body. Esc clears both references.
2. Face A defines the mounting plane and its projected boundary-box centre. The
   longest straight boundary edge defines in-plane direction; optionally choose
   another straight **Direction edge** on Face A. Circular faces use a stable
   world-axis-derived direction. Placement angle rotates within that plane.
3. Sliders sit on Face A with their base embedded by Attachment overlap. Their
   travel runs along the local Y direction. Clevis and hinge mounting backs embed
   into Face A; their axis follows local in-plane Y. Bayonet male starts at A's
   support plane, with its axis normal to A.
4. Face B identifies the second source body. Both generated parts must overlap
   their own source by positive volume, and the complete two resulting bodies
   must not overlap one another. Adjust dimensions or local XYZ placement if B
   does not meet its mounting part. A touching face alone does not count as a join.
   There is no implicit source cutting, forced gap change or automatic scaling.

For opposing slider supports, the default mounting gap is
`2 × wall + height + clearance − 2 × attachment overlap` (11.3 mm initially).
For opposed clevis supports it is `length − 2 × overlap` (39 mm initially).
Hinge mounting-back gap is `2 × (barrel radius + leaf reach) − 2 × overlap`
(51 mm initially). These are fixture examples, not requirements for every source
shape. Bayonet attachment needs separate annular support regions that leave the
opposite sleeve/tube clear; a full solid plate can obstruct the other part.

Attached persistence owns one BaseFeature containing the generated tools and two
consuming Join features. Rebuild reads source faces **before** that owned history,
updates only the owned tool source bodies and retains the same targets. Optional
pins remain separate. Delete removes only that owned operation and restores the
source geometry. Saved attached family/output mode cannot change during Edit.

Recipe 2 adds the exact attachment/reference mapping and four new settings.
Exact recipe-1 separate results load unchanged, injecting defaults in memory only;
an explicit successful Rebuild saves recipe 2. No saved recipe migrates on listing.
Automatic update authority is scoped by `refresh_context`; it can bypass only the
stale result fingerprint after an upstream source change. Tool ownership, native
Join definitions and source clearance guards remain mandatory.

Native attachment fixture: `tools/fusion/AttachedMechanismValidation.py`. It checks
seven families with Preview/Create/Edit and exact-owned Delete, including retained
body tokens/names and restoration of the original source volumes. Report results
separately from actual pointer use, movement of attached source shapes and printing.

The **Offset four-bar hinge** supplies a rotating output through 90 degrees,
using unequal links and external shoulder screws. Its separate assembly and flat
print layout are described in [Swing hinge](swing-hinge.md). This complements the
parallel lift and the recessed single-axis family.
