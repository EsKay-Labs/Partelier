# Script-driven Fusion validation

The development validation bridge runs native checks without controlling the
mouse, keyboard, windows or browser. The pattern workflow also creates and
discards its own unsaved test document, then restores the original document,
component and camera. It is outside the
installable Partelier bundle and starts only when explicitly run in Fusion.

## One-time setup

In Fusion, open Utilities > Scripts and Add-Ins > + > Script or add-in from device.
Select the folder `tools/fusion/PartelierValidationBridge` in this repository and
Run **PartelierValidationBridge**. Leave Fusion idle between ordinary commands.
After updating a loaded bridge, Stop then Run it once. The status advertises its
supported scenarios; the CLI rejects new scenarios against an older loaded bridge.
There is no need to reload the product add-in to load the development bridge.

From the repository, using the same normal user temporary directory as Fusion:

```powershell
py tools/run_fusion_validation.py status
py tools/run_fusion_validation.py submit --scenario joined_finish --no-wait
py tools/run_fusion_validation.py submit --scenario snap_fit --no-wait
py tools/run_fusion_validation.py submit --scenario patterns --no-wait
py tools/run_fusion_validation.py submit --scenario pattern_status --no-wait
py tools/run_fusion_validation.py submit --scenario pattern_display --no-wait
py tools/run_fusion_validation.py poll REQUEST_UUID --timeout 60
```

The CLI does not launch Fusion or control its interface. A fresh `ready` status
confirms that the bridge is loaded. `unavailable` means its one-time Run is still
needed. A busy Fusion command is left alone and eventually returns `blocked`.
CLI timeout leaves the request queued; inspect/poll that UUID before resubmitting.

The queue and atomic reports live in `%TEMP%/PartelierValidationBridge`. Each
request has a UUID, a fixed scenario and a per-Run session UUID (protocol 2). The
CLI submits only against a fresh running bridge session. Requests from earlier
Runs are cancelled rather than replayed. Paths, arbitrary commands and executable
code are rejected. A file watcher only reads plain files and queues a custom
event; all model access stays on Fusion's main thread. Stop removes its own
handler/watcher and cancels waiting jobs. An active probe receives a cooperative
cancellation signal; queued geometry/runtime-preview work checks it before
computing, and only the probe's own commands are closed. Its final cancelled
report is published after owned-command cleanup and rollback checks. An old
completion cannot reset a newly started bridge session. CLI timeout still leaves
a request pending within the current session; Stop cancels it. No external
connection is used.

## Balanced preserves requested Cell size (0.10.8)

Balanced previously enlarged openings to satisfy its 48-cell soft budget. On
large faces, several smaller Cell size values therefore produced the same result.
It now keeps opening size fixed and increases center spacing in both directions.
The minimum-gap and border checks still apply. Only Automatic size treats the
opening dimension as a target. The help comparison uses equal opening sizes and
different gaps, and Balanced status reports size plus approximate nominal grid gap.

Native request `4f7faa52-5984-4346-ac51-5f465d8a7f86` passes on Fusion 2705.1.30.
The production Session prepares and displays a 200 × 160 mm panel, then performs
Create, Edit and Rebuild. Requested/actual opening size changes from **12.5 mm**
(45 cells) to **5 mm** (33 cells); both layouts remain within 48 cells. Body
identity, body count and three owned history features remain stable. Preview
export scratch history rolls back, all 12 cached display cycles pass, and the
original model/document/camera are restored without cleanup errors. Runtime and
probe hashes are retained in the [scoped evidence](validation/pattern-balanced-size-0.10.8.json).

Local validation passes **876 Python tests**, all **three Node DOM suites**,
compilation and whitespace checks. New regressions cover five shapes, clipped
and whole cells at 5/10/20 mm below the same large-face spacing floor, wrap size
and gap preservation, correct status text, and one preview request for each size
edit. Headless Edge at 300/380/520 px verifies help bounds and Esc dismissal;
the help screenshot was inspected. These checks do not establish actual Fusion
CEF interaction acceptance, globally optimal packing or physical printability.

## Partial edge cells and stable controls (0.10.7)

New patterns use **5 mm Minimum gap**, stable **Cell size / Minimum gap / Border**
labels in every layout mode, and **Clip at border**. Recipe v3 persists the edge
mode; old v1/v2 recipes load as Whole cells only without being rewritten.

Native matrix `f599e771-e708-493e-a60f-4c89a6cce753` passes **61 geometry and
production cases** on Fusion 2705.1.30, including all five clipped shapes in
Through/Engrave/Emboss, cylinder end-rim clipping, a two-face faceted hex body,
finite notches, an existing round hole and clipped-cell Create/Edit/Rebuild.
The five flat-shape cases retain partial cells (4 or 7 per fixture), and the
notched panel retains 45 cells. Convex pieces from one lattice cell are counted
once; gap checks still compare distinct cells.

This matrix is **not an overall successful run**: its final snapshot check found
an active app preview had disappeared and its hidden source body had become
visible after document deactivation. Body geometry, attributes, count, timeline
and marker match exactly; the difference was limited to preview graphics and
source visibility. The subsequent read-only status showed the app session canceled.
The evidence retains the original failure flag rather than treating it as a pass.

Independent display request `5b7851a5-5081-4c92-9c20-243241d1151c` then **passes**
with the same runtime/probe source manifest: 12 cached display cycles plus the
actual rollback `_Session.prepare` / standard STL export / Create / Edit /
Rebuild workflow using the new clipped defaults. The original model and camera
are restored exactly and cleanup reports no errors. No direct native mesh
calculator is introduced.

Local checks pass **874 Python tests**, three Node DOM suites, compilation and
staged whitespace checks. New checks cover convex subtraction/merging without
filling holes, closed convex trim offsets, partial cells for all shapes and
layouts, minimum polygon separation, finite notches/holes, recipe v1/v2 reads,
5 mm defaults and unchanged labels. Headless Edge at 300/380/520 px confirms the
controls, independent size/gap edits, help bounds and Esc/focus return without
page errors; screenshots were inspected. This does not claim actual Fusion CEF
interaction acceptance or physical printing validation.

The first two native candidates refused at fragmentation bounds for a round
hole and multiple notches; closed-loop offsets and convex merging resolve those
fixtures. A later legacy fixture incorrectly inherited Clip mode and was made
explicitly Whole to preserve its original complete-cell contract. These earlier
results remain identified in the [scoped evidence and source hashes](validation/pattern-clipped-cells-0.10.7.json).

