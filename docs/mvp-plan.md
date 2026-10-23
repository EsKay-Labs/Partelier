# Product scope and MVP plan

## Confirmed purpose

Create small parametric CAD helpers inside Autodesk Fusion that save time on
repetitive details in the user's own 3D-print designs. The user specifically
identified hinges and similar mechanisms as the intended value. Finished printer
accessories in earlier concept images did not communicate this purpose.

Common interaction: select existing geometry -> enter dimensions -> preview the
detail -> create it. For example, a hinge helper builds matching knuckles and
coaxial bores on the selected design. The original truss/honeycomb intent remains
in scope as a later tool family. The user approved **Partelier** as the product
name on 2026-10-21. The project folder and Fusion bundle use Partelier; the Python
package uses partelier.

The user explicitly requested a polished HTML interface like StructForge, with
an image explaining each function. This supersedes the native-only UI assumption.
An HTML library prototype is the first UI increment; it does not advance the
hinge geometry gates or establish the illustrated features as implemented.

## Consolidated planned tool set

All entries are planned capabilities, not implemented features. First-release
grouping is a working prioritization based on the user's clarified need.

| Tool | User supplies | Detail to automate | Stage |
| --- | --- | --- | --- |
| Pin hinge | Two mating parts, axis/edge, dimensions and clearances | Alternating knuckles, matching bores, attachments and optional separate pin | First release |
| Snap-fit pair | Mating regions, tab dimensions and clearance | Cantilever hook and matching receiving opening | First release |
| Sliding guide | Direction, length, section and clearance | Matching rail/groove with optional travel stop | First release |
| Pivot/clevis joint | Axis, fork/tongue dimensions and pin | Aligned ears, intermediate tongue and coaxial holes | Extension |
| Bayonet closure | Mating cylindrical regions, engagement and clearance | Matching lugs and rotation slots | Extension |
| Retaining clip | Position, retained section/diameter and opening | Clip geometry and attachment | Extension |
| Hardware pockets | Placement and actual hardware dimensions | Nut traps, insert seats, magnet pockets and bearing seats, with appropriate access | Extension |
| Ribs and gussets | Faces, thickness, direction and spacing | Attached reinforcement webs | Extension |
| Planar trusses | Closed planar boundary, pattern and strut dimensions | Connected chord/web geometry; begin with Warren, then assess Pratt/Howe | Pattern stage |
| Honeycomb | Supported boundary/envelope, cell/wall sizes and keep-solid zones | Bounded cells with preserved borders and selected mounting regions | Pattern stage |

## Shared behavior targets

- Few meaningful parameters, explicit mm units and adjustable fit clearances.
- Local HTML/CSS/JS tool library and guides, with Fusion-owned geometry selection
  and simple validation messages. Each function needs an explanatory image.
- Non-persistent Preview, clean Cancel and explicit Create target/result ownership.
- Matching features aligned through the same geometry plan.
- Edit/rebuild from saved parameters and reusable presets are product targets;
  introduce them as separately verified slices after first creation works.
- Attached helpers integrate directly into the selected bodies, retaining their
  identities, names and visibility. They must not leave duplicate source/result
  pairs. Separate output creates independent parts deliberately. Specify owned
  tools/features and rollback so Preview, Cancel and failed creation leave the
  selected design unchanged.
- State support and verification limits. Input checks and concept images do not
  prove fit, motion, printability, strength or durability.

## First-release milestones

Work through the following gates in order, with one bounded task active at a
time. Each gate can take several small implementation tasks. A failed native
check returns to the current gate; it is not deferred while more tools are added.
This is a delivery plan, not a claim that the listed systems already exist.

