# Surface patterns

Version 0.9.0 adds one pattern workflow behind Honeycomb, Perforations and
Texture in the existing HTML palette. These entries start different presets of
the same tool. Hinge and snap-fit geometry remains locked at the user-approved
behavior.

Version 0.10.0 adds **Automatic** spacing and fixes distance checks against short
trim edges. A short edge beside a top cutout is measured as a finite segment,
not as an infinite supporting line that could exclude a whole column below it.
Curved trim boundaries use cached conservative strokes. Real outside borders
and existing holes remain protected.

## Use

Choose a shape (hexagons, circles, diamonds, squares or slots), then **Through
holes**, **Engrave** or **Emboss**. In 0.10.4, selecting one face immediately
starts preview. Use **Add face** for another face on the same solid, or **Faces**
to replace the selection. Esc cancels the current pick and keeps the previous
selection. Multiple preselected faces are reused. Start with **Layout > Balanced**,
**Cell size**, **Minimum gap** and **Border**. These names stay the same in all
layout and action modes. Through holes hide the unused **Depth / height** field.
Rotation, offsets and **Edge cells** live under Advanced.

Version **0.10.8** starts new patterns with a **12.5 mm Cell size**, **5 mm Minimum
gap**, **2 mm Border** and **Clip at border**. The local **?** dialogs explain
every field in Greek with an original SVG comparison; they do not request CAD
geometry or change settings. Close with Esc, the close button or a backdrop
click; focus returns to the help trigger.

**Balanced** preserves the requested Cell size and centers a sparse grid with a
soft limit of **48 cells per face**. It increases center spacing when needed,
so the gaps may exceed Minimum gap. Its preview reports the requested size and
approximate nominal grid gap; curved surfaces still undergo physical gap checks.
**Automatic size** uses the full bounded work budget and treats Cell size as a
target; the preview reports the resolved size (or range across faces).
**Fill face** preserves size and minimum gap.
**Exact pitch** retains the fixed-spacing algorithm for old whole-cell recipes;
with clipped cells it uses the same fixed-size centered lattice as Fill face.

For hexagons, size means opposite-flat distance; for circles diameter; squares
use side length; diamonds use the tip-to-tip diagonal; slots use total length.
Changing gap preserves the requested size in every UI layout mode. The existing
internal `pitch_mm` remains size + gap; it is not exposed as a changing user label.

**Clip at border** keeps partial hexagons, circles and other shapes where the
lattice crosses the border. Chart-space polygons are clipped to the inset face
bounds. Finite real trim boundaries, including notches and holes, are then
subtracted with conservative border envelopes. Closed convex trims use one
offset region rather than many overlapping edge capsules; other finite edges
use capsules and bounded convex decomposition. Pieces outside the real face are
removed; all retained boundary and midpoint witnesses must lie on the face and
preserve the physical border. Each original lattice cell is counted once even
when clipping splits it into several convex pieces.

A periodic cylinder seam is not an edge border. The grid wraps around it, with
at least the requested gap; cells can be clipped at its true end rims. Cell
size remains fixed in Balanced and Fill, while circumferential center spacing may increase
slightly to close the seam. Each selected face of a faceted solid is clipped
independently; there is no promise of continuity over a sharp ridge.

The border is a **minimum**, with small conservative numerical/stroke allowances.
General curved charts reserve additional metric clearance and may leave a wider
rim or refuse a distorted region. Extremely complex clipping refuses above 96
convex fragments per cell / 1,200 total fragments; it never silently falls back
to untrimmed cuts. Tiny numerically degenerate polygon pieces are omitted.
The lattice does not guarantee globally optimal packing or continuous material
removal at every point of the border: the gap between repetitions still remains.

**Whole cells only** is available under Edge cells. Saved v1/v2 recipes retain
this previous behavior on Edit; choose Clip at border and review Rebuild to
update them. The full work limits remain **200 cells per face / 400 total**,
shared by area for several faces. Dense fixed-size layouts refuse with a
larger-size estimate instead of silently enlarging the shapes.