## Illustrated pattern help and independent cell size (0.10.6)

Final native request `2611bd09-3a25-4612-ade3-9251935ae9e8` passes **41 cases**
on Fusion 2705.1.30 with an unchanged runtime source manifest. The initial run
`e55ff647-9c20-4552-a693-81ad634f26ff` also passes 41 cases, before the final
Balanced status-text adjustment. Nine new cases cover all five Fill shapes on a
plane, exact fixed-size full-cylinder wraps for Through/Engrave/Emboss, and the
less dense Balanced default. All previous geometry and production async cases
remain in the matrix.

The plane Fill cases retain 5 mm elements with a 1.5 mm minimum gap; the
cylinder cases retain 6 mm elements while closing the circumferential seam.
Fill Create/Edit/Rebuild retains settings, body identity and owned history.
The 300 × 170 mm notched-panel default produces **43 cells**, within the new
48-cell soft per-face budget. All native preparation guards run, the owned
scratch document is discarded, and the original model/component/camera are restored.

Local validation passes **862 Python tests**, all **three Node DOM suites**,
compilation and whitespace checks. New checks cover polygon-to-polygon gaps,
whole-cell borders, fixed wrap size, density refusal, legacy golden geometry,
actual size status, all 12 help buttons, no CAD dispatch from help, and size/gap
independence through invalid intermediate edits.

A separate headless Edge 135 browser check at 300/380/520 px verifies dialog
bounds, Esc/focus return, backdrop closing, extra-details disclosure and size/gap
conversion without page errors. Screenshots were inspected. This is browser QA,
not acceptance of the actual Fusion CEF palette or model picking. User acceptance
of the previous cached preview/orbit implementation remains recorded below.

See [source hashes and scoped evidence](validation/pattern-help-fill-0.10.6.json)
and the [layout behavior and limits](surface-patterns.md). Fill uses complete
cells with conservative checks, so the requested border is a minimum. It is not
a clipped full-surface fill or a globally optimal packing solver.

## Cached export display (0.10.5)

Live sessions now cache display triangles with Fusion's standard STL exporter.
They do not access the direct native mesh-manager/calculator path implicated by
the abandoned experiments. A source guard rejects temporary export bodies;
exact CAD is copied into one owned BaseFeature during rollback computation,
exported in centimetres as binary STL at Medium refinement, then removed.
Native wrapper references, including exception traceback frames, are released
before their owner is deleted. The temporary directory is also removed.

Plain validated arrays survive rollback. One opaque mesh reuses the source
appearance, and one batched outline retains trimmed edge clarity. Shallow joins
use angle-weighted normals, with sharp edges retained. Create and Edit/Rebuild
continue to consume exact BRep geometry; recipes/settings are unchanged. A local
AST guard excludes the failed API calls from the exporter and fixed probe.

The fixed **pattern_display** scenario now explicitly exercises this different
standard-export route. A dry run imports no Fusion API. Native runs use an owned
unsaved document and three export/draw/cleanup repetitions each on a box, a
192-opening plate, a cylinder and a sphere. Six fixed camera refresh samples per
cycle compare the plate with its original BRep display. The actual Session.prepare
then runs inside the production rollback runner, followed by cached drawing,
same-body Create, Edit preparation inside another rollback command, and Rebuild.
The probe verifies scratch cleanup, target/anchor identity, history/body counts
and restoration of the original model/camera. Durable checkpoints precede native
export operations and display phases. The user model is never used as a fixture.

Final source-identical native runs pass **36 display cycles** and **three complete
Create/Edit/Rebuild workflows** in the same Fusion process, with original state
restored after every run. In the final paired run, the plate's original camera
refresh averages 157.1 ms over six samples, versus 5.3 ms over 18 cached-export
samples. Initial display capture averages 526.6 ms on that fixture. Raw paired
samples for all three runs are retained; the first run overlapped local CPU tests,
so aggregates include varying host load. Local checks pass **854 Python tests**,
all three Node DOM suites, compilation and syntax.

See [exact verification and source hashes](validation/pattern-display-0.10.5.json).
These are scripted camera refresh timings, not a universal interactive FPS or
stability guarantee. On 2026-10-24, the user confirmed that orbit is smooth in
the actual pattern preview after reloading 0.10.5, closing the reported orbit
issue. Broader palette/surface acceptance and physical printing remain separate. The earlier native geometry matrix remains historical: the
surface/planner/boolean algorithms were not changed by this display work.

## Historical preview orbit investigation (0.10.4)

The 0.10.4 user session confirms a completed preview of 193 cells: 3,801 ms of
geometry preparation and 1,056 ms of initial graphics drawing. No new geometry
preparation ran while the user orbited. Orbit becomes responsive after Create,
which removes the custom graphics and persists the native result.

A development attempt to capture display triangles from temporary geometry
crashed Fusion. A second approach used a document-owned copy and removed its
owned BaseFeature after copying the mesh arrays. Short native comparisons
passed, including actual Session.prepare, drawing, Create/Edit/Rebuild, cylinder
and sphere displays, and restoration of the original model/camera. On a plate
with 192 openings and 774 faces, six synchronous camera refresh samples averaged
144.3 ms for BRep graphics and 5.7 ms for cached triangles. Disabling graphics
selection alone averaged 139.4 ms, which did not solve the problem.

A later run of the second approach also crashed Fusion. Its last checkpoint was
`mesh_manager`; `mesh.calculate` was never reached. This brackets obtaining and
configuring the native calculator, not one proven faulting call. Windows
reported heap corruption (`0xc0000374`, `ntdll.dll`) for both crashes. The good
isolated timings do not establish repeated-run stability or interactive FPS.

At the end of that investigation, all candidate rendering code was removed and
the product was restored to 0.10.4 with orbit lag unresolved. The display probe
was disabled to prevent replay. Those direct-calculator prototypes remain only
under ignored local `output/native/` for investigation. The subsequent 0.10.5
standard-export implementation is a separate route, described above; it does
not restore the failed calculator calls.

[Investigation record](validation/pattern-display-investigation.json).

## Pattern selection return (0.10.4)

The user reproduced the reported loading state with 0.10.3 diagnostics enabled.
The actual native trace shows one accepted face, a ready state, and a second
blocking `selectEntity` call. The original `pattern_begin` request had not
returned, so the UI could not request preview. No geometry preparation had
started. The previous instructions required Esc to finish multi-selection, but
the UI hid those instructions after the first selection and showed updating.

