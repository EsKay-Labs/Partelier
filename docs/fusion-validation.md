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
