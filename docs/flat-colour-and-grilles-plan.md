# Flat colour and grilles implementation

Goal: add flush material regions to the existing pattern workflow, and a separate
Grilles library entry with parallel, crossed and inclined openings.

- Keep the existing target identity and three-feature pattern store. Flat colour
  adds one strictly owned BaseFeature with one disconnected, multi-lump colour
  body. Rebuild updates its source; refuse external edits/dependencies. Geometry
  is partitioned from the original wall, never overlapping or leaving a void.
- Cache the base and colour STL meshes in the rollback computation. Draw two
  opaque meshes in one owned group with contrasting colour, without meshing during navigation.
- Export only the selected owned base/colour geometry as an aligned two-part 3MF
  using the standard-library ZIP/XML writer and the validated STL export route.
  Assign actual filaments in the slicer; do not promise Fusion appearance transfer.
- Reuse shared selection, mapping, transactions and recipe controls for Grilles.
  Parallel bands and crossed openings are planar-first; louvers use a bounded
  sheared prism, an explicit tilt and preserved front/back rectangular border.
  Reject unsupported curved/trimmed louver selections with an actionable message.
- Version the extended settings recipe and retain exact legacy parsing. Keep new
  controls conditional, with local help. Auto fit and 7 mm pattern defaults stay.
- Validate pure layout/shear/3MF invariants, ownership and UI lifecycle locally,
  then fixed native geometry/create/rebuild/export checks in disposable fixtures.
  Check a fresh bridge heartbeat before native requests; preserve the user model.

Validation scope: the current fixed `patterns` entry runs the new details and
shared planar/wrap/general-surface, clipping, Auto fit, Fill, density, persistence
and direct-prism regressions. The 41 unchanged polygon-family checks remain in
`cases(include_polygon_regressions=True)` for motif/mapping changes. Progress is
written atomically beside the probe report so long cases can be identified.