Picking now returns after one face, allowing the begin/focus acknowledgment and
then automatic preview. An explicit **Add face** action adds one face on the
same solid; **Faces** replaces the selection. Duplicate picks and Esc keep the
selection. Preselected multiple faces, body scope and saved-pattern Edit remain
available. Selection status and help stay distinct from computation.

Local regression checks cover the first-click-to-preview boundary, adding,
replacement, cancellation, duplicates, cross-body refusals and scope guards.
All **846 Python tests** and three Node DOM suites pass, along with syntax,
compilation and whitespace checks. The browser checks cover the Add face request
and one subsequent preview, keeping the selected state while picking, and hiding Add face in Body/Edit. These are
controlled API/DOM checks; they do not substitute for post-reload native picking.
The 0.10.3 log establishes the cause in the actual user session. The user
confirmed the preview after reloading 0.10.4. Native logs show one
completed pick, successful preparation/drawing of 193 cells and a current preview,
followed by successful Create. The separately reported orbit lag is a display
performance issue, not another selection wait.
See [selection verification record](validation/pattern-selection-0.10.4.json).

## Local interaction diagnostics (0.10.3)

Reload **Partelier** once, close Scripts and Add-Ins, and reproduce the actual
interaction. No development bridge is needed for logging. Native records are
written immediately to `%LOCALAPPDATA%/Partelier/logs/partelier.jsonl`. The file
rotates at 2 MiB with three backups. Every record includes UTC time, monotonic
time, a per-start run UUID and sequence number. Startup records identify the
disk version and loaded instrumentation build; browser boot records identify
the loaded UI build separately.

The pattern UI traces handled clicks, capture-phase pointer presses on disabled
controls, input changes, lock states, request IDs, queued actions, bridge replies,
timeouts, state pushes and reasons for rejecting stale states. Native traces
cover request entry/return/errors, preselection, each blocking `selectEntity`
call and its return, selected counts, command/custom-event lifecycle, compute
callbacks, geometry stages, individual kernel calls, periodic cell progress,
batch fallback, drawing, commit and cancellation. A queued driver call is logged
separately from actual event delivery, so lack of delivery is distinguishable
from a long geometry call.

Browser records use a bounded 80-entry in-memory/localStorage ring and batches
of at most ten entries. A strict read-only `diagnostic_log` endpoint validates
the batch independently of model actions. Diagnostic sends run outside the
geometry queue and never await their own acknowledgments. Missing diagnostic
replies and file I/O errors cannot fail CAD work. A complete bridge failure may
prevent browser batches reaching the file; native request records and the
browser's local ring provide separate evidence of that boundary. Validated saved
entries replay after reopening the panel, preserving their original browser
timestamp and adding `replayed=true`.

Logs stay on the local computer. They include settings, session/request IDs,
state transitions, source file paths and exception text; the UI trace excludes
body names, selection labels, entity tokens and geometry. Logs are ignored by
Git and are not included in committed validation evidence. The logging changes
do not claim to fix the reported interactive selection hang: the actual
reproduction is needed to identify its cause. Previous 0.10.2 geometry evidence
remains historical and separate from diagnostic transport/lifecycle checks.
Local checks pass **839 Python tests** and all three Node DOM suites, including
rotation, concurrent whole-line writes, strict diagnostic payloads, I/O failures,
runner trace order, disabled-control capture and missing diagnostic replies.
[Diagnostic verification record](validation/diagnostics-0.10.3.json).

## Pattern preparation performance (0.10.2)

Native request `f83e77f7-8151-4b0f-95d2-3bedd2ef37f2` passes **32/32** named
cases, including 20 direct-prism subcases and the complete earlier surface,
persistence and async workflow matrix. The original model/document/camera/display
snapshot matches after rollback and source references remain valid.
[Exact evidence and tested source hashes](validation/patterns-0.10.2.json).

The same owned 300 × 170 mm notched-panel fixture with 195 Through cells measured
8,295.6 ms preparation before the changes and 4,001.6 ms afterwards, in separate
native invocations. Drawing and viewport refresh added 1,847.7 ms in the final
run: approximately 5.85 s for preparation plus drawing, not an instant preview.
The old/new preparation comparison is approximately 2.07× on this fixture;
hardware, source complexity and warm-up affect these numbers.

Within the final invocation, forcing the exact sequential fallback measured
5,904.0 ms versus 4,001.6 ms with batching. Batch and fallback have matching
bounds and common material volume, and independent material witnesses confirm
all 195 cell openings. Through aggregation uses 194 unions on copied tools and
one final Difference; touching/overlap or a refused native operation keeps the
original inputs for exact sequential fallback. The existing first-wall checks
still run on every cell witness.

The 20 prism subcases cover all five footprints, two rigid frames and two depth
intervals. Shared topology, outward normals, bounds, analytic volume, common
material volume and inside/outside witnesses match the earlier clipped prisms.
All 20 new temporary bodies also survive command rollback. Planar trims retain
real hole/border checks while eliminating redundant curvature-ring evaluations;
curved charts retain the ring. Engrave reuses only exactly identical wall rays.

Through preparation uses temporary BRep and creates no timeline features.
The completed pattern still uses its three owned persistence features and
supports Edit/Rebuild. Preparation, wall, tool-construction, tool-clipping,
result-application and drawing timings are now available in the Fusion log and
the read-only status diagnostic. All **827 Python tests**, three Node DOM suites
and JavaScript syntax checks pass. Geometry evidence remains separate from
physical printing and broad manual CEF interaction acceptance.

## Pattern palette recovery (0.10.1)

A read-only inspection of the reported stuck session found a finished native
preview with 182 cells, a current result and no running or pending computation.
The loading indicator was stale UI state. The browser controller now recovers
lost preview acknowledgments/completion pushes using the existing read-only
`pattern_status` action, outside the serial geometry queue. A matching completed
state can release an outstanding preview acknowledgment. Recovery never
recalculates geometry or commits the result.

The development bridge also adds a fixed `pattern_status` diagnostic scenario
to inspect this distinction without running fixtures or closing a preview. Only
this read-only scenario may run during another active native command. It locates
the product by its exact local module path and reports session/runner lifecycle
flags. This is separate from the browser action with the same name. Reload the
bridge once to advertise the new scenario; older bridge sessions keep their
previous allowlist. Diagnostic reports remain local and may contain selected
body names and settings.