The preview shows the complete proposed body with its existing Fusion
appearance. Create changes that same body. Edit accepts its body, face, edge or
owned feature, restores the saved settings, and Rebuild updates the same owned
history. Selection scope is fixed during Edit. Cancel removes the tool's own
preview and restores visibility.

Version 0.10.1 recovers lost preview acknowledgments and completion messages by
reading the current native session status while awaiting a preview. Status
queries run independently of the queued geometry actions. Recovery reuses the
computed result; it does not start another calculation or confirm Create.
Late responses cannot restore an obsolete loading state after completion.

Version 0.10.2 constructs convex cell prisms directly from closed shared BRep
topology, with full healing and analytic volume/winding guards. It avoids the
previous sequence of clipping a box separately against every polygon edge.
Planar face acceptance uses the trim-valid center and enclosing-disk clearance
from every finite boundary; curved faces retain the complete ring checks.
Identical Engrave wall rays are reused only when their normals match exactly.

Through tools remain individually bounded to the first material wall and
intersected with the original source. Eight or more disjoint tools can then be
combined on independent copies and applied in one Difference. Lump counts and
volume agreement establish that every tool contributes separate material;
failure or touching/overlap discards the aggregate and restarts the original
sequential path from pristine inputs. Engrave and Emboss retain sequential
application. Final results still require one solid and fresh source references.

Version 0.10.5 displays live sessions with one cached triangle mesh and one
bounded outline batch. The standard binary STL exporter supplies centimetre
coordinates at Medium refinement; only display data is approximated. Shallow
joins use angle-weighted smooth normals, while edges over 30 degrees stay sharp.
The source appearance is reused with an opaque display; textured UV mapping is
not reproduced by this display buffer.

Display capture briefly copies the result into one owned BaseFeature inside the
rollback compute command. Export options and body wrappers are released before
removing that feature. Temporary files are removed and no display history/body
remains after computation. Camera motion reads the cached graphics; it does not
request CAD geometry or another export. Create/Rebuild still uses the original
exact temporary BRep, never the display triangles. The direct native mesh
calculator used by the abandoned experiments is not accessed.

The display export is limited to 200,000 triangles. A refused display leaves the
last valid preview and its source visibility contract intact, without allowing
Create for the failed revision. Preparing an export adds a measured initial
cost; it does not eliminate the separate CAD preparation stage.

## Surface contract

Actual Fusion CAD examples from the passing native checks:

![Automatic honeycomb filling a panel below three top cutouts](images/patterns-balanced-panel.png)

The owned 300 × 170 mm notched-panel fixture produces 27 complete cells with a
41.81 mm fitted pitch from a 40 mm target. Opposite margins match: 4.90 mm at
the sides and 6.38 mm at the ends. Cuts occupy the left, middle and right below
the cutouts, while their real borders remain solid. This is an example, not a
promise of equal outer margins on arbitrary trimmed or curved faces.

![Automatic honeycomb wrapping a hollow cylinder](images/patterns-automatic-cylinder.png)

Automatic spacing also closes the cylinder seam with equal cyclic gaps. This
fixture has 52 cells at 7.73 mm from an 8 mm target; its end rims remain solid.

| Through holes on a cylinder | Raised hexagons on a cylinder |
| --- | --- |
| ![Cylinder with hexagonal through holes](images/patterns-full-wrap-through.png) | ![Cylinder with raised hexagons](images/patterns-full-wrap-emboss.png) |

| Circle engraving on a cone | Hexagon engraving on a sphere |
| --- | --- |
| ![Engraved circles following a cone](images/patterns-cone-engrave.png) | ![Engraved hexagons in a regular spherical band](images/patterns-sphere-engrave.png) |

- Plane charts use physical millimetres. Cylinders use arc length around the
  circumference. A full periodic cylinder distributes an integer number of
  columns without duplicate seam cells, increasing pitch slightly if necessary.
  Native U- or V-periodic faces are normalized to the same circumferential chart.
