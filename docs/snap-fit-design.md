# Snap-fit geometry and workflow

Partelier generates mating details on the same two selected root-component
bodies. Create integrates the male detail into A and cuts its receiver into B;
it adds no final bodies. Four mechanism families have separate geometry rather
than different names for the same hook. Dimensions describe the CAD shape; they
do not establish assembly force, strain, fatigue life or a printer-specific fit.

## Families

| Family | Generated mechanism | Sources |
| --- | --- | --- |
| Hook latch | An exterior cantilever with a flat retaining shoulder and inclined lead-in | Coplanar exterior walls and a straight seam |
| Ball detent | A rounded spherical nose on an exterior flexible beam and a matching bounded spherical socket | Coplanar exterior walls and a straight seam |
| Torsion latch | Two fixed posts, a round cross-bar and a central lever carrying a hook | Coplanar exterior walls and a straight seam |
| Annular ring | A continuous triangular bead around a cylindrical neck and a matching circumferential groove | Coaxial outside neck and inside socket faces, plus A's complete circular rim |

Hook latch has three variants: Straight keeps constant arm thickness, Tapered
reduces it to 65% at the free end, and Twin uses two parallel arms and hooks with
a shared root. Twin's middle gap is `max(thickness, 4 * clearance + 0.2 mm)`;
each arm uses half the remaining overall width. The receiving pockets remain
separate, with material between them. These variants belong to the hook family.

Ball detent uses the specified ball radius for the nose and radius plus
clearance for its socket. Engagement places part of the sphere behind the wall
plane, while another part overlaps its beam. It is a rounded detent, not a
material simulation or an automatic force-controlled release mechanism.

Torsion latch supports its Y-axis round bar in two posts attached to the root.
The central lever joins the bar rather than extending directly down to the
fixed root. The bar has an air gap above the root between its posts. Width,
lever thickness, radius and reach must leave positive clearances and keep the
catch above the bar; invalid combinations are refused.

## Planar-wall selection

Use a parametric Design, with the root active and history marker at the end.
For Hook latch, Ball detent or Torsion latch, select the exterior wall of A, a
coplanar wall of B with the same outward normal, and a complete straight facing
rim on either wall. A gap between the rims is supported. A pick on B maps to A's
real edge only when both complete projected spans match and the facing
boundaries are unambiguous. Partial, shifted, diagonal and far-side picks are
refused; A's actual edge is stored for Edit/Rebuild.

Local X points out of the wall, Y follows the rim and Z points from A toward B.
The adapter transforms detached copies before checking exterior-plane bounds,
so rotating the model does not change the source checks. Both bodies remain
behind the common exterior wall plane. Internal tongue-and-groove lips may cross
the seam when the actual sources and generated halves do not interfere.

Native intersection coverage checks the complete embedded root on A and the
receiver plus its remaining border/back wall on B. Family-specific shapes
supply their own receiver envelope. The free hook or detent is checked against
original A so an internal lip cannot attach it back to the fixed body. A checked
temporary difference must preserve the full final A volume after subtracting B;
a failed boolean is refused, rather than treated as proof of empty overlap.

## Annular selection and construction

Select an **outer cylindrical face on neck A**, an **inner cylindrical face on
socket B**, and a **complete circular rim belonging to that selected face A**.
A planar face, partial arc, B's rim, offset axis, or reversed mating-face normal
is refused. Axes must be coaxial, and B's inner radius must exceed A's outer
radius by a positive radial gap. Bead height must exceed that existing gap.

The frame origin is the center of A's rim. Its Z axis is oriented so A's neck
extends into negative local Z; bead offset is measured in that direction.
Radial X and circumferential Y complete a right-handed frame. Axial alignment
and the full-circle radius/length are checked independently of world orientation.

One continuous bead is built from two frustums meeting at the maximum radius.
Its exposed profile starts and ends at A's radius over the requested bead width.
Subtracting a cylinder at A's radius minus attachment overlap leaves a full-width
embedded ring root before it joins A. Changing attachment overlap does not reshape
the exposed bead. The groove radius is the
bead's maximum radius plus clearance, and its axial span includes clearance
above and below the bead. General exposed-edge chamfers are disabled for this
family; the bead already has sloping profile sides. Count must be one.

Exact annular intersection witnesses require A to contain the full ring root,
including its width and attachment depth. B must contain the complete groove
region, remaining radial wall, lower floor and upper extent around the entire
circumference. A partial shell, short socket or thin wall is refused. Neither
radius nor bead dimensions are resized automatically.

Print-friendly shape adds a 45-degree groove roof: the cut's outer radius
shrinks toward a radius inside B's bore as local Z increases. The lower groove
floor remains in place. With that setting off, the groove has a flat roof.
Both original and final pairs undergo positive-volume overlap checks.

## Outer finishing and print direction