All **797 Python tests**, three Node DOM suites and JavaScript syntax checks pass.
The browser regressions cover missing preview acknowledgments, missing completion
pushes, queue release, stale responses, one in-flight status query, bounded
read-only query timeouts and retirement of polling after Cancel. Geometry and
Create are never retried by this recovery path.

The corrected 0.10.1 palette was then reopened through its own native API. The
real HTML `ready` handshake returned the same current 182-cell preview. The
original native session, detached result and preview graphics retained their
identities; the model/history/visibility/graphics snapshot matched before and
after. This one-time UI check ran instead of the geometry matrix and its
temporary probe hook was removed afterwards. The public record omits user paths,
names, selected references and settings. [Recovery evidence](validation/pattern-preview-0.10.1.json).

The CAD adapter, planner, persistence, native rollback driver and fixed geometry
matrix are unchanged from 0.10.0. Its 30 native cases remain the geometry evidence;
the UI recovery regressions separately simulate missing, delayed and stale
messages. Native palette reconnection and local DOM checks do not establish
manual CEF clicking coverage for every interaction.

## Balanced patterns and finite trim boundaries (0.10.0)

Native request `dcfc7f44-3c31-4c30-92ba-393bd219b11b` passes **30/30** cases on
Fusion 2705.1.30. [Exact evidence](validation/patterns-0.10.0.json) records all
44 native-tested source hashes. The original document, component, camera,
geometry, attributes, visibility and graphics match the initial snapshot after
the disposable test document is discarded. Source references remain valid.

An owned 300 × 170 mm panel with three small top slots tests the reported gap:
both Exact pitch and Automatic cut actual material in its left, middle and right,
while retaining the real slot borders. Automatic produces 27 cells at 41.8106 mm
from a 40 mm target, with equal opposite outer margins of 4.9026 and 6.3788 mm.
The finite-edge checks avoid Fusion's point-to-edge measurement of the infinite
supporting curve; line endpoints and conservative cached curved-edge strokes
retain the real trim extents.

A dense 1 mm Automatic target resolves to 174 cells at 1.8565 mm without changing
the target setting. Create/Rebuild retains the same body and three owned
features. Full-cylinder Automatic layouts pass Through, Engrave and Emboss with
52 cells at 7.7332 mm and equal cyclic gaps across the seam. Legacy version 1
settings read as Exact pitch without rewriting attributes, then migrate to a
complete version 2 snapshot only on deliberate Rebuild. All previous positive
geometry, bounded refusal, production async preview and cached-Create cases
remain covered.

Six native captures restore the view after each capture. The new panel and
cylinder captures were visually inspected. Local checks pass **792 Python tests**,
all three Node DOM suites and **36 responsive UI combinations**: two widths,
three tool presets, three actions and two spacing modes. These browser checks
remain separate from manual Fusion CEF acceptance. Automatic native positives
cover planes and cylinders; the regular cone/sphere positives use Exact pitch.
Physical-web and distortion refusals remain in force for curved regions.

The first run of this same matrix passed its 29 geometry/preview cases but failed
the final original-display comparison: switching documents cancelled an already
open product preview, revealing its source and removing its own graphics group.
No original geometry, history or attributes changed. The identical clean rerun
above passed all 30 cases without weakening the restoration checks.

## Pattern density guidance (0.9.1)

Native request `8f0fc496-26bc-48b2-a682-2bafacca6d0c` passes **24/24** cases,
including the complete previous pattern matrix and production preview workflow.
[Exact evidence](validation/patterns-0.9.1.json) matches all 44 historical native-tested
source files. A dense single-face fixture is refused with clear repetition
counts and an approximate Pitch hint; applying its suggested 2.4 mm instead of
1 mm produces 84 accepted layout cells, below the 200-cell limit. The original
settings and model remain unchanged. Local checks pass 760 Python tests and
all three Node DOM suites. The surface-area hint is explicitly approximate and
does not automatically change a design or remove the existing work limits.

## Surface patterns (0.9.0)

The final fixed `patterns` scenario passes **23/23** native cases in Fusion
2705.1.30. [Exact evidence](validation/patterns-0.9.0.json) covers all 44 runtime
Python/fixed-probe files. Its source manifest was checked again before saving.

Plane, half-cylinder and two adjacent hex walls pass all three operation modes.
A full cylinder passes all three modes with 36 cells, including real material
witnesses on both sides of the parameter seam. The half-cylinder independently
retains the unselected opposite wall. All five shapes pass; positive cone
engraving (85 circles) and sphere engraving (48 hexagons) verify regular curved
regions without accepting a refusal as success. Borders and retained floors
have independent point-containment witnesses.

Create and three mode-changing Rebuilds retain the same body and three owned
features, with body/face/edge/feature selection accepted for Edit. The actual
production preview runner supersedes an obsolete request, delivers only after
native rollback and retains fresh source references. A later native command
creates from that exact detached cached result and then rolls back completely.
Its disposable document is discarded without saving; the original document,
active component, camera, attributes, geometry, lightbulbs and graphics match
their initial state. The fixed matrix also rolls back every owned fixture.

Four exact native CAD captures were visually inspected; camera, visibility and
graphics restore after every capture. They are included in the
[pattern guide](surface-patterns.md). Local validation passes **757 Python tests**,
three Node DOM suites and 18 responsive browser combinations (360/540 px,
three presets and three modes), with no overflow or JavaScript errors. Browser
and fake-host tests are distinct from the native CAD evidence.

Measured preparation times in this fixture run:

| Fixture | Cells | Through / Engrave / Emboss |
| --- | ---: | --- |
| Plane | 5 | 0.11 / 0.22 / 0.19 s |
| Half cylinder | 15 | 0.49 / 0.72 / 0.36 s |
| Full cylinder | 36 | 1.26 / 2.31 / 0.85 s |
| Cone, circles | 85 | Engrave 24.78 s |
| Sphere, hexagons | 48 | Engrave 2.59 s |

These are measurements, not latency guarantees. Dense curved circles remain a
performance limit. Pole/distortion exclusion, conservative complete-cell
borders, segmented circle/slot boundaries and one-root-solid selection remain
explicit limits. Manual save/reopen, Undo/Redo and physical printing are still
separate acceptance work.

