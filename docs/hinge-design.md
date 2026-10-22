# Separate pin hinge

## Status and supported case

Version 0.5.0 is experimental. Recipe 9 changes attached persistence: integrate
the hinge into the two selected root bodies and preserve their identity, name and
visibility. Only optional pins add final bodies. Rebuild updates owned tool
geometry rather than appending another pair of source/result solids.

Final native request `9a1e8b26-7909-4f1a-b43b-7fb1deec501b` on Fusion 2705.1.30
passes 53 expectations: 40 positive generated geometry cases, six explicit larger
fillet refusals, six in-place/migration cases and one actual production-session
workflow. Four attached treatments each pass four Rebuilds, retaining targets,
counts and history; legacy migration removes old owned copies and shows the
integrated originals. All 480 local Python tests and the Node DOM suite pass.

The native session uses programmatic selections in a rollback transaction.
Actual interactive picking, the complete CEF palette workflow, navigation,
save/reopen, Undo/Redo, motion and physical printing remain acceptance items.
New queued-preview/cancellation behavior is not established. Full source hashes,
fixture inputs and scoped evidence are in [fusion-validation.md](fusion-validation.md).
Historical 0.4.3 evidence below covers the previous copy-based implementation.

The first case requires a history-based Design, active root component and the
timeline marker at the end. Select two co-oriented, coplanar planar faces on
different single-solid root bodies, then a straight finite boundary edge of face
A. A coincident edge from body B resolves to the actual A boundary edge;
partial/offset segments, unrelated bodies and ambiguous matches are refused.
Occurrence proxies, assemblies and curved attachment faces are rejected.

The axis follows the selected edge and is offset toward face B outside split
mode. One or more separate hinges are distributed along the full reference
edge; their per-hinge length and end margins must fit it. Each attachment web must have
positive-volume overlap with its corresponding source body. Attached Create
joins the complete result into those same two bodies through owned native
features. It retains no separate source backups or duplicate final A/B solids.
Separate mode deliberately creates independent leaves and optional pins.

## Inputs and local geometry

All pure dimensions are mm. Native command expression values arrive in cm and
are converted once. The adapter converts mm points/dimensions back to cm for
Fusion operations. Defaults are examples, not machine/material fit advice.

| Field | Default | Meaning |
| --- | --- | --- |
| `length_mm` | 40 | Axial barrel span of each separate hinge |
| `hinge_count` | 1 | Separate hinges along the reference edge, integer 1 to 20 |
| `start_margin_mm` | 0 | Minimum start-edge to first barrel end distance; exact for 2+ hinges |
| `end_margin_mm` | 0 | Minimum last barrel end to end-edge distance; exact for 2+ hinges |
| `knuckle_count` | 5 | Per-hinge odd count from 3 to 15; A owns first and last |
| `barrel_diameter_mm` | 8 | Outside barrel diameter |
| `pin_diameter_mm` | 3 | Separate straight pin diameter |
| `diametral_clearance_mm` | 0.3 | Bore diameter minus pin diameter; radial gap is half |
| `axial_gap_mm` | 0.3 | Gap between adjacent knuckles |
| `rotation_clearance_mm` | 0.3 | Source/leaf relief around the housing envelope; separate from pin-bore fit; zero preserves legacy geometry |
| `leaf_reach_mm` | 12 | Reach from the axis into each source body |
| `leaf_thickness_mm` | 2 | Attachment web height above the selected plane |
| `web_profile` | tangent | Tapered support for attached/separate, round/square housings; flat retains the earlier web |
| `attachment_overlap_mm` | 0.5 | Attachment depth below that plane |
| `pin_overhang_mm` | 2 | Extension past each hinge end |
| `axis_offset_mm` | 4 | Edge-to-axis offset toward B in the selected plane |
| `include_pin` | true | Create the separate pin body |
| `split_seam` | false | Manual override; a full coincident A/B seam is also detected automatically |
| `seam_clearance_mm` | 0.3 | Total removed width across the verified mating interface, attached split mode only |
| `output_mode` | attached | `attached` modifies selected bodies; `separate` creates independent leaf pairs |
| `leaf_profile` | rectangular | Rectangular or two rounded free outer corners, separate mode only |
| `leaf_barrel_clearance_mm` | 0.3 | Separate plate starts this distance outside the barrel radius |
| `screw_holes` | false | Two through-holes per separate leaf |
| `screw_diameter_mm` | 3.2 | Through-hole diameter; no standard screw fit is implied |
| `screw_end_margin_mm` | 6 | Hole-center distance from each axial leaf end |
| `chamfer_edges` | false | General cosmetic edge finish on generated hinge geometry |
| `chamfer_size_mm` | 0.3 | Equal-distance 45-degree edge break when enabled |

