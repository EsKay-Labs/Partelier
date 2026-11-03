# Partelier repository guidance

## Current delivery: 0.29.0

This section supersedes earlier release-specific deferred-scope statements below.
The current implementation includes attached mechanical pairs (seven two-part
families), linked louvers, parallel lift and a rotating offset four-bar hinge,
blower volute/lid, native-offset concave/spline lid perimeters and guarded
event-driven source updates. Hardware pockets remain excluded by explicit request.
See docs/remaining-tools-0.29.0.md and docs/automatic-updates.md.

Automatic updates enroll only on successful explicit Create/Rebuild, preserve
ownership guards and run inside one rollback-capable native command. No timer,
worker Fusion access or orbit-triggered scan. Old features are not enrolled by
listing. refresh_context authority is limited to one exact anchor and operation
end; never broaden its stale-result exception into general edit permissions.
Multi-part linkages require assembly fasteners and a print layout; do not call
them print-in-place. Sampled collision checks do not establish physical fit,
strength, continuous motion or clearance against user cabinetry.

Palette pArea recovery permits one fresh-ID visible floating retry, retires old
handlers and cleans a failed replacement. Do not suppress unrelated display
failures or create unbounded retries. Native geometry is unchanged by recovery.

## Purpose and scope
Build a Python add-in for Autodesk Fusion that automates time-consuming small
CAD details on the user's existing designs: hinges, snap-fits, sliding guides,
connections, hardware pockets, and later reinforcement/pattern tools. Prioritize
reusable parametric helpers. The proposed first release is hinges, snap-fits and
sliding guides; honeycomb and grilles are implemented, and 0.17.0 adds rectangular
plate Warren/Pratt/Howe planar trusses. The user has
approved Partelier as the product name. Use Partelier for the UI, Fusion bundle
and project folder, and partelier for the Python package.
The repository root is `C:\Users\SKTech\Desktop\Programming_Projects\Apps\Fusion360\Partelier`;
the installable add-in is its `Partelier/` subfolder.
The current app includes an illustrated HTML toolkit, an experimental pin-hinge
planner and Fusion Preview/Create/Edit implementation, and the original native
solid/honeycomb input checker. The user confirmed attached Create and the earlier
picker-to-HTML synchronization. The current palette uses direct model picking
and a zero-input native Create/Rebuild transaction; no second panel is intended.
Live preview is always on in the HTML session, debounced for edits; Create
requires a successful preview of the current revision. Experimental 0.5.0 uses
recipe 9 for attached output: integrate into the two selected root bodies and
retain their identity, name and visibility. Only optional pins add final bodies.
An owned tool BaseFeature feeds native Join/Intersect features; attached Rebuild
updates owned tool sourceBodies instead of creating replacement result bodies.
Separate-leaf output retains its independent persistence path. Strict legacy
migration may remove only old owned results after safe integration.

Native request `9a1e8b26-7909-4f1a-b43b-7fb1deec501b` on Fusion 2705.1.30 passes
53 expectations: 40 generated geometry cases, six explicit larger-fillet refusals,
six in-place/migration cases and one production-session workflow. Four attached
treatments each pass four Rebuilds with retained targets/counts/history. Local
checks pass 480 Python tests, the Node DOM suite, syntax and compilation.
Selections are programmatic; do not claim actual CEF/picking/navigation or new
queued-preview/cancellation evidence. Preview/Cancel and final rollback leave
no persisted model changes. Stored full-shape tools require explicit Rebuild
after upstream edits. Complete palette acceptance, save/reopen, Undo/Redo,
motion and printing remain pending. Earlier 0.4.3 reports are historical.
See docs/fusion-validation.md, docs/hinge-design.md and docs/mvp-plan.md for
current contract, scoped evidence and the next acceptance task. Plan complex or
ambiguous changes first.

The ordered delivery gates are in docs/mvp-plan.md. Finish a usable hinge through
Edit/Rebuild before adding the other first-release helpers.

## Architecture and folders
- `Partelier/Partelier.py` and `.manifest`: Fusion loading and unloading.
- `Partelier/partelier/addin.py`: native dialog, events, and Fusion adaptation.
- `Partelier/partelier/settings.py`: immutable, host-independent input contract.
- `Partelier/partelier/palette.py`: HTML palette/launcher lifetime, bridge and
  manifest-versioned HTML URL; HTML asset tags/display version must agree.
