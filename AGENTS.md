# Partelier repository guidance

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
  Separate 19-field settings and version-1 delta-tool records; same target bodies,
  two/three native features, guarded timeline-end Edit. See docs/small-details.md.
- `Partelier/partelier/tools/truss/`: pure bounded triangular-window planning and
  one-solid Fusion adaptation. Shares the HTML pattern session, plate inspector,
  cached mesh and same-body Cut persistence. See docs/planar-truss.md for scope;
  shared settings recipe 10 adds truss_bays/truss_axis and reads versions 1–9.
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
- `ui/operations.js` opens exact saved anchors through In this design; Pick from model remains an alternative. Earlier-feature geometry guards remain. Explicit successful Rebuild may adopt exact legacy history; listing never migrates it. See docs/selection-history.md and its native/browser evidence.

## Compact workflow (0.20.0)
- `ui/workspace-flow.js` owns geometry disclosure presentation only. Fold once references are complete; keep multi-face picking open until Done. Change stays open through ordinary edits and reset reopens selection. Never use disclosure state to decide CAD validity or alter settings.
- Startup size is 380 × 760; actual docked height belongs to Fusion. Saved is the header entry point for operations; the alternate model picker is inside it. Examples and all secondary parameters remain available.
- Session revisions are local to their session. On a legitimately adopted new operation, load its settings even if its revision is lower than the previous session's. Continue rejecting retired sessions and older same-session pushes.
- See docs/compact-ui.md and docs/validation/compact-ui-0.20.0.json for scoped checks. Browser screenshots are not native pointer acceptance.
