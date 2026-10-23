# Surface patterns

Version 0.9.0 adds one pattern workflow behind Honeycomb, Perforations and
Texture in the existing HTML palette. These entries start different presets of
the same tool. Hinge and snap-fit geometry remains locked at the user-approved
behavior.

## Use

Choose a shape (hexagons, circles, diamonds, squares or slots), then **Through
holes**, **Engrave** or **Emboss**. Select faces on one solid and press Esc when
finished picking. Preselected faces are reused. Start with pitch, solid web (gap
for emboss), border and depth/height. Through holes do not use a depth setting.
Rotation and offsets live under Advanced.

The preview shows the complete proposed body with its existing Fusion
appearance. Create changes that same body. Edit accepts its body, face, edge or
owned feature, restores the saved settings, and Rebuild updates the same owned
history. Selection scope is fixed during Edit. Cancel removes the tool's own
preview and restores visibility.

## Surface contract

Actual Fusion CAD examples from the passing native checks:

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

Pattern preparation enforces 100 selected faces, 200 cells per face, 400 total and 4,000 layout
candidates. Smaller pitch or excessive density produces a specific refusal.
Sources must be native faces of one solid in the active root of a parametric
design, with the timeline at its end. Assembly proxies are not supported.

Small/rim faces without a complete fitting cell remain unchanged. An empty
overall result is refused. Curved circles are comparatively expensive: the
85-circle cone fixture took 24.78 seconds to prepare; the 36-hexagon full cylinder
took 0.85–2.31 seconds depending on operation. These are measured cases, not a
guarantee of instant live updates on dense geometry.

The full ten-field settings snapshot is immutable and validated. The recipe
stores selected face/body references. Source geometry and owned history are
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