The right-handed local frame has X from A toward B, Y along the hinge and Z
outward from the source faces. The base origin is the edge midpoint plus the
axis offset; the barrel centerline is at X=0, Z=barrel radius. The adapter flips
X and Y together when the reference edge orientation is reversed.

For length L, count N and axial gap G, each knuckle span is
`(L - (N - 1) * G) / N`. Spans alternate A/B over `[-L/2, L/2]`. Bore radius
is `(pin diameter + diametral clearance) / 2`.

### Distribution along the edge

`hinge_count` counts whole mechanisms; `knuckle_count` counts fingers within
one mechanism. For edge length E, margins S/T, count C >= 2 and per-hinge length
L, the equal barrel-to-barrel gap is `(E - S - T - C*L)/(C-1)`. The first barrel
starts at `-E/2 + S` and the last ends at `E/2 - T`. For C=1 the hinge is
centered in the interval remaining between the margins. Zero margins preserve
the original centered placement for one hinge. Start/end follow the effective
local Y direction; reversing the reference edge does not change the layout.
Swapping A/B can reverse this direction, so asymmetric margins should be checked
in the model preview.

Margins measure barrel ends, not pin tips. Pins extend by `pin_overhang_mm`
beyond each barrel end. The inter-hinge gap must be at least `axial_gap_mm`,
or `2*pin_overhang_mm + axial_gap_mm` when pins are enabled. Requests that do
not fit are refused before constructing temporary solids; dimensions are not
silently reduced. Each hinge adds its own pin; the attachment results remain
the same two selected solids carrying all of the mechanisms.

Example: on a 50 mm edge, three 10 mm hinges with 5 mm margins produce centers
at -15, 0 and +15 mm, equal 5 mm barrel gaps, and three separate 14 mm pins with
the default 2 mm overhang. This is a geometric layout example, not print-fit
validation.

Each flat web has the same Y interval as its knuckle and spans Z from negative
attachment overlap to positive leaf thickness. Its X extent is `[-reach, -R/2]`
for A or `[R/2, reach]` for B. Require reach > R and
`R * (1 - sqrt(3)/2) < leaf thickness < R - bore radius`: this ensures positive
barrel contact without filling the bore. These are geometric constraints, not
printer minimums. Non-finite, collapsed or overflowing requests are rejected.

## Tapered support from the user reference (recipe 7)

This section records the initial recipe 7 implementation and its historical
six-case probe. Current recipe 9 retains recipe 8 taper for both housing profiles and
output modes; separate tapers stay within leaf reach and protect the finished
hole lip. Movement clearance relieves temporary source/leaf copies around the
housing envelope and verifies a positive static gap. It is distinct from bore
clearance and is not a complete rotational sweep.

The user manually extended one knuckle in `parteliers test_v02.f3d` / STEP on
2026-10-21 and requested the same outline on the remaining fingers. The exported
reference was inspected read-only; it was not copied into the add-in. Its barrel
radius is 4 mm, old web upper outer corner is local (-12, 2) mm and its new
support meets the source plane near X=-15.660458 mm. The reference line is
approximately tangent to the circle, rather than a small cosmetic edge chamfer.

New attached round hinges default to **Tapered support**. The pure `support.py`
planner computes the exact upper/outside circle tangent through the existing
web upper outer corner, then extends it to the source plane and below that plane
by the existing attachment overlap. At the reference dimensions the exact
intercept is X=-15.659417 mm and tangent point is approximately
(-1.918331, 7.509987) mm. The derived slope is about 28.66 degrees to the selected
face; no fixed 45-degree overhang or printer direction is implied.

A triangular prism fills this outline and overlaps the barrel with positive
volume. It is mirrored for A/B and generated for every alternating knuckle in
every distributed hinge. The pin bore is cut after the union. The attachment's
source footprint extends beyond **Leaf reach**: reach/thickness locate the old
upper corner through which the tangent passes, not the new source-plane tip.
Positive attachment checks require a join; they do not establish complete
containment on an arbitrarily narrow selected face.

