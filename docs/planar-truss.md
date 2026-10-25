# Planar truss — 0.17.0

## Use

Choose **Patterns > Planar truss**. Select one rectangular face of a uniform solid
plate, then **Done**. Set the layout, Bays, Member width, Frame width and Span
direction. Preview shows the actual cut body. **Create truss** confirms it;
**Edit existing** loads its saved settings and **Rebuild truss** updates that same
body. Cancel removes the temporary preview and restores source visibility.

| Setting | Behaviour |
| --- | --- |
| Layout | Warren, Pratt or Howe; initially Warren |
| Bays | Initially 6; Warren accepts 2–64, Pratt/Howe accept even counts 2–64 |
| Member width | Initially 2 mm, measured perpendicular to each diagonal/post; 0.4–100 mm |
| Frame width | Initially 3 mm of solid perimeter; 0.5–1000 mm |
| Span direction | Along long side initially, or along short side; measured in the selected plate |
| Thickness | Original plate thickness, preserved throughout |

The interface hides unrelated pattern/grille controls and empty advanced groups.
All five controls have illustrated contextual help. The small drawing follows the
layout/count/direction; it is a schematic, separate from the real Fusion preview.

Warren has one alternating zigzag with no intermediate vertical posts and
`Bays + 1` windows, including its two end triangles. Pratt and Howe have opposite
diagonal orientations, vertical posts between bays and `2 × Bays` windows.
Pratt/Howe require even counts to retain central symmetry. Top/bottom refer to
the plate's local layout coordinates, not an applied world-space gravity load.
The geometry nomenclature follows the standard parallel-chord layouts; see
[SCI's truss overview](https://steelconstruction.info/topics/design/trusses/).
No load analysis or physical printed-strength rating is inferred from a name.

Actual Fusion results after changing the initial six bays to eight in Edit:

![Warren](validation/images/truss-warren-0.17.0.png)
![Pratt](validation/images/truss-pratt-0.17.0.png)
![Howe](validation/images/truss-howe-0.17.0.png)

## Geometry and efficiency

`tools/truss/planner.py` is a new host-independent millimetre planner. It divides
the inner rectangle into triangles and proves that their areas cover the region.
Each interior triangle edge is inset by half the requested member width. Edges
on the frame keep the requested perimeter. This yields true perpendicular member
widths, connected junctions and disjoint convex windows, rather than overlapping
independent bars. Windows with inscribed radius below 0.1 mm are refused before
native solid creation, without silently reducing the member width or bay count.

The existing rectangular-plate inspection proves uniform material through the
entire thickness, including the back. One closed multi-loop BRep is then created
using the existing perforated-prism helper. Opposed shared edges, strict window
separation, exact volume and a single solid lump are checked. Work is bounded by
64 bays and at most 128 windows. There is no Boolean or feature per member and
no repeated wall query per triangular window. No StructForge code was copied.

The tool reuses the accepted pattern face picker, cached mesh preview, visibility
lease and in-place Cut persistence. It adds one owned cutter BaseFeature and one
native Cut. Rebuild replaces only the owned cutter geometry, retaining the target
identity, name, visibility, feature ID and history count. The shared store allows
one owned Pattern/Grille/Truss layout per body; these cannot be independently
stacked on the same body. Edit uses the original plate before the owned cut.

Shared settings recipe **10** contains 25 fields. Versions 1–9 gain only the
previously absent `truss_bays=6` and `truss_axis=long` defaults. Exact old schemas
remain strict; reading an old recipe does not write attributes or alter geometry.
New truss styles are refused in old recipe versions. Grilles and other pattern
settings retain their existing dimensions and behaviour.

## Supported geometry and limits

Use one native root-component rectangular planar face on a complete uniform
solid plate in a parametric Design, with the timeline at the end. The plate may
be inclined in 3D; the layout follows its face. It must have straight boundaries,
no holes/steps and a flat opposite back. The current rectangular chart alignment
requirements of the shared plate inspector apply. Multi-face, Whole body, curved,
arbitrary sketch-profile, hollow enclosure and variable-thickness inputs are not
supported. Unsupported selections are refused without model edits.

Every member is constant through the plate's original thickness. The intended
print orientation places the plate back on the bed; the add-in does not rotate
the document or export orientation. The release does not add raised/engraved
trusses, mounting holes, member chamfers, curved boundaries, FEA or load ratings.
Fit, adhesion, material strength and printing remain physical validation tasks.

## Validation

**1001 Python tests**, three Node UI suites, compilation and whitespace checks
pass. Independent tests sample both sides of every diagonal/post at half-width
±0.03 mm, confirm the frame, exact closed volumes, axis changes, bounded windows,
legacy schema defaults and early refusals. A command-session test checks the
truss preview message and that Create uses the reviewed result.

Headless Edge at 300/380/520 px passes three layouts, both span directions, odd
bay guards, all five help illustrations, hidden unrelated controls, family
switching and no horizontal overflow. This is separate from actual Fusion CEF
pointer/navigation acceptance.

Fusion 2705.1.30 passes **15 isolated MCP cases**: the three styles, odd Warren,
short-side layout, a plate inclined 60°, maximum 64 bays/128 windows, a style/
direction/dimension Edit cycle, six early refusals and a mounted-grille legacy
regression. Material witnesses measure real windows and both sides of every
member through the plate midpoint. Preview mesh draw/cleanup, Create/Edit/Rebuild,
unchanged body/name/visibility/history and restoration of the original caller
pass. All disposable documents are discarded without saving.

The 128-window fixture measured about 159 ms preparation, 608 ms Create and
2.2 s full read/prepare/Rebuild/read plus independent material checks. These are
fixture observations, not a universal performance promise. Actual pointer/orbit,
save/reopen, Undo/Redo and physical printing/load tests remain unproved.

Evidence: [planar-truss-0.17.0.json](validation/planar-truss-0.17.0.json).
