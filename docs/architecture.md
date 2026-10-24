# Architecture

## Stack and boundaries

Use Python with Fusion's supplied `adsk.core` and `adsk.fusion` API and a local
HTML/CSS/JavaScript palette, as explicitly requested by the user. Native command
inputs handle the existing diagnostic. Hinge and snap-fit picking run directly
from the palette with selectEntity; commits use zero-input native commands.
No frontend framework, backend, database, external geometry library or dependency
installer is needed for the foundation.
The initial supported platform is Windows. The Fusion-embedded Python version
must be recorded during native validation; developer checks use local Python.

| Module | Responsibility |
| --- | --- |
| `Partelier/Partelier.py` | Fusion `run(context)` / `stop(context)` entry points and top-level errors |
| `Partelier/Partelier.manifest` | Unique identity, version and Windows add-in metadata |
| `Partelier/partelier/addin.py` | Register/unregister the command, own event references, select a solid, adapt native inputs and display results |
| `Partelier/partelier/settings.py` | Immutable honeycomb parameters and numeric rules; no `adsk` imports |
| `Partelier/partelier/palette.py` | Own the tool-library launcher, resizable palette and HTML event handler |
| `Partelier/partelier/palette_protocol.py` | Validate allowlisted requests and hinge dimensions independently of Fusion |
| `Partelier/partelier/ui/palette.html` / `.css` | Compact hinge workflow, grouped tool selector, optional guide and readable blue light theme |
| `Partelier/partelier/ui/catalog.js` | Planned-tool content and parameter/workflow descriptions |
| `Partelier/partelier/ui/illustrations.js` | Original explanatory SVG rendering; never used as a geometry planner |
| `Partelier/partelier/ui/palette.js` | Session state, grouped dropdown, guides, illustrative controls and asynchronous bridge |
| `tests/test_settings.py` | Host-independent behavioral checks |
| `Partelier/partelier/tools/hinge/settings.py` / `planner.py` | Frozen dimensions, alternating knuckles and web bounds in mm |
| `Partelier/partelier/tools/hinge/fusion.py` | Selection frame, temporary BRep, custom graphics, owned persistence and recipes |
| `Partelier/partelier/tools/hinge/command.py` | Native Create/Edit command lifetimes, validation, preview and timing |
| `Partelier/partelier/tools/hinge/native_finish.py` | Native finishing of fully joined owned copies, explicit stage-edge membership and cleanup |
| `Partelier/partelier/tools/hinge/native_preview.py` | Zero-input compute Command, detached results and rollback before graphics |
| `Partelier/partelier/tools/hinge/roof_finish.py` | Read-only round/tapered cap-contour witnesses; refusal without geometry repair |
| `Partelier/partelier/tools/hinge/relief.py` | Pure movement-envelope plan and temporary source/leaf relief |
| `Partelier/partelier/tools/hinge/visibility.py` | Scoped persistent-body light-bulb leases; no geometry edits or deletions |
| `Partelier/partelier/tools/snap_fit/` | Independent settings, family dispatch, transient paired geometry, versioned recipes and palette command lifecycle |
| `Partelier/partelier/tools/snap_fit/ball_detent.py` | Spherical detent/socket geometry and its receiver envelope |
| `Partelier/partelier/tools/snap_fit/torsion.py` | Two-post torsion-bar/central-lever plan and detached native primitives |
| `Partelier/partelier/tools/snap_fit/annular.py` | Coaxial cylindrical selection, full-circumference coverage, annular bead and blind groove |
| `Partelier/partelier/tools/snap_fit/finish.py` | Complete convex outer-edge classification after union, protected contacts, bounded exterior cutters |
| `Partelier/partelier/tools/solid_pair.py` | Shared two-target in-place persistence; strict owned BaseFeature/four-Combine records and historical source scope |
| `Partelier/partelier/ui/snap.js` | Independent snap-fit form/session controller; library shell forwards host messages |
| `tools/fusion/HingeFixture/` / `SnapFitFixture/` | Standalone new-document reference fixtures |
| `tools/fusion/SnapFitProbe/` | Fixed rollback-only snap-fit native checks |
| `Partelier/partelier/tools/patterns/auto_fit.py` | Bounded numeric visual-layout scoring, density and exact-size locks; at most two surface-checked proposals |
| `Partelier/partelier/tools/patterns/tiles.py` / `tiled_layout.py` | Convex polygon motifs, inward gap offsets, rounded profiles and bounded multi-tile layouts |
| `tools/generate_pattern_samples.py` | Reproduce local SVG family samples from the real numeric planner |