The initial recipe 7 advanced attachment dropdown could restore **Flat web**;
separate leaves and square housings then retained their existing webs. Current
recipe 9 retains that choice in all these modes. Versions 1-6 expand in memory to
flat webs and zero movement relief; version 7 retains its support choice with
zero movement relief. Merely opening or editing a saved recipe does not silently
change its shape. A successful deliberate rebuild now saves strict recipe 9.

The original recipe 7 adapter clips temporary boxes to make the prism. Its optional chamfers use
equal distances on the incident faces; fillets use an inset prism, face slabs,
edge cylinders and spherical corners. Finishes apply to the convex generated
primitive, with the existing limitation that concave source/barrel unions are
not subsequently blended. Requested collapsed finishes fail explicitly.

The standalone `tools/fusion/TangentSupportProbe` checks temporary geometry
without creating a document, feature, attribute or setting. On Fusion 2705.1.30,
embedded Python 3.14.0, all six native cases passed: five knuckles with sharp,
chamfered and filleted supports, each in identity and translated/rotated frames.
It verified positive source joins, bored knuckles and separation between the
halves, pin and adjacent knuckles. Active model snapshots before/after matched
(four bodies, seven timeline features). Local evidence is
`output/native/tangent-support-probe.json`; it is an ignored development artifact.
These historical checks validate those temporary kernel cases. Current
production-preview and saved-recipe Create/Rebuild evidence is recorded below;
document save/reopen and physical print/motion acceptance remain pending.

## HTML workflow and native selection

All dimensions, output choices, live preview, Create/Rebuild and Cancel live in the
local HTML palette. Basic placement and dimensions stay visible; fit, attachment
and mounting details are grouped disclosures. The normal workflow creates no
native selection dialog. Select geometry prompts for Face A, Face B and a
reference edge directly in the model. Esc stops the sequence, retaining previous
picks. Individual selection buttons let the user retry or replace a reference;
changing a face invalidates the captured axis edge. Edit prompts for a generated
hinge body or occurrence, then loads all saved dimensions into HTML.

The adapter calls the documented UserInterface.selectEntity from the palette's
HTML callback, never from a Command event. Picking waits for user completion or
Esc; no bridge timeout is applied to begin/focus actions. Native references stay
in Python. HTML accepts only plain state, a session UUID, a monotonic revision
and full validated dimension snapshots. Sharp preview uses temporary BRep/custom
graphics directly on the main thread. Finished preview uses a short zero-input
native compute Command: its preview transaction creates helper-owned copies,
detaches results and rolls back before graphics are drawn. It leaves no
persistent model changes or settings.

Create/Rebuild launches a zero-input native Command with isAutoExecute true.
Its execute handler re-reads/revalidates sources and current dimensions,
then persists results in Fusion's native transaction. No CommandInputs are added,
so Fusion need not display a command panel. A launch acknowledgement does not
mean Create succeeded; actual execute success is pushed back to HTML. Further
actions are blocked while commit is pending. The old native parameter dialog is
retained only as a compatibility path.

Plain parameter updates clear stale graphics without expensive kernel work on
every keystroke. The normal HTML flow now requests a debounced live preview
after valid edits, retaining the old view until replacement is drawn. Cancel/Stop/document deactivation release preview and native
references. Completed Fusion commands check source freshness; unchanged geometry keeps the temporary preview;
source picks remain available for revalidation. Failed command setup disables
auto-execution and releases its session; press Esc before retrying if Fusion
retains that failed command. Qt push response acknowledgements remain separate
from user actions. User-reported selection synchronization is confirmed. The
actual finished-preview runner, graphics cleanup and rollback have passed native
validation, as has a saved-recipe Create/Read/Edit/Rebuild path; broader manual
palette, Undo/Redo and document save/reopen acceptance remains pending.

## Housing profiles and fillet treatment (recipe 6)

The UI offers Classic, Soft, Linear, Compact and Piano presets. Only profile,
knuckle count, finish and leaf outline are preset; placement and nominal
dimensions remain user-controlled. Full settings are saved, not a preset name.
The two added appearance flags are mutually exclusive: chamfer_edges and
fillet_edges. Fillet radius defaults to 0.6 mm; legacy recipes read with fillets
off and their prior chamfer setting. Knuckle profile defaults to round.

For Linear, R=barrel_diameter_mm/2 is the circular envelope, not the square's
side width. Square half-side is R/sqrt(2), centered at local X=0,Z=R; its
corners remain inside radius R. Bore fit and contact height are checked against
the actual square wall/bottom before kernel work. Static body separation still
runs; a full rotational interference sweep is not implemented.