- Multiple selected faces may cover several sides of a hexagonal or other
  faceted body. Each face retains its border independently; rows are not claimed
  to continue seamlessly across a sharp ridge.
- Other smooth faces use a local surface chart. Singularities, strong distortion
  or excessive curvature are excluded or explicitly refused. This is not a
  guarantee of uniform geodesic spacing on every possible freeform surface.
  Native Automatic checks cover planes and cylinders; the positive cone/sphere
  examples use Exact pitch. Automatic can refuse a curved region when its local
  metric would reduce the requested physical web. Exact pitch is an alternative,
  subject to the same physical-web checks.
- New patterns clip partial cells at real borders, including trimmed holes.
  Whole cells only retains the previous conservative complete-cell behavior.
  A periodic seam is not treated as a border. Keep-solid masks are not included.
- Through holes stop after the first material wall along the cell direction.
  Parallel boundary/midpoint rays and a single connected intersection reject
  ambiguous re-entry into another wall. They are not unbounded cuts through the
  opposite side of a hollow object.
- Engrave/Emboss use native offset/thickness bands to follow the actual surface
  depth, intersected with each mapped cell. An offset or thickness failure is
  reported; the tool does not substitute a flat-depth cut.
- Whole-body selection includes all faces, including cavity faces. It can be
  refused when those faces lead to overlapping or unsupported operations. For a
  hollow container, select the intended exterior walls explicitly.

The current circle boundary is a 32-segment polygon; slots use a segmented
capsule. Full periodic wraps restrict rotation to lattice-preserving angles:
hexagons 60 degrees, squares/diamonds 90 degrees, slots 180 degrees. Circle
rotation is unrestricted. Nonperiodic faces allow arbitrary rotation.

## Limits and persistence

Pattern preparation enforces 100 selected faces, 200 cells per face and 400 total.
Automatic planning evaluates bounded candidate layouts and checks at most three
finalists against each native surface. Exact pitch retains the 4,000-candidate
limit and specific density refusals.
Sources must be native faces of one solid in the active root of a parametric
design, with the timeline at its end. Assembly proxies are not supported.

Small/rim faces without a complete fitting cell remain unchanged. An empty
overall result is refused. Curved circles are comparatively expensive: the
85-circle cone fixture took 24.78 seconds to prepare; the 36-hexagon full cylinder
took 0.85–2.31 seconds depending on operation. These are measured cases, not a
guarantee of instant live updates on dense geometry.

With the 0.10.2 path, the owned 195-cell notched-panel fixture prepares in
4.00 s versus 8.30 s before the changes; drawing/viewport refresh adds 1.85 s.
These are historical 0.10.2 measurements, not a universal speed guarantee.
Through geometry itself creates no timeline features. In 0.10.5, display capture
adds/removes its own scratch BaseFeature inside rollback; the final three owned
features still provide Edit/Rebuild support.

The full twelve-field settings snapshot is immutable and validated. Version 3
recipes add edge mode to the previous layout and selected face/body references.
Strict version 1 recipes (ten fields, Exact pitch) and version 2 (eleven fields)
remain readable with Whole cells only. Reading never rewrites their attributes;
only successful deliberate Rebuild saves version 3.
Source geometry and owned history are
checked before Create/Rebuild; a stale preview cannot be committed. Upstream
changes require an explicit Edit/Rebuild and missing/split face references may
require reselection.

One owned BaseFeature and two Combine features persist the full result while
preserving the selected body's identity, name and visibility. Rebuild replaces
that same tool source. No hidden source backups, dummy bodies or result copies
are added. Failed creation requires native command rollback.

Exact offset bands are copied into temporary geometry and their scratch native
features are removed in `finally`. Live computation runs in a separate
rollback-only native preview command, then draws the detached result after
rollback. Validation uses owned disposable fixtures and checks the user's model
again after the test command is destroyed.

CAD checks do not establish structural strength, waterproofing, slicer support,
material suitability or printability for a particular orientation. In
particular, a perforation shape does not automatically receive a print-oriented
roof/chamfer. Inspect the final orientation in the slicer.