| Gate | Work | Observable exit condition |
| --- | --- | --- |
| 0. Hinge specification and host baseline | Define the supported two-body case, selections, axis, knuckles, bores, attachments, gaps and result ownership. Record the Fusion build/runtime and check the existing add-in lifecycle on a disposable document. | A dimensioned fixture and expected results are written down; host baseline is recorded, or explicitly remains a blocker for native implementation validation. |
| 1. Pure hinge plan | Add immutable hinge inputs and a planner in mm. Introduce only the shared registration, unit and event helpers the first hinge actually needs. | Valid inputs produce deterministic placement and dimensions; invalid or degenerate cases produce actionable errors. Focused local checks pass. |
| 2. Temporary hinge preview | Read a bounded geometry snapshot, build temporary hinge geometry and display it. Compare native sketch/extrude and temporary BRep approaches on the same fixture before choosing the creation strategy. | Preview matches the plan; changes invalidate stale previews; Cancel, document changes and Stop leave no persisted geometry/settings or temporary graphics behind. Timing is recorded. |
| 3. Integrate attached details | Join the hinge into the two selected root bodies using owned tools and native combines. Retain target identity/name/visibility; optional pins are the only additional attached-output bodies. Keep independent leaves as a separate output choice. | Body identities and counts match the contract; joins, bores and gaps are verified. Cancel/failed Create leave no change, and Undo/Redo leaves no orphaned tools or results. Record native evidence. |
| 4. Edit and rebuild | Save a versioned recipe and explicit target/tool ownership. Update attached tool shapes in place so combines recompute; migrate older copy-based output only after strict ownership/dependency checks. Handle missing or changed sources clearly. | Repeated rebuild retains target identities/counts, including after save/reopen. Failed rebuild preserves the last valid result. Unknown recipes and unsafe migration are refused. Complete native checklist/performance review. |
| 5. Two more helpers | Implement one bounded snap-fit pair, then one sliding guide, each with specification, planner, preview, creation and editing. Extract common code only when actual duplication warrants it. | Both tools pass their own fixtures and cancellation/edit checks without changing hinge behavior. Adding them does not require adding tool-specific branches to the shared runtime. |
| 6. Small details and surfaces | Add selected hardware pockets, enclosure details, text and planar surface patterns as separate useful increments. | Every new helper has a supported selection contract, editable inputs and its own native acceptance evidence. |
| 7. Truss and honeycomb family | Add bounded planar Warren trusses and honeycomb with borders/keep-solid zones, then assess more layouts and volumetric cases. | Exact supported clipping, connected junctions, size limits and measured performance are verified before broader boundaries or denser patterns are enabled. |

**2026-10-23 priority update:** the user confirmed and locked the current hinge
and snap-fit tools, then requested surface patterns before the next mechanical
helper. Version 0.9.0 implements perforations and engraving/embossing together,
starting with physical plane/cylinder charts, several faces of faceted solids,
and guarded regular regions of other smooth surfaces. The
[surface-pattern contract](surface-patterns.md) supersedes the earlier planar-only
pattern ordering above; trusses and volumetric lattices remain separate work.

The first usable checkpoint is the hinge through gate 4. The proposed first
release adds the two helpers in gate 5. Do not wait for cosmetic patterns or a
large feature catalogue to make the hinge useful. No release date or validated
generator exists at present.

For the first hinge, the proposed scope is two solid bodies in the root component
and a separate pin. The design task must settle the exact planar attachment and
axis selections before coding. Assemblies, arbitrary curved attachments,
print-in-place hinges and flexible hinges are separate extensions.

"Parametric" initially means editable dimensions with an explicit Edit/Rebuild
action. Automatic response to every upstream model change is a later decision;
it must not be implied by a static generated body or a saved recipe.

## First native-use feedback