The original recipe 6 analytical implementation used exact inset-box-plus-sphere
sums for filleted boxes: three face slabs, twelve
cylinders and eight spherical corners. Cylinder ends use inset cores and tori
with major radius R-r and minor radius r. The nominal middle diameter, original
length and envelope remain unchanged. Bore/hole-entry cutters subtract a torus
from a short cylinder to produce a concave circular transition. All inputs and
results are temporary generated solids; positive bore-mouth removal is checked.
Original source bodies are excluded. Joined solids retain their concave
intersection; this is not a general rolling-ball blend across the final union.

For separate leaves, fillets apply to the rectangular outline and round all
corners/edges; the legacy two-free-corner rounded outline is a separate sharp /
chamfer option. Radius checks protect web contact, housing wall, pin middle,
leaf thickness and hole lips. Failed requested geometry is rejected rather than
silently left sharp. These primitive-finishing details are historical; the
current joined-body native adapter and its incomplete native acceptance are
described under Compound edge finish correction.

## Separate leaves and mounting holes

Separate mode still uses the selected faces/edge for placement and freshness,
but does not copy, cut or join source bodies. A shared edge centers the axis
without requiring a rectangular mating interface or making a seam cut. Each
placement produces its own A leaf, B leaf and optional separate pin.

The continuous plate spans local Z=0..leaf thickness, Y=-L/2..L/2 and
`abs(X)=R+leaf_barrel_clearance..leaf_reach`. It stays outside the opposite
barrel. Short webs exist only in their owner's alternating knuckle intervals;
they stop after positive overlap into the plate. Rounded style rounds only the
two free outer corners, leaving the barrel-side edge straight. Its radius is
`min(plate_width/4, L/8, leaf_thickness/2)`; it is geometry, not illustration-only.

Optional holes run normal to each plate. Two centers lie on the plate's width
midline at Y=`+/- (L/2 - screw_end_margin)`. Hole diameter, end/sides, spacing and
rounded-contour containment must leave positive material. The adapter checks a
positive volume reduction and one solid after drilling. It checks every pair
of generated bodies for static separation. These are geometric checks, not
screw compatibility, motion clearance, load rating or printability evidence.
Source mounting holes, countersinks/counterbores and the other hinge families
are separate specifications in [hinge-families.md](hinge-families.md).

Preview (0.5.2) uses CustomGraphicsAppearanceColorEffect with the actual A/B
body appearances for attached output. Generated separate leaves and pins use
the root component material appearance. No appearances are copied into the
document. Graphics explicitly override opacity to 1.0. Trimmed, nondegenerate
physical edges are stroked to 0.005 mm and batched into one black 1-pixel line
entity per body, avoiding material-tinted outlines. Plain Shaded style omits
the line batches. Periodic surface seams are excluded. All graphics remain
nonselectable and live in the existing preview group for atomic cleanup.
The preview draws the complete prepared result, including cuts and additions.
This follows body-level appearances; individual source-face overrides are not
mapped onto regenerated faces. Current-camera Steel - Satin rendering and
cleanup are verified; other material/style combinations remain visual checks.

## General chamfer finish

The user requested broad aesthetic finishing across hinge parts, extending beyond
print-in-place underside relief. **Edge finish > Chamfer exposed edges** enables
one size in mm for both attached and separate output. It is optional and off by
default. The finish targets generated hinge regions and does not bevel unrelated
edges of the selected source designs. A cosmetic finish does not create print-in-place retention or
validate an overhang in a chosen print direction.

The following describes the original recipe 5 primitive finish. Current
finishing occurs after the complete join, as described under Compound edge
finish correction.

Generated web edges and separate leaf perimeters receive bounded equal-distance
45-degree cuts. Rounded free corners retain their outline with quarter-conical
cap cuts. Barrel ends and bore entries receive conical edge breaks; pins have
beveled ends with their cylindrical fit diameter retained in the middle. Optional
screw through-holes receive the same small entry break. It is not a standard
screw-head countersink. Joined/embedded interface regions can be covered by the
subsequent unions; the operation is not a blanket native chamfer of every final
topological edge.

The pure `finish.py` planner builds cutters in mm. The adapter uses temporary
oriented boxes and cylinder/cone primitives before persistence, so Preview and
Cancel remain transient. It checks positive material removal, one solid after
cuts and the existing final separation guards. It never silently skips a finish
when the kernel cannot produce it. This historical primitive path does not
validate the current compound finish.