## Free-tip corners and fork-slot finishing (0.8.1)

Native request `c70ed109-a193-4420-b3a9-e9059db42d14` passes **56 cases** on
Fusion 2705.1.30. [Exact evidence](validation/snap-fit-0.8.1.json) records all 34
runtime/probe hashes, protected contact geometry and material checks. The combined
SHA256 is `e7a4edd109db288313948609200a2027c9f02ed7c583cd3f3e81319bdb7de2c6`.
The user's original model, history, topology references and visibility remain
unchanged after fixture rollback.

The previous 48 cases now also check the inner fork-front edges at the requested
chamfer size. Material checks prove that the tip-side cuts meet the inclined nose
without triangular end caps, while the mating face and retaining shoulder retain
their complete original trims. A concave fork foot receives the intersection of
the neighboring bevel cutters, so the new inside finish does not leave a horizontal
end cap at its lower end. The Twin visual fixture has zero axis-aligned triangular
faces after finishing. Its exact Fusion screenshot is in ignored
`output/native/snap-hook-A-0.8.1.png` and was visually reviewed.

Eight additional cases vary straight/tapered/twin profiles, repeated clips,
torsion latches, 0.01/0.6 mm clearance and 0.3/0.4 mm chamfers. The small-clearance
case checks the nose runout across the wall plane; it stays above the retaining
shoulder. All existing receiver, round-core, Create/Rebuild and migration checks
remain in the run. **676 Python tests**, both DOM suites and all 80 Python-file
compilation checks pass. Physical printing and the other manual acceptance limits
listed below remain unverified.

## Historical four snap mechanisms and protected finishing (0.8.0)

Final native request `403a3f13-dc02-4507-805f-6ed61a449f7b` passes all **48**
checks on Fusion 2705.1.30. [Committed evidence](validation/snap-fit-0.8.0.json)
records the exact cases, protected-surface fingerprints and round-core volumes.
All 32 runtime Python files and both fixed probes retained the tested raw bytes;
their combined SHA256 is
`a3d5faa919c100852d2f6493a64b359e0b1dee90b24766c81b9bff847e146f94`.
The complete local envelope is `output/native/snap-fit-0.8.0-full.json` (ignored).

The 22 geometry matrix cases cover Hook latch's three variants, Ball detent,
Torsion latch and Annular ring, with print roofs and supported outer chamfers
on/off. The remaining cases cover repeated placement, in-place Create/Rebuild,
planar-family changes on the same history, guarded invalid dimensions, gaps/lips,
production logical sessions and read-only v1/v2 loading followed by v3 migration.
All Create/Rebuild cases retain their selected A/B identities and owned Combines.
The original user document, topology references, history and visibility match
their pre-test snapshot after fixture rollback.

The chamfer regression checks compare complete trimmed inner/catch surfaces and
the entire receiver against sharp baselines. Independent material samples bracket
the requested equal setback along root/arm/hook joins and the free end; Twin's
inside-gap edges and receiver web are protected, including a 0.75 mm outer finish.
Entire sphere/bar intersection volumes prove that neighboring planar cutters do
not remove their functional round cores. Annular witnesses near both requested
axial ends distinguish the full-width bead from the previously buried profile.

Eight native images show A and B separately for all four families. Their capture
temporarily hides the other scene bodies/graphics and restores the exact camera,
visibility, appearance count and graphics count in `finally`; all four restoration
checks pass. Images in ignored `output/native/snap-*-A-0.8.0.png` and
`snap-*-B-0.8.0.png` were visually reviewed. These checks use Fusion's scripting
API without mouse, keyboard, window or document-activation control.

**672 Python tests**, both DOM suites, 80 Python compilation checks and JavaScript
syntax checks pass. Headless Edge renders all four families at 360 and 540 px
without page errors or horizontal overflow; the full-width type selector and
family-specific forms were visually inspected. Native handler-binding refusal
and partial setup tests prove that an empty failed commit can close without
persisting geometry or permanently blocking the palette.

Physical printing, assembly forces, fatigue, chosen slicer orientation, manual
CEF picking, save/reopen and Undo/Redo remain outside this evidence. Print roofs
assume local +Z build-up. Historical reports below describe their original scope;
0.7.0's finishing witnesses did not catch the partial/internal bevel defects now
covered by the complete-edge and protected-surface regressions.

## Historical snap-fit types and printing details (0.7.0)

Native request `da972d4b-b91b-4bfa-93f1-854eaa128f4e` passes 27 cases on Fusion
2705.1.30. [Committed evidence](validation/snap-fit-0.7.0.json) records all cases,
source hashes, result volumes, repeated native reference checks and limits.
The combined tested source hash is
`8dde80647fae1cf9580d0942cf31e824ddc654ddd75400cfbbaa087708d63313`
for 29 runtime Python files and both fixed probes.

The 12 geometry matrix cases cover three arm types with chamfers and print ramps
each on/off. Native point-containment witnesses check the actual taper, two arm
slots and remaining receiver web, retaining catches, arm gaps, 45-degree root
ramp and receiving roof. Chamfer witnesses bracket the requested equal-setback
size at the outer arm and recess-mouth sides; chamfered versions remove material
relative to their exact same sharp baselines. Rebuild changes type and finish
three times while preserving the same two bodies, BaseFeature and four Combines.
Gap/lip cases and production logical session preview/update/Cancel/Create/Edit
remain covered. Oversized chamfers are explicitly refused without changes.
A version 1 recipe reads without modifying geometry or attributes, then a
successful deliberate Rebuild stores a complete version 2 snapshot.

Read-only diagnostic `37e275f1-08f1-4988-a7c7-ebc57f772f3a` loads the user's
actual version 1 snap with its sharp/support-off settings intact and prepares all
three new styles with 0.3 mm chamfers and print ramps. All six result solids are
valid single solids. The temporary geometry stage is approximately 47–70 ms on
this model; this excludes drawing/persistence and is not a general speed bound.
The four snap runtime hashes match the matrix run. No actual user Rebuild is
performed, and the original model/history/display snapshot remains unchanged.

629 Python tests, both DOM suites, JavaScript syntax and Python compilation
checks pass. A separate headless 540×840 browser rendering has no page errors or
horizontal overflow and was visually inspected. The browser screenshot is
ignored local evidence in output/native/snap-styles-ui.png. This is separate from
manual CEF interactions. The ramps assume local +Z printing from A toward B;
physical printing, chosen bed orientation, deformation/forces, save/reopen and
manual Undo/Redo remain unverified. Historical results follow.