- `Partelier/partelier/palette_protocol.py`: host-independent message validation.
- `Partelier/partelier/ui/`: local HTML/CSS/JS, catalogue and original SVG art.
- `Partelier/partelier/tools/hinge/`: pure settings/planner/layout/seam/finish bounds, Fusion geometry and
  native selection/transaction commands. `rounding.py` constructs transient
  analytical primitives; support.py adds the user-referenced tapered support.
  native_finish.py finishes fully joined copies; native_preview.py owns the
  HTML workflow's short rollback-only compute commands. roof_finish.py only
  checks/refuses detected round/tapered C1 valleys; it returns the same body and
  must not refill material or silently shrink a requested finish. The unproven
  roof-completion approach was discarded. visibility.py owns captured body
  light-bulb leases for preview, repicking and mode changes.
  Current recipe v9 adds attached in-place persistence; v8 added movement relief; v1-v6 retain flat webs/no relief, v7 retains taper/no relief. See docs/hinge-design.md for scope.
- `tools/fusion/HingeFixture/`: standalone disposable fixture script, not runtime.
- `tests/`: standard-library tests runnable outside Fusion.
- `Partelier/partelier/tools/details/`: 0.18.0 rectangular mating lid lip/groove,
  alignment pins and same-body 90-degree ribs/gussets. Hardware pockets excluded.
  Separate 21-field settings and version-2 delta-tool records (strict version-1 reads); same target bodies,
  two/three native features, guarded timeline-end Edit. See docs/small-details.md.
- `Partelier/partelier/tools/truss/`: pure bounded triangular-window planning and
  one-solid Fusion adaptation. Shares the HTML pattern session, plate inspector,
  cached mesh and same-body Cut persistence. See docs/planar-truss.md for scope;
  shared settings recipe16 retains28 fields and reads exact versions1–15.
- `docs/`: product plan, architecture, development and AI workflow guidance.
- `.ai/templates/`: manually selected task prompts, not auto-loaded instructions.
Use docs/architecture.md for module boundaries and docs/development.md for setup
and host checks. Read only the documents relevant to the task.

## Run, checks, and build
Load the `Partelier` folder using Fusion's Scripts and Add-Ins dialog; run the
Partelier add-in, then open its command from the Design workspace Add-Ins panel.
Fusion supplies `adsk`; do not install an unrelated package with that name.
From the repository root on Windows:
```powershell
py -m unittest discover -s tests -v
node tests/test_palette_ui.cjs
py -m compileall -q Partelier tests tools/fusion
git diff --check
```
There is no separate build or configured linter. Distribute the self-contained
Partelier folder after native validation; add packaging only when needed.

## Conventions and product rules
- Use Python's standard library, four spaces, explicit names, and small modules.
- Keep geometry planners independent of `adsk`. Use millimetres in pure code;
  convert Fusion's internal centimetres once at the adapter boundary.
- Grow independent tool modules around a thin shared runtime. Add shared code
  for demonstrated needs; do not create an empty plugin framework. Measure
  geometry/preview costs before introducing optimization infrastructure.
- Keep Fusion API access on the main thread. Any later workers must operate
  only on plain data and need a task-specific justification.
- Use the user-requested HTML/CSS/JS palette for the product UI. Keep all assets
  local and add no frontend dependencies without a specific reason. Native
  controls remain appropriate for Fusion geometry selection and the diagnostic.
  Show units and actionable errors. HTML must not access or mutate the model
  directly; route supported actions through the Python adapter.
- The user prefers a grouped tool dropdown to the card gallery. The 0.20.1 UI uses a graphite header, slate-gray workspace, pale cards and
  white inputs. Preserve visible surface contrast; the 0.20 all-white result
  was explicitly rejected by the user. Keep a clear active-pick highlight. The dropdown exposes implemented tools only; keep Saved and
  secondary controls out of the default configuration view.
- Keep UI text in English initially, matching the reference tool; this is an
  assumption, not a confirmed language requirement.
- Retain event handlers while needed and remove owned controls on Stop.
- Preview and Cancel must leave no persisted geometry/settings. Finished previews
  may use helper-owned model objects only within their rollback transaction.
  Create/Rebuild must preserve selected body identity for attached output and
  clean partial owned features on failure without changing unrelated objects.
- On tested Fusion 2705, fireCustomEvent can return False despite actual delivery.
  Do not reject a queued preview on that return alone; retain registration and
  event-ID guards, delivery-driven completion and explicit handling of real API
  exceptions.
- Attached output integrates into the selected root bodies using owned full-shape
  tool geometry and native combines; no duplicate final source/result pair.
  Preserve target identity/name/visibility. Full preview hides only explicit
  targets/owned old results; repick reveals them temporarily. Restore captured
  preview visibility on Cancel, failed creation and Stop. Report failed restores.