Validation requires the size to leave a barrel ring at both beveled surfaces,
straight pin/knuckle middles, plate thickness/width, web-to-barrel contact and
material around separate screw entries. Top/bottom leaf bevel insets are included
in the hole-mouth edge bounds. Overlarge requests are refused with an actionable
message. This verifies geometry constraints, not strength or printer fit.

Example for the default 40 mm hinge: enable the 0.3 mm finish. The barrel middle
keeps radius 4 mm, outside end radius becomes 3.7 mm, bore middle stays radius
1.65 mm and its entries flare to 1.95 mm. The pin middle remains diameter 3 mm
and its end flats are diameter 2.4 mm. End-to-end length and placement do not
change. These relationships require native measurement before acceptance.

## Touching split bodies

A complete coincident boundary on A and B automatically activates **Split seam
(touching parts)** for the reported block/lid scenario. The native checkbox and
status reflect the effective mode. It can also be selected explicitly. A
coincident candidate with unsupported topology is refused instead of silently
using the offset mode.
Select the two co-oriented, coplanar exterior faces and the common straight
boundary. For a box split horizontally, these may be the large front face of
the lower body and the narrow front strip of the lid, rather than the two
opposing internal cut faces. Either coincident visible seam edge can be picked.

This mode uses an effective axis offset of zero while retaining the saved
positive edge-offset value for the other mode. Each edge must have exactly one
matching adjacent planar rectangular mating face, with opposite normals along
local X, one loop, four straight edges and matching full corner extents. The
first implementation requires polyhedral sources with all vertices on their
respective side of the seam; curved/filleted or cross-plane sources are refused.
It is not an arbitrary split-body repair operation.

A pure `seam.py` plan describes a centered slab of width `seam_clearance_mm`.
It spans the entire mating face, beyond the hinge length if necessary and
through the full depth, with a small kernel margin at its ends. The adapter
subtracts that slab from temporary copies only. Each trimmed result must remain
one valid solid with a positive volume reduction; webs attach to the trimmed
copies. Final half/pin separation checks remain mandatory. Source geometry and
the saved recipe remain unchanged during Preview/Cancel. Full-result graphics
show the actual gap in the trimmed copies while a visibility lease temporarily
hides the current selected bodies. Cancel restores their captured visibility.
Successful attached Create applies the cleared final shape to those same bodies,
retaining their names and pre-commit visibility.

The separate [HingeSplitFixture](../tools/fusion/HingeSplitFixture/HingeSplitFixture.py)
script creates a new unsaved document matching this case: A is X[-25,25],
Y[-20,0], Z[-24,0] mm; B is the same X/Y with Z[0,6]. The fixture uses Part design intent to reproduce the reported Create failure.
Select exterior front faces Y=0 and their shared edge at Y=0,Z=0. Use clearance 0.3 mm,
length 40 mm and leaf reach 5.5 mm. Expected result seam positions are world
Z=-0.15/+0.15 mm through the entire 50 x 20 mm interface; the barrel axis is
world Y=4 mm,Z=0. Original volumes are 24000 and 6000 mm3. These expectations
still require native measurement, including a swapped A/B and reversed edge run.

## Reproducible fixture

Run the standalone script folder
[HingeFixture](../tools/fusion/HingeFixture/HingeFixture.py) through Fusion's
Scripts dialog. It creates a new unsaved parametric document, without modifying
the previously active document. Script execution itself remains unvalidated.

| Source | X bounds mm | Y bounds mm | Z bounds mm | Expected original volume |
| --- | --- | --- | --- | --- |
| Hinge fixture A | -24 to -4 | -25 to 25 | -4 to 0 | 4000 mm3 / 4 cm3 |
| Hinge fixture B | 4 to 24 | -25 to 25 | -4 to 0 | 4000 mm3 / 4 cm3 |

Select the top faces at Z=0, with matching outward +Z normals, then A's inner
50 mm edge at X=-4. Default offset 4 gives base origin (0,0,0) and barrel axis
(0,Y,4). Each knuckle is 7.76 mm; there are four 0.3 mm gaps. Pin endpoints are
Y=-22 and +22; bore diameter is 3.3 mm and radial clearance is 0.15 mm.