## Gap rims and internal lips (0.6.1)

Final native request `6711587d-71da-4023-8926-b6ca1c65ce56` passes all eleven
snap-fit cases, including two new Create/Rebuild scenarios with a 0.3 mm gap:
a rim picked on the lid maps to the base rim, and internal tongue/groove lips
extend across the exterior seam without being rejected by whole-body bounds.
The final paired solids have verified clearance, the original body identities
remain, and the user's original geometry/history/display snapshot matches after
rollback. [Evidence and exact hashes](validation/snap-fit-0.6.1.json).

Read-only diagnostic `acabaf11-2242-42a3-a64d-906f4d7d79ae` also prepares the
user's actual failed selections with the same final geometry-adapter hash. The
selected lid edge at Z=170.15 mm maps to the base edge at Z=169.85 mm; the
existing inner lips are retained. Both candidates remain one solid. This check
creates no persistent geometry and leaves the document snapshot unchanged.
Persistent body tokens and model details are omitted from committed evidence.

615 local Python checks and both DOM suites cover the revised behavior. Startup
now displays the palette after registering the managers; repeated start re-shows
it, while startup display failure cleans up for retry. Lifecycle coverage does
not simulate manual native Run/Stop or CEF clicks. Existing print/motion and
save/reopen/Undo/Redo limits still apply. Historical 0.6.0 evidence follows.

## Exterior snap-fit (0.6.0)

Final native request `54536e93-be12-418f-86c9-9f83d0bbe872` passes nine named
cases on Fusion 2705.1.30. The
[committed evidence](validation/snap-fit-0.6.0.json) contains inputs, native
point-containment witnesses, outcomes and exact runtime/probe source hashes.
Hashes describe the exact tested working files; Git checkout line-ending
conversion can change raw-byte hashes without changing the Python code.
The combined SHA256 is
`252d81b2011a272517dd315f8d0f76670d38a1b7c37941190c4593f1463f65d7`.
The bridge hashes all 28 runtime Python files and both fixed probes, verifies
that they are unchanged when the run completes, and rejects arbitrary paths or
code in requests. The full local envelope is in ignored
`output/native/snap-fit-0.6.0-full.json`.

| Cases | Verified result |
| --- | --- |
| Default / three clasps | Beam material, exterior gap, hook engagement, receiving clearance and remaining back wall at stated sample points |
| Create in place | Same two selected bodies, names and visibility; no duplicate final bodies |
| Rebuild with later independent history | Same BaseFeature and four Combine references, changed dimensions/count saved |
| Short rim / thin wall / short receiving face | Explicit refusal before persistent changes |
| Production logical session preview/update/Cancel | New dimensions reach the preview; exact snapshot and visibility restored |
| Production logical session Create/Edit/Rebuild | Body selection loads saved dimensions; new count reaches rebuilt geometry; no remaining preview groups |

All native persistent work runs inside one outer rollback-only command. After
its empty execute/destroy, original bodies, topology counts, timeline, marker,
appearance count and graphics flags match their original snapshot. Original
body/face/edge references remain valid; detached temporary results remain valid
solids after rollback. No document is saved.

606 Python tests and both Node DOM suites pass separately, with JavaScript
syntax and Python compilation checks. The session probe calls production
logical sessions inside its outer transaction; it does not simulate manual CEF
picking or clicking the Create button. Unit/DOM checks cover the zero-input
commit wiring, request ordering, stale settings and cleanup failures. Manual
CEF behavior, save/reopen, Undo/Redo, arbitrary enclosure geometry, assembly
force and physical printing remain outside this result. The tool's first family
and its geometric limits are specified in [snap-fit-design.md](snap-fit-design.md).

## Preview appearance correction (0.5.2)

Native request `c4c7d61f-99f5-44aa-8327-2b000097ae14` renders transient copies of
the actual user's current outputs with their existing Fusion appearances,
explicit opacity 1.0, and three batched black outline entities. It verifies all
three native AppearanceColorEffects and opacity overrides. Steel - Satin is
confirmed. Captured before/after images were visually inspected: the corrected
preview retains the material and crisp black boundaries of the normal model.
Draw time was about 75 ms for this model; it is not a general performance bound.

The test restores the existing preview-group and body visibility, checks that
owned graphics are removed, and leaves the body's geometry/history/visibility
snapshot unchanged. The document appearance count remains 1. No document is
saved and the diagnostic flag is restored afterward. All 16 hinge runtime
hashes match the tested code. See
[preview-appearance-0.5.2-summary.json](../output/native/preview-appearance-0.5.2-summary.json),
[before](../output/native/preview-appearance-0.5.2-before.png) and
[corrected preview](../output/native/preview-appearance-0.5.2-after.png).

491 Python tests, the Node DOM suite, JavaScript syntax and compilation pass.
Tests cover A/B appearance selection, component material for generated bodies,
fully opaque nonselectable graphics, historical source resolution, trimmed-edge
batch indices, seam/degenerate-edge exclusion and plain Shaded display. This is
a display-only check; the full geometry matrix was not repeated. Body-level
appearance is supported; individual face overrides and other styles/materials
remain unverified visually.

## Selection loading correction (0.5.1)

The live user session retained a valid `adsk::fusion::Component` named
`(Unsaved)` as its Edit target. Its load failed, then automatic preview cleared
the original error and replaced it with the generic dimensions-loading prompt.
Edit now resolves a root Part only when it contains exactly one owned hinge
recipe. Body, face and edge picks retain exact body ownership validation;
multiple hinges require a specific body or pin. A single existing selection is
adopted when opening Edit. A separate load-error field survives preview retries,
parameter changes and an aborted repick, and clears on a successful repick.

Native diagnostic request `c09556d3-da05-43a6-8ae0-ccea900475cb` on Fusion
2705.1.30 reads the actual user's Part, resolves its v9 hinge and loads all saved
dimensions in the actual isolated production `_Session`, reaching `ready`.
The before/after body, volume, topology-count, history and visibility snapshots
match. No geometry is created or rebuilt. All 16 hinge runtime source hashes
match the diagnostic; the temporary diagnostic flag was restored afterward.
The compact record is
[edit-selection-0.5.1-summary.json](../output/native/edit-selection-0.5.1-summary.json).