- Attached v9 Rebuild updates owned tool sourceBodies and recomputes combines.
  Evaluate historical source references before the owned tool feature. Require
  exact ownership, topology and dependency checks for legacy migration; delete
  only old owned output after safe integration. Never delete arbitrary hidden
  bodies or unrelated later results. Separate Hybrid Edit retains its last-feature
  gate. Upstream tool-shape recalculation requires explicit Rebuild.
- Keep host pushes newer than delayed acknowledgments; reject older revisions
  and retired session IDs. Retired IDs are page-local so fresh Connect recovery
  works. Version the top-level HTML URL and all assets from the manifest.
- Main palette Close cancels all owned tool sessions and queued work (0.25.1).
  Keep the native closed handler, strict page-generation guard and clean page
  recreation. Each manager owns cancel_palette and skips cancelled openings;
  completed features remain. Close must never revive a stale HTML request or
  preempt an unrelated command. Native synchronous calls finish at their next
  event boundary; do not claim immediate interruption. See docs/palette-close.md.
- Native finish stages must keep explicit edge membership: no automatic cap
  tangent-chain expansion, and no re-finishing newly created blend borders.
  Preserve the frozen original side-curve ownership and hole-safe neck bounds.
- Do not invent printability, strength, load-rating, or optimization guarantees.
  Geometry checks cannot substitute for physical or engineering validation.
- No database, backend, network calls, telemetry, or external Python dependencies
  are required. Do not add them without a task-specific reason.
- Do not copy the StructForge project, alter its checkout, reuse its command IDs,
  or treat its validated fixtures as evidence for Partelier geometry.
  Selective adaptation of useful techniques is authorized; record the origin
  and add focused checks for any adapted algorithm. See docs/architecture.md.
- Do not add fake Generate/Preview actions or mark proposed features implemented.
- Generated concept images illustrate ideas; they are not implementation specs or
  evidence of valid mechanism geometry. Use docs/mvp-plan.md for current scope.

## Completion and reporting
Use Goal, Context, Relevant files/folders, Constraints, Done when, and Checks/tests
for future task prompts. A task is done when its observable acceptance criteria
and relevant checks pass. Distinguish local tests from native Fusion validation;
report pending host checks explicitly. Report what changed and why, files changed,
commands/results, assumptions, limitations, and the next useful task. Update
affected docs when behavior or a material decision changes.

## Development validation preference
The user prefers script-driven checks without taking control of the PC. Use
`tools/run_fusion_validation.py` and the opt-in development
`tools/fusion/PartelierValidationBridge` for supported native checks. The bridge
has been exercised in Fusion; check its fresh running status before each request.
Do not substitute Windows input automation for these tests. The watcher may only
perform file I/O and fireCustomEvent; all Fusion access stays on the main thread.
See docs/fusion-validation.md. Local mocks remain distinct from native evidence.

## Selection and operation history (0.19.0)
- `partelier/operations.py` lists recipe metadata only, captures native timeline groups inside commit transactions and owns guarded suffix deletion. Group children have exact per-operation ownership; preserve original source bodies. Stable timeline groups are used; no preview Custom Features API.
- `ui/selection-ui.js` owns shared step styling, palette Esc/reset and wheel routing. Esc resets references/preview but keeps dimensions; pattern faces still require Done. Late preview work must be cancelled/retired.
- `ui/operations.js` shows Saved features in each tool (0.24.1), with exact saved-anchor Edit/Delete. Buttons use two equal grid columns; confirmation replaces the toolbar with Keep feature/Delete feature and scrolls into view. Ordinary surface aliases share a list; Planar truss, Grilles and each other tool are scoped separately. Saved is the optional all-features browser; Pick from model remains an alternative. Earlier-feature geometry guards remain. Explicit successful Rebuild may adopt exact legacy history; listing never migrates it. See docs/selection-history.md and its native/browser evidence.

## Compact workflow (0.20.0)
- `ui/workspace-flow.js` owns geometry disclosure presentation only. Fold once references are complete; keep multi-face picking open until Done. Change stays open through ordinary edits and reset reopens selection. Never use disclosure state to decide CAD validity or alter settings.
- Startup size is 380 × 760; actual docked height belongs to Fusion. The per-tool feature list is visible above Geometry; Saved opens the optional all-features browser and model picker. Examples and all secondary parameters remain available.
- Session revisions are local to their session. On a legitimately adopted new operation, load its settings even if its revision is lower than the previous session's. Continue rejecting retired sessions and older same-session pushes.
- See docs/compact-ui.md and docs/validation/compact-ui-0.20.0.json for scoped checks. Browser screenshots are not native pointer acceptance.