Default A webs overlap source A by 8 mm in X and 0.5 mm in Z; B is symmetric.
Web top Z=2 stays below bore bottom Z=2.35. Attached Create modifies the two
selected root bodies through an owned tool BaseFeature and native combines.
There are three final bodies with the pin, or exactly the original two bodies
when the pin is disabled. Their identities, names and original visibility are
preserved. Tool bodies consumed by the combines do not add duplicate final
A/B bodies. Separate leaves retain their independent Part/Hybrid result path.

## Preview and persistence

`prepare_hinge` builds copied temporary solids, unions barrel/web attachments and
cuts the bores. It verifies single solids, positive source overlap and static
separation between the halves and pin. Failed or ambiguous kernel/measurement
results reject creation. Temporary-body minimum-distance measurement and empty
Boolean behavior are explicit native acceptance risks.

Preview displays the complete candidate using Custom Graphics. It leaves no
persisted preview geometry or settings; finished previews use helper-owned model
objects only within the rollback transaction described above. Valid input changes
replace graphics after the candidate is ready. Invalid
changes keep the last valid preview with an explicit stale/error message;
Create is disabled until the current revision previews successfully. Cancel,
Destroy and Stop clear owned graphics/handlers. Create re-reads inputs and sources rather than accepting the
cached display as proof. Attached persistence uses an owned root tool BaseFeature
with complete final A/B shapes and optional pins. For each selected target, native
Join keeps its tool, then native Intersect consumes that tool and leaves the
same target at the final desired shape. Record and verify the resulting target
handles, names, visibility, counts and exact owned feature chain. Separate output
uses one owned root BaseFeature in Part Designs or an owned component/BaseFeature
in Hybrid Designs. Document intent is never changed.

A session-owned visibility lease hides the current attached targets and, during
legacy Edit, only the validated old owned result. Separate output leaves source
visibility unchanged. Repicking reveals leased bodies and hides graphics;
finishing the pick restores the candidate view. Accepted output-mode changes
transfer the lease. Cancel, failed creation and Stop restore captured preview
flags; failed restores remain owned and reported for retry. Successful attached
commits preserve the targets' prior visibility. There are no committed hidden
backup bodies to manage.

Version 9 attributes store the logical feature UUID, validated dimensions, source
references, target identities and exact tool/feature ownership. Resolve tokens
through the Design rather than comparing strings. Missing, split, modified or
ambiguous references and unknown recipes are refused. Clean partial owned output
on failure; incomplete cleanup reports the need to undo the command.

New results use Partelier's ownership namespace. The rename preserves the tool
ID, and a strict read-only alias accepts earlier ownership namespaces. Version 1
recipes require their exact prior settings schema and expand in memory to split
mode off with default seam clearance. Version 2 requires its exact split-seam schema. Both old versions expand in
memory to one hinge with zero margins. Version 3 requires its exact distribution schema. Versions 1–3 default the new
output/profile/hole fields in memory to attached output. Version 4 stores the leaf/output fields and requires its exact schema. Versions
1–4 expand finish settings to off / 0.3 mm in memory. Version 5 stores the finish
choice and size. Version 6 adds housing profile and fillet choice/radius, reads
v1–v5 with round profile and fillets off, and verifies result roles against
output mode and count. Version 7 adds support shape. Version 8 adds movement
clearance; versions 1-6 read with flat webs/zero relief and version 7 with its
support shape/zero relief. Version 9 changes attached persistence and requires
its complete schema.
Part recipes live on the owned BaseFeature; Hybrid recipes remain on the
generated component. Root component attributes are never used for ownership.
Opening a saved hinge or previewing it does not migrate attributes. A successful
Edit/Rebuild saves the updated owned recipe under the Partelier namespace; failure
preserves the prior result. Native save/reopen acceptance remains pending.

## Manual Edit and Rebuild

Edit existing selects the hinge-bearing attached body or the independent owned
leaf/occurrence and loads its saved parameters into HTML. Source selections stay
those of the recipe; changing source selections requires a new hinge.

For version 9 attached output, evaluate source references at the history position
before the owned tool BaseFeature. Prepare new complete final shapes, update the
owned tool sourceBodies with `BaseFeature.updateBody`, then let the existing
native combines recompute. Repeated Rebuild must retain target identity/name/
visibility and must not append bodies or features. These stored full-shape tools
require explicit Rebuild after upstream geometry changes; no fully automatic
regeneration or persistent downstream face identity is promised.