Local checks pass 487 Python tests, the Node palette session suite, JavaScript
syntax and compilation. New checks reproduce lost load errors, reuse a single
preselection, refuse ambiguous Parts, retain legacy ownership validation and
resolve v9 Component/face/edge picks. Interactive picker/CEF confirmation remains
separate; the geometry matrix below was not repeated for this selection fix.

## Current 0.5.0 native evidence

Version 0.5.0 changes attached persistence to recipe 9: the selected root A/B
bodies become the hinge-bearing bodies, preserving identity, name and visibility.
An owned tool BaseFeature feeds native Join/Intersect features; consumed tools
leave no additional final A/B solids. Only optional pins add bodies. Separate
leaves keep independent output. Rebuild updates owned tool sourceBodies rather
than appending another result pair; upstream edits require explicit Rebuild to
recalculate these stored shapes.

Final request `9a1e8b26-7909-4f1a-b43b-7fb1deec501b` completed successfully on
2026-10-22 in Fusion 2705.1.30: **53 stated expectations, zero failures**. Payload:
`%TEMP%/PartelierValidationBridge/probe/9a1e8b26-7909-4f1a-b43b-7fb1deec501b.json`.
Its `results/` envelope hashes 17 runtime/probe files with source-set SHA-256
`574fc11a4d8a92af02dbd1d6135f02bede6bf6a175118530beb218726a0ad874`.
The compact local record is
[inplace-0.5.0-summary.json](../output/native/inplace-0.5.0-summary.json).

| Check group | Result | Scope |
| --- | --- | --- |
| Generated geometry | 40 positive cases | Attached/separate, round/square, supported treatments and translated/rotated frames; declared sizes match the matrix below |
| Larger-fillet limits | Six verified refusals | Explicit 0.6 mm limits below; these are not successful geometry generations |
| Native combine algebra | One case passed | Join/Intersect consumes final tool outputs, preserves original targets/names/counts and supports updating the consumed tool sources |
| Attached production fixtures | Four cases passed | Sharp, 0.3 mm chamfer, 0.2 mm fillet and square housing; each Create plus four Rebuilds preserves target identity/name/visibility, expected body counts and timeline count |
| Legacy attached migration | One case passed | Old owned copies removed, same original targets integrated and visible, recipe 9 readable from the original body |
| Actual production sessions | One workflow passed | New preview/Create; Edit/update/preview/Rebuild; Edit/preview/Cancel restores previous geometry/history/visibility/recipe and retains original targets |

The four attached production fixtures start with two 35 mm hinges, 10 mm end
margins and a split seam. Their four successive edits are length 32 mm/three
knuckles, pins disabled, three 20 mm hinges/pins enabled, then one 45 mm hinge.
Pin counts follow the requested output; no duplicate main bodies or history
accumulates. Edit preparation and graphics leave persisted snapshots unchanged.
The production Session fixture uses 0.3 mm chamfers and changes length to 30 mm
with three knuckles before Rebuild; a later 28 mm preview is cancelled.

All tests run inside a rollback transaction using disposable owned fixtures.
The existing user model snapshot and original topology references match before/
after; detached prepared solids remain valid after rollback. No document is saved
and no mouse, keyboard or window control is used. Source-hashed runtime modules
are loaded fresh for the request. Local checks separately pass 480 Python tests,
the Node DOM/syntax suites, compilation, 59 Python AST checks and 71 direct
formatting checks.

This evidence uses programmatic selections and direct production Session calls;
it does not exercise the real CEF palette/picker, manual orbit/navigation, new
queued NativePreviewRunner delivery or interruption/cancellation of a running
native operation. The root context was tested without claiming coverage of all
document intents. Save/reopen, Undo/Redo, broader failure/dependency/topology
acceptance, motion sweeps and physical printing remain pending. The historical
0.4.3 report below remains separate evidence for its former copy-based workflow.

## Historical native scenario and 0.4.3 evidence

`joined_finish` loads the actual runtime adapter, builds raw joined
source/leaf/housing/support copies and holes, and calls the native finish adapter.
It checks connected solids, static separation, pin/bore dimensions, screw-hole
middles and mouths, selected junctions and shared tangent contours. These are
bounded geometry checks, not printability, strength or a complete motion sweep.
The development scenario is
[JoinFinishProbe.py](../tools/fusion/JoinFinishProbe/JoinFinishProbe.py).

The probe uses an undoable preview transaction followed by an empty execute.
Temporary helper features are deleted, preview work is rolled back, and detached
BRep copies are checked after rollback. Original bodies, visibility and history
are compared before/after. No source body is edited and no document is saved.
The report identifies the actual source hashes and fails if source changes during
the run. Runtime modules use a fresh namespace for every request.

Final request `3902166f-b114-4da6-b55b-a6a4cb445bea` completed successfully on
2026-10-22, Fusion 2705.1.30 / embedded Python 3.14.0. Full payload:
`%TEMP%/PartelierValidationBridge/probe/3902166f-b114-4da6-b55b-a6a4cb445bea.json`.
The `results/` envelope records individual file hashes and source-set SHA-256
`c4ffd8559dc60346db5398e131a7b29daa8d01cb60c564010165e846d9e0d671`.
The compact local record is
[joined-finish-0.4.3-summary.json](../output/native/joined-finish-0.4.3-summary.json).

| Check group | Result | What passed |
| --- | --- | --- |
| Positive geometry matrix | 40 generated cases, zero failures | Attached rectangular: 16; separate rectangular: 16; separate rounded: 8, across identity and translated/rotated frames |
| Larger-radius limits | Six explicit refusals, zero generated results accepted | Round/flat attached, round/flat separate and round/tapered separate, each requesting 0.6 mm fillets in both frames |
| Saved two-hinge recipe | One actual workflow passed | Prepare, temporary Create, Read/Edit, temporary Rebuild, read-rebuilt and actual session commit with edited settings |
| Real session sequence | Five current previews passed | Edit: five to three knuckles, then length 40 to 36 mm; Cancel; New: five to three knuckles; Cancel |
| Attached commit visibility | Passed | Two original source bodies retained and hidden; saved edited length is 36 mm |
| Earlier independent Part Design result | Passed | Earlier root BaseFeature rebuilt; later fixture recipe, geometry and counts stayed unchanged; forged logical dependency refused before replacement creation |
| Production preview lifecycle | Passed without runtime errors | Actual `NativePreviewRunner`, full-result custom graphics, no-op execute and detached-body survival after rollback |
| Original model preservation | Passed | All six original bodies, topology references, history and visibility matched after rollback and explicit fixture-visibility cleanup |