Fusion requires a matching Python entry point and manifest in the add-in folder.
The bundle uses package-relative imports, following Autodesk's
[Python add-in structure](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/PythonTemplate_UM.htm).

## Current data flow and state

```text
Fusion Run -> register native diagnostic + hinge commands + HTML launcher
  -> local HTML palette -> ready -> actual registered tool capabilities
  -> hinge_begin / hinge_focus -> direct model selection
  -> validated immutable HingeSettings + selected faces/edge
  -> pure plan -> temporary BRep -> sharp Custom Graphics
     or rollback-only native finish Command -> detached BRep -> Custom Graphics
  -> native Create/Rebuild -> revalidate -> owned result feature + recipe
  -> optional diagnostic -> immutable HoneycombSettings -> summary only
Fusion dialog destroy / Stop -> release handlers / remove owned UI
```

The dialog state is temporary. The module retains the registration handler and
one handler collection per live dialog so Fusion callbacks stay alive. Destroy
releases that dialog; Stop removes the owned control and command definition.
Repeated Run is guarded against duplicate registration.

The library has a separate lifetime from the native dialog. Closing it hides it;
the launcher re-shows the same valid palette. If a workspace switch invalidates
it, the next launch creates it again. Stop removes its own palette, launcher,
controls and retained handlers. UI favorites and illustrative dimensions remain
in page memory only and are discarded when the page is recreated.

The user found the original dark theme tiring and preferred a dropdown. The
revised shell uses one native HTML select grouped by tool family, with a Favorites
group when needed. Each tool appears once. Selecting a tool updates the guide
directly; the card gallery, category navigation and search screen were removed.
Only the selected illustration is generated, rather than preparing thumbnails
for the whole catalogue. Wide layouts place image and inputs side by side;
narrow layouts stack them. Detailed guidance is progressively disclosed.

The palette uses the Qt browser option and an absolute local file URI with a
manifest-version query. HTML asset cache tags and displayed version also match
the current manifest version, preventing old HTML from retaining stale assets after
Stop/Run. The HTML
bridge awaits `adsk.fusionSendData`, accepts both its Promise and legacy return
form, and checks a protocol version and request identity. The Python allowlist
permits explicit handshake/diagnostic, hinge begin/focus/status,
update/preview/commit/cancel and legacy Create/Edit actions. Session updates,
previews and commits carry complete settings snapshots plus a UUID and revision;
Python validates/canonicalizes them before model work. No arbitrary command
IDs, paths or generic generation actions are accepted. A bounded handshake reports a
real connection or remains in browser-preview mode. It does not assume success.
See Autodesk's [palette and bridge guide](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Palettes_UM.htm)
and [Palettes.add reference](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Palettes_add.htm).

The hinge protocol keeps model selection and sharp previews on the main-thread
palette path. Finished previews and Create/Rebuild use proper Fusion Commands
for temporary finishing/rollback or owned persistence; HTML never mutates
geometry. Capabilities are present only while the hinge manager is registered. Late requests after
Stop are refused. HTML never calls the model API directly. This UI decision
supersedes the earlier native-only proposal, not the geometry ownership rules.