Earlier attached recipes created owned copies and may leave hidden original
sources. A deliberate successful Rebuild may migrate them to version 9 only after
strict ownership/signature, topology, safe-deletion and native/logical dependency
checks. Integrate the original targets, remove only the old owned copy output,
and show the intended integrated targets. Never delete unrelated or merely
hidden bodies. Refuse unsafe or ambiguous migration before destructive changes;
failure must keep the prior valid result and recipe.

Separate-leaf Rebuild retains its prepare-replacement-before-retirement contract.
Earlier independent Part Design output is permitted only when its ownership and
dependency checks allow it. Separate Hybrid output retains its last-feature
restriction. The timeline marker must be at the end. Moved/shared occurrences,
modified owned geometry, added owned-component content and unsupported source
changes remain explicit errors. Native save/reopen and Undo/Redo acceptance is
still required.

## Acceptance and evidence

The checklist below retains the broader acceptance scope; it is not an
all-passed record. Completed native evidence and explicit finish limitations are
recorded under Compound edge finish correction and in fusion-validation.md.
Record Fusion build, embedded Python, Windows/hardware, exact inputs and observed
outcomes. A mock passing a branch is not a native geometry result.

| Check | Expected observation |
| --- | --- |
| Fixture script | New document; two original solids with exact bounds/volumes |
| Default preview | Complete result and alternating knuckles; scoped source/result hiding; no preview timeline/bodies/attributes survive cleanup |
| Touching split preview/Create | Coincident A/B pick accepted; centered axis; full-result positive gap applied to the same two selected bodies |
| Unsupported split topology | Actionable refusal; no source cut or persistent result |
| Version 1 Edit/Rebuild | Legacy dimensions load with split off, flat webs and zero movement relief; safe successful migration writes version 9 |
| Invalid face/edge/length/gap | Actionable error; no persisted output |
| Default attached Create | Original A/B identities, names and visibility retained; owned tool/combine features; only optional pin increases final body count |
| Three-hinge layout | 50 mm edge, length 10, count 3, margins 5: centers -15/0/+15, barrel gaps 5, two result halves plus three pins |
| Separate rectangular/rounded | Each placement owns A/B leaves and optional pin; rounded outer corners remain curved after webs; sources untouched |
| General edge finish | Equal 0.3 mm bevels on supported generated edges; nominal middle diameters/lengths and unrelated source edges retained |
| Separate holes | Exactly two open through-holes per leaf with requested diameter/end offset; invalid fits refused |
| HTML Preview/Create/Cancel | Parameter changes and selection sync; Preview transient; actual execute confirmation; cancelled session cannot create |
| Impossible layout | Actionable fit error before temporary solid creation |
| Attached Edit/cleanup | Owned tool sourceBodies updated, combines recompute, target identities/counts retained; unsafe legacy migration refused; unrelated objects preserved |
| No pin | Exactly the original two selected bodies, now hinge-bearing |
| Bore/attachment/gaps | Open 3.3 mm bores, connected webs, 0.3 mm axial gaps, positive static separation |
| Reversed edge | Equivalent placement and ownership |
| Cancel/Stop/repeated preview | No owned graphics/handler growth or persisted preview state |
| Failure/Undo/Redo | No orphaned owned tools/results; target shape/count/name/visibility restored on failure/Undo; unrelated objects preserved |
| Save/reopen/Edit | Same recipe dimensions resolve to original source identities |
| Rebuild failure | Previous valid result retained, replacement cleaned |
| Modified or downstream-dependent result | Rebuild refused before replacement/deletion |

Aggregate native timings are logged for source reading, planning, temporary
geometry, drawing and persistence. Cached previews do not repeat the work. No
native speed baseline or response-time claim exists yet. Static checks do not
validate a rotational motion sweep, pin retention, durability or print success.

## Orbit-safe live preview (0.4.1)

The user reported that the first orbit gesture removed the preview and changing
style restored it. The commandStarting cleanup deleted graphics for navigation.
The palette now validates a source-only snapshot at commandTerminated. Unchanged
source geometry keeps the same graphics/revision, without preparing BRep again.
Changed or unreadable sources clear the stale preview and disable Create until
refresh/reselection succeeds. Own Create/Edit/picking callbacks avoid reentrant
checks. Cancel, document deactivation and Stop keep their cleanup behavior.
The snapshot retains no generated temporary output bodies.