All 47 geometry/limit/recipe checks passed their stated expectations: 40 positive
generated cases, six verified refusals and one saved-recipe workflow. The five
real session previews and cleanup checks provide additional lifecycle evidence;
this does not mean 47 successful geometry generations.

The final additional finish completed before Cancel was handled.
`session_cancel_completed_early` and `session_cancel_drained` are both true:
the run verifies a clean closed state without a late resurrected session, not
interruption of an executing native kernel operation. Operations were rolled
back and fixture visibility explicitly restored; no document was saved.

### Fixture dimensions and limits

The base matrix uses 40 mm length, five knuckles, an 8 mm barrel, 3 mm pin,
0.3 mm diametral bore clearance, 0.3 mm axial gap, 0.3 mm movement clearance,
12 mm leaf reach and 2 mm thickness. Separate leaves include screw holes.
The requested finish sizes are:

| Fixture | Requested finish |
| --- | --- |
| All positive chamfer cases, including rounded leaves | 0.3 mm equal-distance chamfer |
| Attached round/tapered | 0.6 mm fillet |
| Separate round/tapered | 0.2 mm fillet |
| Round/flat, attached or separate | 0.2 mm fillet |
| Square housing, tapered or flat, attached or separate | 0.4 mm fillet |

Rounded separate outlines were tested with chamfers. Rounded outline plus
all-corner fillet is an invalid combination and was excluded from the positive
matrix. The fixture radii above were explicitly requested before computation;
the runtime did not reduce a requested radius.

At the additional 0.6 mm limits, round/flat attached and separate fixtures were
refused by native fillet errors. The separate round/tapered fixtures were refused
by the read-only C1 contour guard after the native kernel removed required roof
material. These six refusals are documented limitations, not generated successes.
No analytic refill, silent radius reduction or substituted finish was used.

The saved recipe starts with two 40 mm hinges, 11 mm start/end margins, five
knuckles, an 8 mm barrel, 3 mm pin setting, generated pins, split seam and sharp
edges. The real Edit session previews five then three knuckles and changes length
to 36 mm; its actual commit stores the edited length and hides two retained
source bodies. Earlier-independent-root and logical-dependency checks are part
of this saved-workflow case. Existing saved results change only on deliberate
Edit/Rebuild.

Historical 0.4.3 local validation passed 461 Python tests, the Node DOM race/session
suite, compilation and whitespace checks. These remain separate from the native
report. Version 0.4.3 is experimental: actual interactive picking, the complete
palette workflow, document save/reopen, Undo/Redo, motion sweeps and physical
printing still need acceptance.

Historical 0.4.2 request `e01c5d7f-aba5-4fe6-a3fe-21fdc06d2846` passed its 47
expectations with a different saved three-hinge, 60 mm / 0.8 mm chamfer recipe;
its record is
[joined-finish-0.4.2-summary.json](../output/native/joined-finish-0.4.2-summary.json).
Earlier `4094200b-b4a0-46c7-8150-ed0ad5c003bb` recorded 25/33 checks with eight
round-housing finish failures on earlier code/fixtures. The 0.4.3 positive sizes
and larger-size refusal checks are declared separately above.

### Historical 0.4.3 runtime files and guards

- [visibility.py](../Partelier/partelier/tools/hinge/visibility.py) leases only
  explicitly captured body light-bulb flags. Attached preview hides sources and
  Edit also hides the prior owned result while full replacement geometry is
  drawn. Repicking temporarily reveals the captured bodies; mode changes
  transfer the lease when the replacement preview is accepted. Cancel, failed
  creation and Stop restore prior leased flags; restoration failures remain
  owned and are reported for retry. Successful attached commits keep the source
  bodies as hidden rebuild backups: body count retains them, with no source
  geometry overwrite or deletion.
- [palette.js](../Partelier/partelier/ui/palette.js) preserves newer pushed state
  against delayed acknowledgments, rejects older revisions and retired UUIDs,
  and permits fresh-page Connect recovery. Local DOM tests exercise callback
  ordering; native session checks do not substitute for interactive CEF picking.
- [palette.py](../Partelier/partelier/palette.py) loads the top-level HTML with
  the manifest-version query. HTML asset tags and displayed UI version are 0.4.3
  to prevent an older cached palette after Stop/Run.
- [fusion.py](../Partelier/partelier/tools/hinge/fusion.py) checks exact result
  ownership, native safe deletion and logical recipe references before replacing
  an earlier independent Part Design root result. Hybrid results retain their
  last-feature restriction.
- [native_finish.py](../Partelier/partelier/tools/hinge/native_finish.py) finishes
  fully joined copied bodies. Cap sets disable automatic tangent-chain expansion;
  frozen original side-curve supports prevent later stages from treating newly
  created blend borders as original sharp edges.
- [roof_finish.py](../Partelier/partelier/tools/hinge/roof_finish.py) only checks
  mirrored planar-roof/cylinder cap witnesses on detached solids. It refuses a
  detected C1 valley and returns the same unmodified solid on success. An
  unproven roof-completion approach was discarded.
- [native_preview.py](../Partelier/partelier/tools/hinge/native_preview.py) and
  [command.py](../Partelier/partelier/tools/hinge/command.py) own the compute,
  rollback, session and custom-graphics lifetimes.
- [planner.py](../Partelier/partelier/tools/hinge/planner.py) reserves the screw
  mouth's finish lip: the separate tapered neck uses 85% of the available
  hole-safe span. Requested hole and finish dimensions stay unchanged.

### Custom-event delivery on the tested host

In the native runs, `Application.fireCustomEvent` returned `False` for the probe's
initial, runtime-start and runtime-finish events even though their retained
handlers ran. The runtime therefore does not classify that return alone as a
queue failure. It retains/checks registration and uses the registered event ID;
actual API exceptions still fail the request with an explicit diagnostic. This
is observed Fusion 2705 behavior, not a general guarantee that every queued
event will be delivered.

## Technique provenance

The user requested the same unattended test approach used in StructForge. Its
`structforge_src/core/validation_bridge.py` and development documentation were
inspected read-only. Partelier independently implements the filesystem queue +
Fusion custom-event technique with its own IDs and one fixed probe. No StructForge
code, scenarios, fixture results or checkout changes are included.
