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
**Target cell size**, **Minimum gap** and **Solid border**. Through holes do not
use a depth setting. Rotation and offsets live under Advanced.

Version **0.10.6** adds a **? beside every pattern setting**, including the new
cell-size control. Each opens a local dialog with a Greek explanation and an
original SVG comparison image; no CAD request, geometry computation or setting
change is performed. Esc, the close button or a backdrop click closes it and
returns focus to its trigger. The drawings explain settings; they are not model
previews.

**Balanced** is the new default. It starts with a 12.5 mm target cell size,
1.5 mm minimum gap and 2 mm solid border. It centers the grid and adjusts one
uniform cell size per face to fit within a soft limit of **48 cells per face**,
instead of using the full 200-cell work budget. The requested target remains
unchanged; the preview reports the actual fitted dimensions. Small faces may
need smaller cells, and large faces normally receive larger ones.

**Fill face · fixed size** repeats whole cells across the available surface at
the specified **Cell size** and at least the **Minimum gap**. For hexagons, size
is the distance between opposite flats; for circles it is the diameter; squares
use side length, diamonds use the tip-to-tip diagonal and slots use total length.
Changing Minimum gap in these two new modes preserves the requested cell size.
Internally the existing strict snapshot still stores `pitch_mm = size + gap`;
there is no extra persisted field or recipe migration.

Fill does not shrink cells, cut partial cells at borders, or silently drop rows
to satisfy the work budget. It tries the centered lattice phases, respecting
finite face trims and the existing surface checks. The solid border is a minimum:
whole cells and conservative curved-surface checks can leave larger margins.
This is bounded lattice placement, not a guarantee of globally optimal packing.
On a full periodic cylinder, circumferential center spacing may increase to
close the seam; opening size stays fixed and minimum gap is never narrowed.

The hard limits remain **200 cells per face / 400 total**. A dense Fill request
refuses with a larger-cell-size estimate or suggests Balanced; it never silently
changes the requested size. With more than two faces, the total work budget is
shared by area. Unsupported surfaces or insufficient actual mapped web still
refuse rather than changing the model.

**Automatic size** retains the previous automatic fit algorithm (up to the full
work budget), with Target pitch and solid web. **Exact pitch** retains the earlier
fixed lattice. Stored v2 recipes keep their saved mode and full dimensions;
pre-layout v1 recipes still load as Exact pitch. Edit/Rebuild does not adopt the
new defaults unless the user changes their settings deliberately.

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
- Cells remain complete. Cells too close to a real boundary or a trimmed hole
  are omitted conservatively. A periodic surface seam is not treated as an edge
  border. There are no clipped partial cells or keep-solid masks in this version.
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

The full eleven-field settings snapshot is immutable and validated. Version 2
recipes include the spacing mode and selected face/body references. Strict
version 1 recipes with ten fields remain readable as Exact pitch; reading never
rewrites their attributes. Only successful deliberate Rebuild saves version 2.
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