The basic field now says Barrel diameter; barrel_diameter_mm remains the stored
parameter (default8 mm), so radius is half the value (default4 mm). No redundant
radius field or recipe change was added. Local regression checks cover camera
commands including unknown IDs, cancelled/nonmutating commands, source changes,
read failures, refresh recovery, cleanup and no geometry rebuild during navigation.
Native orbit/pan/zoom in the reloaded palette remains pending. The prior 0.4.0
32-case geometry probe did not validate compound finishing; the subsequent
script-driven native results are recorded below.

## Historical compound edge finish correction (0.4.3)

The user observed cylinder chamfers/grooves at support intersections. Native
join checks alone were insufficient: separately finished primitives could form
one solid while retaining a real finish valley at a buried edge. The 0.4.3 runtime
built raw supports/housings, joins them into the complete source/leaf copy,
and cuts holes before finishing.
[native_finish.py](../Partelier/partelier/tools/hinge/native_finish.py) selects
convex sharp edges on that compound body, skipping tangent seams and concave
junctions. Attached finishing is confined to the generated region above the
source plane. Cap edge sets explicitly disable automatic tangent-chain
expansion, which could otherwise cross into rounded-leaf side edges. Later side
stages match frozen original analytic curve supports and never target newly
created blend borders.

Native chamfer/fillet features run on helper-owned copies; results are detached
before only those helper features are removed. Separate tapered necks use 85%
of the available hole-safe span, preserving the finished screw-hole lip without
changing requested hole or finish dimensions. Unsupported or failed finishes
are reported rather than silently substituting another shape.

[roof_finish.py](../Partelier/partelier/tools/hinge/roof_finish.py) is a read-only
C1 contour guard for round/tapered fillets. It checks mirrored roof and cylinder
cap witnesses where raw containment establishes the intended surface. A
detected valley is refused. Success returns the same unmodified solid; no
material is filled, no radius is reduced and no alternate finish is applied.
An unproven roof-completion approach was discarded. These sampled checks are
bounded evidence, not a proof of every point on the complete solid.

For the HTML palette,
[native_preview.py](../Partelier/partelier/tools/hinge/native_preview.py) queues a
short zero-input command. Its executePreview computes detached solids,
explicitly leaves isValidResult false, and a no-op execute rolls the preview
transaction back. Graphics are drawn only after command destruction; stale,
cancelled or stopped requests are discarded. Create/Edit use the same native
finishing adapter inside their native transaction. Sharp previews retain the
transient fast path. Existing saved results remain unchanged until a deliberate
Edit/Rebuild; the 0.4.3 recipe schema remained version 8.

Final native request `3902166f-b114-4da6-b55b-a6a4cb445bea` passes on Fusion
2705.1.30 / Python 3.14.0. All 47 case expectations pass: 40 positive generated
cases, six explicit 0.6 mm fillet refusals and one saved-workflow case. Positive
chamfers are 0.3 mm; fillets are 0.6 mm for attached round/tapered, 0.2 mm for
separate round/tapered and round/flat, and 0.4 mm for square housings. Rounded
leaves use chamfers. Refusals remain limits, with no refill or automatic reduction.

The saved case starts with two 40 mm hinges and 11 mm margins. Actual sessions
preview five then three knuckles and length 40 then 36 mm in Edit, Cancel, then
five and three knuckles in New before Cancel. A real commit stores the edited
36 mm length and hides two source backups. An earlier independent Part Design
root result rebuilds without changing the later fixture's recipe, geometry or
counts; a forged logical dependency is refused before replacement creation.

The actual preview runner/graphics/rollback checks pass without runtime errors.
The additional finish completed before Cancel; drained cleanup is confirmed,
rather than interruption of an executing kernel operation. The six original
user bodies, topology, history and visibility match after rollback and explicit
fixture cleanup. The 461 local Python tests, Node DOM race/session tests and
compilation also pass. Actual interactive picking, complete palette acceptance,
Undo/Redo, save/reopen, motion and physical printing remain outstanding. See
[fusion-validation.md](fusion-validation.md) for full inputs and historical
0.4.2 evidence; the former three-hinge 0.8 mm chamfer case differs from the
historical 0.4.3 saved fixture. Neither report validates version 9 persistence.

The host returns `False` from custom-event queue calls whose handlers actually
run. The preview runner relies on actual delivery and API exceptions rather
than treating that boolean alone as failure. Registration/event-ID guards and
explicit exception diagnostics remain. The earlier primitive-finishing probes
did not test absence of these valleys and do not replace the current evidence.