## Selected lip sides (0.21.0)
- Lid lip & groove has Continuous perimeter and Selected sides. Source faces remain rectangular. Side indices are cyclic in the historical face A frame; persist lip_sides as a strict 1–15 bit mask and lip_layout as closed/selected. Keep mask15 on the original ring path.
- Selected runs use a unified contour before the 45° tip, with receiving clearance around run ends too. Never chamfer separate strips and join them afterward. Preview stays gated until the additive native edge picker finishes with Done; Esc clears pending sides. Restore handlers, native selections and visibility on Cancel/Stop.
- Exact 19-field recipe1 records upgrade to closed/15 only in memory; explicit Create/Rebuild writes recipe2 with21 fields. Active snapshots remain strict. Side masks are host-owned, changed by model picking and Done.
- Ribs show Height on A and Width on B together; Thickness is separate. Internal dimension names retain their existing meanings. See docs/small-details.md and selected-lip-0.21.0 validation evidence.

## Rounded push-fit (0.21.1)
- Existing ball_detent is labelled Rounded push-fit. Compact lid preset is explicit-only, not automatic on family selection/Edit. Preserve the21-field snap settings and recipe3.
- Rounded push-fit accepts coplanar inner or outer sidewalls. Use local arm/nose/engagement free-space checks on both source bodies, plus existing exact root/socket/overlap guards. Whole-body exterior-plane checks remain on hook/torsion. Do not remove walls or create duplicate source bodies to enable an interior mechanism.
- This is a flexible-arm rounded detent, not a rigid bump fit or force solver. Show inner/outer sidewall diagrams in collapsed Examples; horizontal lid/rim faces belong to locating lip/groove. Native geometry evidence and limits are in docs/snap-fit-design.md and rounded-pushfit-0.21.1.json.

## Truss junction fillets (0.22.0)
- truss_fillet_mm is a radius, default0 (sharp); exact26-field snapshots, recipe11. Exact recipes1–10 inject0 only in memory and explicit Rebuild saves11. Never silently shrink the radius.
- Round triangular window corners in2D through the original thickness; add junction material without rounding the outer/cap edges. rounding.py owns exact tangent arc/area planning; rounded_prism.py constructs one healed BRep with analytic arcs/cylinders, no per-corner features/booleans. Radius0 stays on the original planar prism path.
- Preserve same target body and BaseFeature/Cut history. Tests and scoped native evidence: docs/planar-truss.md and truss-fillet-0.22.0.json. No structural/print-force claims follow from fillets.

## Surface Warren and cell fillets (0.23.0)
- Surface patterns is the visible name for internal honeycomb alias. Ordinary shape 'warren' is a tiled2:1 triangular band motif, distinct from the plate-only truss_warren. Use the existing chart/periodic/gap/border guards; full-wrap mosaics retain0/180° rotation.
- pattern_fillet_mm is independent of truss_fillet_mm. Exact27-field snapshots and recipe12; exactv1–11 inject0 read-only, and legacy versions refuse 'warren'. Zero preserves previous built-in rounded variants; positive radius overrides them. Circles/slots are already smooth.
- Whole-cell fillets use shared analytic Profile/prism construction; round original polygons before trim decomposition to avoid fragment seams. Preserve Cell.original_polygon_mm only for actual positive-radius clipping. Trim/sheared/raised paths use <=0.01mm sag/128point strokes shared across levels. Never silently clamp a requested radius.
- Keep source safety rays/physical gap threshold, actual on-surface interior witnesses and conservative AABB pruning. Retain cached mesh rendering; no native feature per corner, no duplicate source bodies. See docs/surface-patterns.md and surface-cell-fillet-0.23.0 validation evidence.

## Fixed grille families (0.25.0)
- `patterns/grille_styles.py` adds opposed Two-way deflection and Four-way diffuser to the existing linear/grid/louver types. Per-hole flow directions drive shared cutters/raised lofts. The diffuser remains centred/aligned; nonzero Direction/offsets are rejected, not ignored. Preserve the central/diagonal rib widths, bounded aperture counts and bed-relative45° proof.
- Settings remain27 fields; recipe13 admits the new enums, while exact versions1–12 remain read-only compatible and refuse those enums. Preview remains a cached opaque mesh. Use the same body/history and per-tool Saved features.
- `tools/fusion/PipLouverCoupon.py` is a separate experimental captive-pivot print test, not a production moving/register option. Its generated3MF/STL and instructions are in examples/print-tests/pip-louver. Native motion/solid/overhang checks are not physical release/friction evidence. Wait for a real print before promoting the mechanism to the app. See docs/grille-families.md.

