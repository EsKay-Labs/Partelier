# Script-driven Fusion validation

The development validation bridge runs native checks without controlling the
mouse, keyboard, windows, browser, or document activation. It is outside the
installable Partelier bundle and starts only when explicitly run in Fusion.

## One-time setup

In Fusion, open Utilities > Scripts and Add-Ins > + > Script or add-in from device.
Select the folder `tools/fusion/PartelierValidationBridge` in this repository and
Run **PartelierValidationBridge**. Leave Fusion idle between ordinary commands.
After updating a loaded bridge, Stop then Run it once. The status advertises its
supported scenarios; the CLI rejects snap_fit against an older loaded bridge.
There is no need to reload the product add-in to load the development bridge.

From the repository, using the same normal user temporary directory as Fusion:

```powershell
py tools/run_fusion_validation.py status
py tools/run_fusion_validation.py submit --scenario joined_finish --no-wait
py tools/run_fusion_validation.py submit --scenario snap_fit --no-wait
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