Native length expressions are evaluated by Fusion. Input `.value` is in internal
centimetres even when the UI displays mm; convert once on entry to pure code.
The hinge geometry adapter converts mm back to cm once before API calls. See
[Autodesk's unit documentation](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Units_UM.htm).

Preview/Cancel persist no model geometry or settings. Finished previews use
rollback-only native transactions with helper-owned copies; custom graphics
are drawn from detached results after rollback. Hinge Create/Rebuild persist owned
result geometry and a versioned recipe; the diagnostic stays read-only. There
are no file exports or network calls. Failure diagnostics and aggregate stage
timings go to Fusion's log; the user receives a short error. Do not log model
contents or add a separate logging/persistence subsystem without a concrete need.

## Planned module boundaries

The sequence and exit gates live in [mvp-plan.md](mvp-plan.md). The structure
below distinguishes implemented hinge/snap modules from future extensions.
Shared core/ and fusion/ folders and other tool folders remain proposals; do not
create them as empty scaffolding. Native acceptance is tracked separately in
[fusion-validation.md](fusion-validation.md).

```text
partelier/
  addin.py                 Thin composition and built-in tool registration
  palette.py               Shared HTML host/lifetime; no tool geometry
  ui/                      Shared shell, catalogue, tool-specific presentation
  core/                    Small host-independent shared contracts, as needed
  fusion/                  Shared units, event lifetime and result ownership
  tools/
    hinge/
      settings.py          Immutable inputs and numeric validation
      planner.py           Immutable geometry plan in mm; no adsk imports
      fusion.py            Selection snapshot, temporary/persistent geometry
      command.py           Fusion selection/command session and UI adaptation
    snap_fit/              Settings, family geometry/selection, finish and commands
    sliding_guide/         Same boundaries when implemented
```

Keep the entry point stable. A small explicit list of built-in tool registrations
is sufficient: unique command identity, label and registration/cleanup hooks.
Each tool owns its parameters, selection rules, plan and recipe version.
The shared launcher/runtime does not implement family geometry. Shared helpers
avoid tool settings and command/UI state; the existing SolidPairStore reuses the
conservative BRep signature helper through a lazy hinge-adapter import. External plugin loading, dependency injection
frameworks, abstract class hierarchies and generic scene graphs are not needed.

Migrate the current honeycomb input check only as far as the hinge integration
requires. It remains an honest diagnostic command until intentionally retired;
renaming its button does not turn it into a generator. Extract duplicated
behavior after a second concrete use demonstrates the shared contract.

## Hinge command and geometry flow

```text
HTML parameters + Fusion-owned selection
  -> validate supported geometry and capture plain immutable data (mm)
  -> pure tool planner -> reviewed plan
  -> Fusion adapter -> temporary geometry + custom graphics
  -> Create: re-read/revalidate inputs and sources, then build owned results
  -> verify result -> publish ownership -> command completes
Cancel / Destroy / Stop / failure -> clear owned temporary state
```

Pure planners describe placement, mating relationships and clearances. They
accept plain data, not Fusion objects or callbacks. The Fusion adapter owns unit
conversion, selection resolution and all model access. Preview and Create use
the same planning and geometry rules, while display simplification, if added,
must be explicit and must not affect final dimensions.

Each command session owns its handlers, selected-source snapshot, reviewed plan,
temporary geometry and graphics. Unrelated status changes must not rebuild
geometry. A changed selection or dimension invalidates the reviewed plan. Avoid
duplicating expensive work between input-change and preview events. Create must
recheck source validity and freshness rather than trusting cached body handles.

Use [Custom Graphics](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/CustomGraphics_UM.htm)
for disposable display. Evaluate
[TemporaryBRepManager](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_TemporaryBRepManager.htm)
for temporary solid operations, outside document persistence/timeline overhead.
Compare it with native sketches/extrusions using the same hinge fixture. A
temporary BRep implementation is a candidate, not an assumed speed winner or
an automatic parametric history. Custom-graphics-only preview must still run
the persistent Create path when the user accepts the command.

## Ownership and editing contract

Attached version 9 output modifies the two selected root bodies in place. An
owned root BaseFeature contains complete final-shape tool bodies and optional
pins. For each target, native Join with keepTools enabled adds the final-shape
tool, then native Intersect with keepTools disabled trims the same target to
that shape. The consumed tool outputs do not leave duplicate final A/B solids
in the Browser. Target identity, name and pre-commit visibility are preserved;
only optional pins add final bodies. Preview preparation may still use copies.

Separate output retains independent A/B leaves and optional pins in an owned
root BaseFeature for Part Designs or a new component for Hybrid Designs.
Attachment geometry and exact limits are in [hinge-design.md](hinge-design.md).
No operation claims ownership of the root component or unrelated geometry.

`BodyVisibilityLease` records explicit native body flags for full-result preview.
Repicking temporarily reveals leased bodies and hides graphics; accepted mode
changes transfer leases. Cancel, failed creation and Stop restore captured flags;
failed restores remain owned and reported for retry. Attached commits restore the
targets' existing visibility rather than retaining hidden backup bodies.

Create revalidates sources and uses a native command transaction. Track the owned
tool feature, combines and pins; clean partial owned objects on failure. Native
operations may replace API handles, so capture and validate the returned target
instead of trusting a stale handle. Undo/Redo still needs native acceptance.

Version 9 attributes store dimensions, logical feature UUID, source references,
targets and exact owned feature/body signatures. Tokens are resolved through the
Design, never compared as stable identity strings. Missing, ambiguous, moved or
modified geometry and unsupported recipes produce actionable refusals.
Opening or previewing a recipe does not migrate its attributes.

Attached Rebuild evaluates original source references before the owned tool
BaseFeature, prepares complete new final shapes, then uses `BaseFeature.updateBody`
on the owned tool sourceBodies. Existing native combines recompute against those
updated tools; Rebuild does not append another pair of result bodies. Stored tool
shapes are snapshots: an upstream model change requires explicit Rebuild to
recalculate them. This is not fully automatic upstream regeneration or a custom
compute feature.

A deliberate Rebuild can migrate legacy attached copy-based output when exact
ownership, safe deletion and native/logical dependency checks permit it. Prepare
and validate before changing the model; remove only the old owned results after
successful integration into the original targets. Restore those targets' intended
visibility. Never delete arbitrary hidden bodies as cleanup. Failure must retain
the previous result and recipe. Separate-leaf rebuild retains its existing owned
replacement contract and Hybrid last-feature restriction.

Version history: split seam introduced v2, distribution v3, separate output v4,
chamfer v5, housing/fillet v6, support v7 and movement relief v8. Version 9 changes
attached persistence, not the meaning of those dimensions. Strict legacy readers
preserve prior shapes until deliberate Rebuild. New attributes use
`sktech_partelier_hinge_8c319ce2`; the strict legacy namespace alias remains.
The rename preserves add-in/tool identities. Save/reopen, changed topology and
deleted-source acceptance must be verified in Fusion.

## HTML hinge session boundary

The palette owns dimensions and grouped presentation. A Python session owns
native geometry references and temporary graphics; native-finished previews use
the tool's short rollback-only compute Command.
Validated full snapshots carry only a session UUID, revision and plain parameters;
no model entity/token is accepted from HTML. Allowlisted selection actions call
[UserInterface.selectEntity](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_UserInterface_selectEntity.htm)
from the palette callback, never from a Command event. The synchronous prompt
waits for a click or Esc; the HTML bridge does not time out interactive picking.
Changing either face clears the reference edge. Sharp preview runs disposable
BRep/custom graphics directly. For a requested finish, `NativePreviewRunner`
queues a zero-input compute Command and custom event, then computes detached
results in executePreview with isValidResult false. A no-op execute rolls back
the preview transaction; graphics are drawn only after command destruction.
Helper-owned model objects exist only within that transaction and leave no
persistent changes. Latest-generation checks discard stale/cancelled work.

Create/Rebuild launches a zero-input native Command with
[isAutoExecute](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Command_isAutoExecute.htm)
true. Adding any CommandInput would display a dialog and must be avoided on this
path. Execute revalidates the full snapshot and sources, persists results in the
native undo transaction, and publishes actual completion. An execute-launch
acknowledgement is not success. HTML and Python block further session actions
while commit is pending. Legacy commands retain their full native controls only
for the compatibility bridge.

Host state is pushed via sendInfoToHTML; its Qt response acknowledgement is not
a user action. Cancel and Stop release temporary graphics/references and pending
compute work. Retained commandTerminated handling checks source freshness after
unrelated commands: unchanged sources retain the preview, while changed or
unreadable sources clear it. Own compute/Create/Edit and picking callbacks avoid
reentrant checks.
[documentDeactivating](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Application_documentDeactivating.htm)
closes the session before document deactivation. No window manipulation or hidden
selection inputs are used. The production compute/graphics/rollback lifecycle
has native evidence; broader selection/Undo/Redo/cancellation checks remain.

Live preview is always on in the HTML session. After begin/focus completes,
HTML explicitly requests hinge_preview with the latest full snapshot. Parameter
edits use a 160 ms trailing debounce, and serialized actions coalesce queued
updates to the newest values. Incomplete geometry uses hinge_update without
kernel work. The native compute driver adds a retained Fusion custom event but
no runtime worker thread. Context checks preserve unchanged document-bound
graphics; changed sources require revalidation before showing them again.

A live hinge_preview request invalidates the generation without first removing
the displayed graphics. Preparation/drawing constructs the candidate before
retiring the prior group; failed preparation keeps the last valid view with an
explicit error. previewCurrent distinguishes current geometry from that view.
Failed retirement cleans or retains ownership of the candidate for cleanup;
Cancel does not claim success when its graphics deletion fails. Refresh retries
a previous preview error. The legacy hinge_update path still invalidates without
building, for incomplete selections and compatibility callers. HTML enables
Create only after the current revision has a successful preview, and cancels
pending refresh timers on Cancel/Create. Preview never persists a result.

The JS bridge accepts pushed state before a request acknowledgment can arrive.
A delayed response cannot regress a same/newer pushed revision from preview or
created to computing/opening. Lower same-session revisions and retired UUIDs are
ignored. Retirement is page-local, preserving fresh-page Connect recovery.
These race cases are exercised by the actual JS DOM fixture; real native session
tests separately verify parameter updates and cleanup.

Recipe version 6 introduced round/square housing profile and analytical
fillet treatment/radius, reading versions 1–5 strictly with the original round
profile and fillets off. `rounding.py` uses only temporary boxes, cylinders,
spheres and tori; it never creates a preview document or persistent fillet
feature. These are historical primitive helpers; current compound finishing
uses the native adapter described below. Square housings are inscribed in the
original circular envelope.

Recipe version 4 added separate output and leaf/hole fields. Version 5 adds
optional general chamfer finish and reads versions 1–4 with finish disabled. Versions 1–3 are read
strictly and default to attached output without mutating saved attributes.
Separate output owns per-placement leaves/pins. Historical attached versions 1–8
owned source copies; version 9 uses the in-place tool/combine contract above.

## Performance approach

- Record separate timings for source reading, pure planning, temporary geometry,
  drawing, persistent creation and rebuild. Use `time.perf_counter()` and a local
  development report; no telemetry service or permanent profiler subsystem.
- Cache unchanged inputs and pure plans within one command session. Cache
  source-derived data only with explicit invalidation. Do not retain live body
  objects across document changes or replace source resolution with assumptions.
- Avoid whole-document scans on each keystroke. Use owned result identity and
  selected sources. Gate invalid inputs before expensive geometry work.
- For dense patterns, count estimated cells/struts and impose a work budget
  before allocating geometry. Reuse shared edges and test batching against
  per-cell native features; require exact supported boundary clipping and
  connected junctions. These are later pattern tasks, not hinge infrastructure.
- Measure before adding debounce, lower-detail display, background work or
  native code. Added complexity must address an observed bottleneck and retain
  correctness, cleanup and error handling.

All Fusion API work belongs on the main thread. Autodesk explicitly warns that
calling its API from worker threads can crash Fusion; see
[Threading](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Threading_UM.htm).
If later measurements justify workers, restrict them to plain-data computation
and return results through a supported main-thread event. Threads are not the
default performance architecture. Do not add C++, NumPy, a remote UI server or external
geometry engines without a measured need and a bounded integration plan.

The baseline protocol and future host acceptance cases are in
[development.md](development.md). No latency target or improvement is validated
yet.

## StructForge reference

The user supplied `C:/tmp/StructForge-joint-refactor` and authorized reuse of
useful techniques and technology. The reference was inspected read-only at HEAD
`9587a0e`, with existing local changes; that SHA does not describe all observed
working-tree content. No reference files were changed or copied into this
project. Its validation results do not validate Partelier geometry.

| Reference | Technique worth adapting | Partelier boundary |
| --- | --- | --- |
| `structforge_src/ui/sketch_constrain_command.py` and `core/sketch_constrain_fusion.py` | Prepare a pure plan, display disposable graphics, recheck it before applying | Hinge-specific native session; prevent duplicate preview rebuilds |
| `structforge_src/core/body_mutation.py` | Distinguish preview/persistent intent; return and validate the current body after mutation | Small explicit operation results; no stale handles or speculative body fallback |
| `structforge_src/core/group_update.py` and `core/group_edit.py` | Preflight ownership/dependencies and defer retirement of old results | Scoped feature Edit/Rebuild with preserved prior results on failure |
| `structforge_src/app.py` | Retain event references; remove owned UI and temporary display during shutdown | Thin lifecycle helpers, without importing its large application controller |
| `structforge_src/core/truss_layout.py` | Pure immutable planar segment planning for Warren/Pratt/Howe/Fan layouts | Revisit at the truss gate; adapt its cm convention to this project's mm contract |

Prefer these patterns before importing implementations. If a small self-contained
algorithm is adapted later, record its origin, unit/identity changes and focused
tests in that task. Use new command IDs and a tool-specific recipe schema. The
reference checkout, its full palette, installers, fabrication workflow and user-data
paths must not become runtime dependencies.

## Testing and distribution

Pure rules/planners use `unittest`; source checks use Python compilation. Native
Fusion events, geometry, cancellation, Stop/Run and later export behavior need
the manual checks in [development.md](development.md). Do not count unit tests
as native validation.

There is no compiled build. Link the self-contained `Partelier/` folder for
development. Distribute that folder only after the corresponding native checks;
an installer, CI pipeline and automatic updates are postponed.

## Tapered attached supports (0.3.2)

`tools/hinge/support.py` owns the adsk-independent tangent profile and its lazy
Fusion adapter for temporary convex prisms. The reference outline is calculated
from the old web outer corner, not hard-coded from the user's model. `fusion.py`
initially routed attached round/tangent requests to it for every knuckle.
Recipe 7 introduced strict `web_profile`, with versions 1-6 expanded read-only to
`flat` for stable legacy geometry. Current recipe 9 retains the recipe 8 tapered/flat webs in
both output modes and housing profiles, and adds `rotation_clearance_mm`.
Versions 1-6 preserve flat webs/zero relief, and version 7 its support shape/zero
relief. Attached taper may extend the source footprint beyond leaf reach;
separate taper remains within reach and protects finished hole lips. Preview
and persistence share the same preparation path.

The support adapter uses only documented temporary primitives and booleans.
The initial analytical chamfer/fillet helpers finished convex support edges;
current finishing is deferred until after the complete join. No print-direction
inference or full rotational sweep is introduced. The read-only native probe
under `tools/fusion/TangentSupportProbe` creates temporary test geometry and a
local report, without changing the active design. See hinge-design.md for the
reference measurements, measured native cases and remaining acceptance scope.

## Joined hinge finish and unattended checks

The current finish path handles the complete raw source/leaf/housing/support union after
holes are cut. `native_finish.py` owns only copied helper bodies/features. Cap
sets disable automatic tangent-chain expansion; subsequent side work matches
frozen original curve supports, excluding newly created blend borders.
Separate tapered necks use 85% of the available hole-safe span so the requested
screw-mouth finish lip remains clear.

`native_preview.py` owns the short rollback-only compute transaction and draws
graphics from detached results after destruction. The same native finish adapter
runs inside Create/Rebuild transactions. `roof_finish.py` checks mirrored
round/tapered roof/cylinder cap witnesses where raw containment establishes the
expected surface. It returns the same solid or refuses a detected C1 valley;
an unproven roof-completion approach was discarded. No refill, alternate finish
or automatic radius reduction is used.

The development-only filesystem/custom-event bridge is outside the product
bundle. Its watcher performs file I/O and event queuing, never CAD work; model
callbacks stay on the main thread. It has run in Fusion without PC input.
Check a fresh bridge status before submitting a request; setup, commands,
fixtures and report locations are in
[fusion-validation.md](fusion-validation.md).

Historical 0.4.3 native request `3902166f-b114-4da6-b55b-a6a4cb445bea` on Fusion 2705.1.30 /
Python 3.14.0 passes 47 stated expectations: 40 generated matrix cases, six
explicit 0.6 mm fillet refusals and one saved two-hinge workflow. It also passes
three actual Edit previews (five to three knuckles, length 40 to 36 mm), Cancel,
two New previews, final cleanup and a commit storing length 36 mm with two
hidden source backups. Earlier independent Part Design rebuild preserves the
later fixture; a forged logical dependency is refused before replacement.

The additional finish completes before Cancel is handled, so the drained result
does not establish interruption of running native computation. The production
preview/graphics/rollback path passes without runtime errors. All six original
user bodies, topology, history and visibility match after rollback and explicit
fixture-visibility cleanup. The 461 Python tests, Node DOM race/session suite,
compilation and whitespace checks pass separately.

The new 0.5.0 persistence has separate native evidence: request
`9a1e8b26-7909-4f1a-b43b-7fb1deec501b` passes 53 stated expectations on Fusion
2705.1.30. It covers 40 generated geometry cases, six explicit larger-fillet
refusals, six in-place/migration cases and one programmatic production-session
workflow. Four attached treatments each pass four Rebuilds without replacing
the selected targets or growing history. The existing model and topology match
after rollback. All 480 local Python tests, Node DOM/syntax and compilation pass.

Existing saved results change only on deliberate Edit/Rebuild. Actual CEF
picking/palette, manual navigation, new queued-native-preview cancellation,
save/reopen, Undo/Redo, broader failure/dependency/topology acceptance, motion
and physical printing remain outstanding.
Historical 0.4.2 used a different three-hinge chamfer fixture. Full historical
inputs, source hashes and current acceptance status are in
[fusion-validation.md](fusion-validation.md).

On this host, custom-event queue calls return `False` despite delivered handlers.
The runtime does not treat that return alone as failure; registration/event-ID
checks and real API exception handling remain. The product adds no worker or
generic scheduling framework.


## Second geometry tool (0.6.0)

Snap-fit is a separate tool module and UI controller. Palette requests retain
UUID/revision/full-settings guards; capability flags depend on started managers.
Only one tool owns picking/preview at a time. The existing hinge controller and
persistence remain in place. Snap reuses the proven transient box/prism and
appearance/outline rendering helpers, plus scoped visibility leases.

`SolidPairStore` provides tool-neutral persistence for two existing root solids.
Each tool gets its own attribute namespace and tool ID; pair ownership metadata
is separate from its settings/source recipe. Native history updates the same
selected bodies through a two-tool BaseFeature and four Combines, rather than
creating final copies. Rebuild replaces the two source shapes without appending
history. Historical reads always restore the previous marker.

The fixed development bridge now allowlists joined_finish and snap_fit and
hashes all runtime Python plus both static probes. Its watcher still handles
only files and queued events. Every snap native fixture/persistence test runs
in a rollback-only host command and checks the original document afterwards.
See [snap-fit geometry and limits](snap-fit-design.md).


## Snap mechanism families and exterior finishing

The snap tool has one immutable 21-field settings contract and four concrete
mechanism families: Hook latch, Ball detent, Torsion latch and Annular ring.
Straight/tapered/twin are variants of Hook latch, not alternate names for those
families. The common Fusion adapter dispatches geometry while the shared palette,
preview, historical-source and two-body persistence protocols remain the same.
No framework for external mechanism plugins is introduced.

Hook, ball-detent and torsion families use coplanar wall faces and a canonical
straight facing rim. Pure placement produces repeat centers and root/receiver
coverage requirements in millimetres. The ball adapter supplies a spherical nose
and enlarged socket; the torsion adapter supplies two posts, a round Y-axis bar
and a central lever with an air gap above the fixed root. Each family provides
its own mating envelope and temporary geometry, then the common adapter checks
original-source/free-nose contact and final-pair clearance.

Annular selection has its own contract: native outer cylindrical face A, coaxial
inner cylindrical face B, and a complete circular rim on the selected A face.
The frame origin is that rim center; the axis sign places neck A in negative
local Z. The exposed bead starts and ends at A's radius over the requested axial
width; its embedded root extends inward by attachment overlap. Changing overlap
does not reshape the exposed triangle. The peak radius exceeds the positive
A/B radial gap. Two frustums form the triangular
bead, and annular cutters form B's groove and optional 45-degree roof in local
+Z. Full-circumference intersection witnesses require the entire root, remaining
socket wall, groove floor and roof extent. Annular requires one ring and general
outer chamfers off. Both source and final pairs undergo positive-overlap checks.
Planar and annular features retain different source contracts when editing.

The outer-finish helper inspects the actual united generated detail, after all
of its root, arms, hooks and supports have joined. It classifies complete convex
eligible planar edges, merges continuous collinear segments with matching
incident normals, and builds explicitly bounded cutters. Free fork-slot edges
are eligible. At the free tip, side cutters extend analytically to the inclined
nose rather than stopping at the trimmed edge endpoint and creating a triangular
cap. Only that runout may cross the wall plane, above the retaining shoulder;
the embedded root remains protected. At a concave slot foot, an intersection of
two short adjacent cutter extensions joins both bevel faces without moving a
horizontal end cap into the root. Any incident inward/negative-X surface and the flat
retaining/contact shoulder are protected. The receiving body B is not
cosmetically finished: equal family/dimensions/support settings produce identical
B with outer chamfers on or off. Unsupported or oversized finishing is refused;
no edge size is silently reduced. Curved family components retain their own
profile/selection rules.

After the planar cutters, the complete sphere or torsion-bar primitive is united
back into the generated detail. This protects the round core even where a
neighboring planar-edge cutter crosses its envelope. Native intersection-volume
checks prove that the entire primitive remains present. The torsion root and
posts share their full outer depth to avoid a small construction step and broken
finish band at a post foot.

The fixed native probe checks whole trimmed inner/contact surfaces and the
entire B geometry against sharp baselines, in addition to material witnesses
across root/arm/hook joins and the free tip. This catches partial inside bevels,
changed mating edges and broken outside finish bands rather than treating a
successful boolean alone as acceptance. Native evidence is recorded separately;
these geometry checks do not validate physical printing, force or fatigue.

The HTML controller serializes all 21 typed fields atomically and displays the
controls relevant to the selected family. Version 3 recipes store this exact
schema. Version 1's eleven dimensions are interpreted as straight Hook latch
with sharp edges and print support off. Version 2's fifteen fields retain their
saved hook variant and finish/support values while acquiring explicit Hook latch
family defaults. Legacy parsing is read-only: dimensions can be loaded without
rewriting the recipe or changing existing geometry. Deliberate Rebuild writes
the current version, updates the same BaseFeature tool sources and retains both
selected bodies and the four native Combine references.