## Grille bevel and screw position (0.26.0)
- Raised + chamfer freezes fin shear at the start of the top bevel. Equal inward/outward profile offset and rise give45° bevel planes relative to the flat back, independently of fin tilt. Keep the bounded shared loft, cached mesh and same-body history; no per-edge native chamfer features.
- `grille_chamfer_mm=0` means Auto (min0.6,height/2,rib/4,border/4). Positive size is exact and must be below Height and half Rib width; refuse collapsed/overlapping geometry without clamping. It is independent of cell fillets and louver tilt.
- Auto screw centres move0.8mm inward; custom `mount_inset_mm` remains an exact edge-to-centre distance with its original safety minimum. Reserve effective border before pattern planning. Screw inset is beside Screw size under Advanced → Mounting holes.
- Recipe14 has28 strict fields. Exactv1–13 inject only the absent bevel field in memory; saved bodies/recipes change only on explicit Rebuild. Explain corrected bevel/Auto mounting changes when editing older grilles. See docs/grilles.md and validation/grille-chamfer-0.26.0.json.

## Full-height external grille frame (0.26.1)
- User clarified that Raised + chamfer must slope to the root of the EXTERNAL frame, not just its top edge. This supersedes the external-cap-only0.26.0 behavior. The rim has a continuous45° taper through the whole Height; retain the previous top footprint when possible, widening the root only within the plate. Refuse collisions instead of leaving a vertical wall or changing openings/height.
- Mounting clearances for this profile expand with elevation through the same rise, leaving sloped recess walls rather than cutting vertical steps into the new rim. Reuse profile_loft's bounded closed-solid path with zero holes; ordinary Raised stays vertical. Keep one source body/history and cached mesh.
- grille_chamfer_mm controls only the small fin-top bevel, labelled Rib top bevel. It must not control the full-height external slope. Exact28-field recipe15 reads versions1–14 without writes; old chamfer records show the full-height transition notice before explicit Rebuild. See docs/grilles.md and grille-ramp-0.26.1 validation evidence.

## Mounting must preserve the grille (0.26.2)
- Supersedes corner-block/frustum clearances: mounting may cut ONLY bores/seats in the original flat plate. Never subtract mounting clearance from the raised frame, fins or chamfer, and never restore pads after pattern planning.
- Reserve the complete flat head band first (inset+head radius+1.2mm rim), then the whole raised frame outside that band. Resolve effective aperture Border before planning: flat band + ramp run + worst fin lean + twice fin bevel +0.5mm frame gap. Keep a larger user minimum. Refuse insufficient area; never reduce requested height/opening/rib sizes to fit screws.
- All raised frame contours stay inside that flat band boundary at every height. UI summary/help must explain the profile-dependent Border. Keep original28 settings, exact recipe16 with v1–15 read-only compatibility and an explicit old-mounted Rebuild notice.
- Native validation clips the pre-hole and post-hole shapes above the face and requires equal raised volumes; production mounting performs differences only, so no raised material may be removed. Also check head access, complete bores/seats, same body/history and grouped Delete. See mount-isolation-0.26.2 evidence.

## New helpers (0.28.0)
- tools/mechanisms generates separate mating bodies (not attached edits): straight/dovetail guides, bayonet, clevis, barrel/recessed/captive hinges and independent captive louvers. Preserve explicit separate-part scope, bounded settings and recipe1. Motion fixture is sampled, not a continuous sweep. PIP options are print trials pending physical checks; only louver fixture has a45-degree underside check.
- tools/finishing modifies one planar-face source with notch/keyhole/stop/text/arrow/scale; strict recipe1, full multi-region support masks and one owned delta Combine. Handle Fusion2706 sourceBodies as iterable; change Combine.operation only when necessary and rolled to the feature.
- Continuous lid lips support exact circles and3–10-sided convex polygons. Selected sides and alignment remain rectangular. No concave/spline approximation.
- Fans recipe2 has43 settings, strict legacy40-field recipe1 reads; blower is radial impeller only, no volute. Preserve local cached meshes and owned saved-history lifecycle.
- See docs/overnight-0.28.0.md and validation reports. Hardware pockets, automatic upstream recomputation and automatic attachment of generated mechanical pairs remain outside this delivered increment.