The first reported hinge attempt used two touching bodies from a split block,
with coplanar exterior faces. The visually shared edge could belong to B while
the original code required A, and the old fixture assumed an existing gap.
The selection fix canonicalizes coincident A/B picks to the actual A boundary.
A complete shared seam is detected automatically; the manual Split seam control
remains available. Preview computes rectangular-interface clearance on temporary
copies. Version 0.5.0 applies attached clearance and details to the selected root
bodies through native combines; separate leaves keep their independent output.
Earlier copy-based Create was rejected by the user because it doubled the main
bodies, even when the originals were hidden. That architecture is superseded.
The user also requested separate hinges distributed with explicit count and end
margins. Recipe version 3 stores that layout and strictly reads
prior versions as one centered hinge.
This is a correction within the current hinge gate, not a new tool milestone.
The final 0.5.0 native run passes 53 stated expectations, including four attached
treatments with four Rebuilds each, legacy migration and a programmatic production
Session workflow. It retains the selected targets without duplicate main bodies.
Broader interactive, save/reopen, Undo/Redo, failure/topology, motion and print
acceptance still precedes closing the hinge gate. See
[fusion-validation.md](fusion-validation.md) for exact scope and source hashes.

## Current native feedback and UI direction

The user confirmed successful attached hinge creation and supplied a native
Create log (206.422 ms total, 127.068 ms persistence) after the Part Design fix.
The new request moves dimensions and Preview/Create/Cancel to the HTML palette,
leaving only native geometry selectors, and replaces the flat blue preview with
neutral lit shading. Independent flat/rounded leaves and optional through-holes
are the next hinge increment; their native acceptance remains pending.

Barrel, concealed and print-in-place are all requested hinge families, with
45-degree underside chamfers as an initial print-in-place target dependent on
print direction. They remain planned, with specifications and required evidence
in [hinge-families.md](hinge-families.md). They are not displayed as working tools.

## Extension and efficiency decisions

Use a thin shared runtime and independent built-in tool modules, with pure
planners separate from Fusion interaction. A new tool should register its own
command, parameter contract and geometry adapter. Add common services only for
concrete needs; do not build a dynamic plugin platform or empty framework now.
See [architecture.md](architecture.md) for the intended boundaries.

Efficiency has two acceptance dimensions:

- **Designer time:** preview the matching pair together, expose a small set of
  useful dimensions, explain invalid selections and allow later dimension edits
  without manually rebuilding the detail. Observe selection/parameter steps on
  the fixture before adding shortcuts or presets.
- **Runtime cost:** measure input reading, pure planning, temporary geometry,
  drawing and persistent creation separately. Avoid duplicate rebuilds for
  unchanged inputs, cache only valid session data and budget dense work before
  allocating geometry. Choose optimizations using the same reproducible fixture.

Set numerical response-time targets after the first native baseline, on recorded
hardware and a recorded Fusion build. Do not promise a speedup from a technique
alone. Python and Fusion's own API remain the starting stack; threads, native
extensions or external libraries require evidence of a specific bottleneck.

## Details and cosmetic backlog

These are candidates from the feature discussion, not additions to the first
release commitment. Prefer one consistent surface-pattern workflow with shared
spacing, size/depth, rotation, border and keep-out controls. Do not implement an
independent architecture for every pattern.

| Family | Useful candidates | Initial boundary |
| --- | --- | --- |
| Enclosure details | Lid lip/groove, alignment pins and receiving holes, finger notches, motion stops, keyhole slots | Simple mating planar regions; generate matching details together |
| Hardware details | Nut traps, insert seats, magnet pockets and bearing seats | User-specified actual hardware dimensions, depth, clearance and access |
| Labels and orientation | Raised/recessed text, arrows, index marks and scales | Planar face placement first |
| Grip and surface relief | Diamond knurl, straight flutes, ribs, waves and herringbone | Planar relief first; wrapping onto curved faces is a separate task |
| Perforations | Circle, slot, triangle, square and diamond patterns, plus honeycomb | Finite planar region with preserved border and excluded zones |
| Later surface cases | Radial arrangements, Voronoi cells and O-ring grooves | Separate specifications for center/boundary or actual seal/gland dimensions; no sealing claim |

After the initial three helpers, choose the next small detail using the user's
actual design needs. A practical starting shortlist is hardware pockets,
lip/groove with alignment pins, text, and planar perforations or knurling.