For planar families, Print-friendly shape adds a 45-degree ramp below the
external root and a 45-degree receiver roof. These features assume **local +Z**
as the buildup direction; they do not inspect the slicer's bed orientation.
Ball detent uses a roof around its socket, while annular uses the radial groove
roof described above. Sloping bead sides depend on the chosen profile dimensions.

**Print-friendly shape** and **Chamfer edges** are separate settings. Chamfers
are derived from complete eligible convex edges of the **actual united generated
detail**, after its root, supports and male features have joined. Continuous
collinear segments with matching incident faces form one path. Finishing is
restricted to the exterior of the wall before the detail joins user body A.
It does not chamfer every edge of either source body.

Inward-facing beam surfaces and the retaining/contact shoulder are protected.
The entire detent sphere and torsion-bar core are preserved after finishing;
excluding curved edges alone would let a neighboring planar cutter nick them.
The receiving body B is identical with outer chamfers on or off for the same
family, dimensions and print-support setting: receiver entry edges are not
cosmetically beveled. Finishing must preserve complete inner/contact surface
trims and must not leave partial inside bevels or broken bands between old
construction pieces. Requested sizes are either applied to eligible exterior
edges or explicitly refused; they are not silently reduced. Curved family
profiles retain their own geometric rules, and unsupported finishing is refused.

The fixed native probe compares whole trimmed inner/catch surfaces and the
entire receiver against sharp baselines. It also samples requested outer bevel
sizes through root/arm/hook junctions and at the free tip. These checks establish
bounded CAD behavior, not physical print success.

## Dimensions and UI

The HTML form shows family-specific controls, with placement and construction
settings progressively disclosed. Picking happens directly in Fusion without a
second parameter panel. Every host update carries the complete typed settings
snapshot, even when some fields are hidden for the selected family.

| Setting | Default | Scope |
| --- | --- | --- |
| Width / thickness / reach | 8 / 1.5 / 16 mm | Planar mechanisms; torsion uses width as the bar span |
| Clearance | 0.3 mm | Mating gaps and receiver allowance |
| Engagement / lead-in | 1 / 3 mm | Hook or rounded-nose placement and hook ramp |
| Count | 1 | Planar repeats up to 20; annular requires one ring |
| Start / end margins | 5 / 5 mm | Planar rim ends to complete placement envelopes |
| Root length / overlap | 4 / 0.5 mm | Planar root; overlap also embeds the annular bead |
| Hook variant | Straight | Hook latch only: Straight, Tapered or Twin |
| Outer chamfer / size | On / 0.3 mm | Eligible planar-family outer detail edges; off for annular |
| Print-friendly shape | On | Local-direction root/receiver or annular roof changes |
| Ball radius | 2 mm | Ball detent nose |
| Torsion radius | 0.8 mm | Cross-bar radius |
| Annular bead width / height / offset | 2 / 0.5 / 3 mm | Ring dimensions and distance below A's rim |

Preview shows both full solids in their current Fusion appearances and leases
the originals' visibility. Cancel restores the exact prior light-bulb settings.
Camera movement does not dispose the graphics. A failed refresh retains the last
valid view, marked stale; Create requires a current successful preview.

Edit accepts an owned A/B body, face, edge, BaseFeature or a root Part containing
exactly one snap-fit. It restores all saved dimensions. Planar families can
reuse compatible planar sources. Annular keeps its cylindrical source contract;
Edit does not generically retarget a saved feature between those workflows.

## Persistence and recipe migration

`solid_pair.py` owns a two-tool BaseFeature and four native Combines
(Join/Intersect for A and B). Tools are consumed at the end of history. Create
modifies the same selected bodies; names, identity and visibility are preserved.
Rebuild updates the same two tool sources and retains the four Combine
references. It appends no result pair and stores no hidden source backups.

Create/Rebuild runs inside a zero-input native command transaction; a failure
requests rollback. Saved sources are read before the owned history block and
the previous marker is restored even on error. Ownership, contiguous native
history, native Combine definitions and output fingerprints are rechecked.
Later independent history is allowed; downstream edits changing a target are
refused. Another snap operation on already-owned targets is refused: use Count
or Edit/Rebuild. Upstream edits require explicit Rebuild.

Version 3 recipes store all **21** settings fields, including mechanism family
and its dimensions. Version 1's eleven-field recipes load as straight Hook latch
with chamfers and print support off. Version 2's fifteen-field recipes preserve
their saved hook variant/finishing settings and acquire the explicit Hook latch
family defaults. Reading either legacy format changes neither geometry nor the
stored recipe. A deliberate Rebuild writes the current version on the same
native history using the chosen settings.

CAD checks do not establish material strain, assembly force, fatigue life,
printing orientation or physical fit. Physical printing and assembly, manual
save/reopen and Undo/Redo remain separate acceptance work; no FEA or automatic
mechanical optimization is present. Native evidence and its exact scope belong
in [fusion-validation.md](fusion-validation.md).