## Later priorities

Add the chosen small details, clips and ribs independently; then expand to
pivots and bayonet closures. Retain trusses and honeycomb in a pattern stage,
with connected geometry, exact supported boundaries and keep-solid mount zones.

Gear/rack generators, ratchets, cams, variable-density lattices, printability
analysis and calibration coupons remain candidate backlog items. Earlier
illustrations of spool holders, camera mounts and printer stands are examples
of possible end products, not dedicated first-release generators.

Grow the requested HTML palette in small verified increments. Defer complete
product templates, a slicer, FEM/automatic strength optimization, AI services,
licensing and marketplace packaging.

## Current implementation and verification

The UI increment adds a toolbar launcher for a local, resizable HTML palette.
Its 12 catalogue entries are planned tools selected from a grouped dropdown,
with an original SVG concept image for the selected tool, session favorites,
detail guides and illustrative view controls. The user requested a stronger blue light theme with legible labels and field
boundaries, replacing the sage trial. Direct tool selection replaces the initial
dark card gallery. Pin hinge geometry is picked directly in the model from HTML buttons;
only Create/Rebuild launches a zero-input native transaction command, with a
live capability handshake; other tools stay disabled. The browser version
does not simulate a live Fusion connection or geometry selection.

The foundation also registers a native honeycomb input-check command. It accepts one
selected BRep solid and HoneycombSettings containing cell_size_mm and
wall_thickness_mm. That diagnostic makes no model writes and saves no recipe.

Five pin-hinge presets now configure round/square profile, knuckle count and
sharp/chamfer/fillet treatment. Fillets affect generated primitives, not original
source edges or concave union blends. Other mechanism families remain planned.
An independent experimental hinge module implements frozen planning, native
selection, temporary BRep preview, copy-based Create and versioned manual
Edit/Rebuild. Its exact supported fixture, formulas and native checklist are in
[hinge-design.md](hinge-design.md). The pure planning gate has local evidence;
the host-dependent gates remain pending native acceptance. No validated hinge
release, snap-fit, sliding-guide or pattern generator is claimed.

Local tests cover parameter rules, units, bridge request validation and a fake
host lifecycle contracts, ownership/rollback and recipe boundaries. Browser
interaction checks are recorded in
[development.md](development.md). Native Fusion loading, palette/bridge behavior
and panel-free selection/transaction acceptance remain pending. Attached Create
and the prior geometry-to-HTML synchronization are user-confirmed; local/fake-host
tests do not validate the new native paths.

## Assumptions and decisions still needed

- Keep Python, standard library, local HTML/CSS/JS, Windows-first and initially
  English UI. Native Fusion controls handle selection as needed. FDM is the
  initial printing assumption, not a specified machine.
- Start with a separate-pin hinge. Print-in-place and flexible hinges need
  their own material/clearance requirements and verification.
- Before each helper, settle supported selections, dimensions/fit semantics,
  attachment method, result identity and Edit scope. Do not guess critical details.
- Printer, nozzle, material, layer height, build direction and acceptable fit
  are unspecified. Use adjustable values and test coupons when needed; do not
  assert universal tolerances or automatic print success.
- Pattern tools still need decisions about planar openings versus volumetric
  envelopes, closed skins versus exposed cells, and shell/skin thickness.
- No backend, database, network service or account system is needed. The hinge
  uses versioned Fusion attributes for its concrete Edit/Rebuild workflow.

## Geometry risks and next task

Hinge attachments, coaxiality, mating gaps, snap-fit material behavior, sliding
travel, stale body references and assembly transforms require bounded fixtures.
Dense patterns additionally need a cell/body budget, actual clipping and
connected junctions. A bounding box is not proof of shape conformity.

Use [.ai/next-task.md](../.ai/next-task.md) for native hinge acceptance. See
[architecture.md](architecture.md) for pure-planner/Fusion boundaries and
[development.md](development.md) for the foundation's native checklist.
