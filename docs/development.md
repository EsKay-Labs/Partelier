# Development and checks

The current implementation is experimental 0.5.0 with recipe 9 in-place attached
output. Its final native report passes 53 stated expectations and current local
checks pass 480 Python tests. Scope and remaining acceptance are recorded below.
The 0.4.3 results are historical evidence for the previous copy-based architecture.
Older increment sections retain their historical test counts and restrictions.

Selection loading in 0.5.1 accepts the enclosing Part only for a unique owned
hinge, reuses a single preselection, and preserves the actual load error across
preview retries. The isolated native Edit session reaches ready on the actual
user model without geometry changes; 487 local tests pass. See the scoped
[evidence](fusion-validation.md#selection-loading-correction-051).

## Run and reload

Fusion supplies the application Python runtime and Autodesk API. Link the
repository's `Partelier/` folder through Scripts and Add-Ins, choose the Add-Ins
entry and Run, then open **Partelier: Tool library** or **Partelier:
Check honeycomb inputs** in the Design workspace Add-Ins panel. Partelier is the
approved product and bundle name.
Dialog labels differ between Fusion versions; Autodesk
documents [linking local add-ins](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/WritingDebugging_UM.htm).

After code changes, Stop and Run again. If imported modules remain cached,
restart Fusion. No hot-reload framework or automatic installation is included.
The manifest keeps Run on Startup off during this experimental development stage.
The top-level HTML URL, four local asset cache tags and displayed version use
the manifest version (0.5.1), so Stop/Run does not retain older cached HTML.

## Local checks

Run from the repository root:

```powershell
py -m unittest discover -s tests -v
node tests/test_palette_ui.cjs
py -m compileall -q Partelier tests tools/fusion
git diff --check
```

`py` selects a locally installed developer Python. The initial check environment
is Python 3.13. On other systems use `python` if necessary. No pip dependencies
are needed. Bytecode caches are ignored. No separate build or linter is
configured; compilation is a syntax check, not lint or API execution.

Unit tests cover finite/positive dimensions, invalid wall/cell relationships,
preserving a positive opening without unconfirmed printer-specific restrictions,
and the cm-to-mm boundary. The UI increment adds malformed/unsupported bridge
message cases and fake-host checks for idempotent registration, palette
recreation, Stop/Run, partial teardown failure and explicit diagnostic launching.
The fake host supplies an API-shaped test double, not Autodesk's runtime. No
local test generates geometry or confirms native Fusion behavior.

After JavaScript changes, run `node --check` on `catalog.js`, `illustrations.js`
and `palette.js` under `Partelier/partelier/ui/`, then exercise the UI in a
browser. The Node DOM suite also runs the actual palette script against a
minimal host/DOM fixture: early pushes, delayed acknowledgments, lower revisions,
retired sessions, Edit/Cancel/New and fresh-page Connect recovery. Node is a
development tool, not an add-in dependency.

`git diff --check` checks tracked/staged differences; it does not inspect ordinary
untracked files. During the initial bootstrap, newly created files are also
checked directly for whitespace, valid JSON and local documentation links.

## Current 0.5.0 acceptance

Attached output must retain the two selected root bodies' identities, names and
visibility. Only optional pins add final bodies. Rebuild updates the owned tool
BaseFeature and recomputes the native Join/Intersect features without growing
body/feature counts. Preview and Cancel remain transient. Legacy migration must
remove only strictly owned old results, integrate the original selected bodies,
and refuse unsafe native/logical dependencies before destructive changes.

Final request `9a1e8b26-7909-4f1a-b43b-7fb1deec501b` on Fusion 2705.1.30 passes
53 stated expectations: 40 positive geometry cases, six explicit larger-fillet
refusals, one native combine-algebra case, four attached production fixtures,
one legacy migration and one programmatic production-session workflow.

Sharp, 0.3 mm chamfer, 0.2 mm fillet and square-housing fixtures each pass four
Rebuilds: changed length/knuckles, no pins, three hinges, then one hinge. Original
target identity/name/visibility and final counts remain correct; Rebuild does
not grow timeline history. Preview leaves persisted snapshots unchanged. The
migration removes only old owned output and reveals the integrated originals.
The actual Session workflow passes New preview/Create, Edit/update/preview/
Rebuild and Edit/preview/Cancel, with the same target identities and restored
state on Cancel. The existing model snapshot and topology match after rollback.

All 480 Python tests, Node DOM/syntax checks and compilation pass separately;
59 Python files parse and 71 code/assets pass direct formatting checks. The final
report covers 17 source files; hash and full evidence are in
[fusion-validation.md](fusion-validation.md).

Selections are programmatic; this is not actual CEF interaction/picking or a new
queued NativePreviewRunner/cancellation test. Manual navigation, full palette,
exception/failure recovery, save/reopen, Undo/Redo, motion and printing remain
acceptance items. Stored complete tool shapes require explicit Rebuild after
upstream changes. Native evidence is bounded to the tested root context; do not
infer that every document intent, topology or dependent model was validated.

## Historical 0.4.3 contract and native evidence

Final request `3902166f-b114-4da6-b55b-a6a4cb445bea` passes on Fusion 2705.1.30 /
Python 3.14.0. Its 47 case expectations comprise 40 generated cases, six explicit
0.6 mm fillet refusals and one saved two-hinge workflow. Refusals are limits,
not generated results. Five actual session previews pass: Edit five to three
knuckles, length 40 to 36 mm, Cancel, then New five to three knuckles and Cancel.
A real commit stores length 36 mm and hides two retained sources. The additional
finish completes before Cancel; drained cleanup is verified without claiming
interruption of running native computation.

Earlier independent Part Design root rebuild also passes, preserving the later
fixture; a forged logical dependency is refused before replacement creation.
All six original user bodies, topology, history and visibility match after
rollback and explicit fixture cleanup. The production preview/graphics/rollback
path has no runtime errors. Full inputs, hashes, bridge commands and reports are
in [fusion-validation.md](fusion-validation.md).

Attached preview draws the full candidate and temporarily hides explicit sources;
Edit also hides the previous owned result. The session and `visibility.py` helper
record original body flags, restore captured visibility for repicking and
transfer leases on accepted mode changes. Cancel, failed creation and Stop restore captured preview flags; failed
restores are reported and retained for retry. Successful attached commits keep
original bodies hidden as rebuild backups. Geometry is not overwritten/deleted,
and body counts include those backups. Separate mode leaves source visibility
unchanged. Hybrid Edit remains last-feature-only; earlier independent Part Design
root Edit needs exact ownership, native safe deletion and logical source checks.

Historical 0.4.3 local checks passed 461 Python tests, the Node DOM suite, three JS syntax
checks, compilation and whitespace checks. All 16 native-tested file hashes
match the final report. Important files are `ui/palette.js` and `palette.py` for
state ordering/cache versions; hinge `command.py`, `visibility.py` and `fusion.py`
for full previews, visibility and safe replacement.

Actual interactive picking, the complete CEF palette workflow, Undo/Redo,
document save/reopen, motion and physical printing remain pending. Use a
disposable Design for the additional manual checklist below; record build,
embedded Python, platform, exact inputs and observations.

| Check | Expected behavior |
| --- | --- |
| Link and Run | Partelier loads and adds exactly one input checker and one Partelier library launcher |
| Open with a Design document | Native dialog shows solid selection, two mm inputs and current capability text |
| Select a box; cell 10 mm, wall 1.2 mm | Check inputs displays the selected name and exact mm values; model remains unchanged |
| Enter explicit inch expressions | Summary shows equivalent mm values, without a tenfold conversion error |
| Missing selection, surface or mesh | Valid execution is unavailable; only closed BRep solids are accepted |
| Zero/negative/invalid expressions; wall equal to or above cell size | Invalid inputs cannot execute; correct errors are visible |
| Change values repeatedly | Status updates correctly without repeated-event recursion |
| Cancel and reopen several times | No geometry/settings writes and no duplicate controls or growing retained dialog list |
| Stop with this dialog open | Own command closes, own button is removed; no unrelated command is terminated |
| Run, Stop, Run | Exactly one checker and one library launcher remain; callbacks work after reloading |
| No active Design document | Explain that a Design document is needed; no executable input check |

The following manual palette checks remain beyond the scripted session evidence:

| Check | Expected behavior |
| --- | --- |
| Open the library | Local HTML/CSS/JS, 12 menu entries and the selected concept image load; live handshake reports registered capabilities |
| Resize / dock | The persistent tool dropdown and stacked/side-by-side image/input layout work without horizontal clipping |
| Browse tools | Grouped dropdown/favorites work; only hinge Create/Edit become available in Fusion; other tools remain disabled |
| About > input checker | The one existing native diagnostic opens; no other command is selected by HTML |
| Close and reopen palette | One valid palette is re-shown, with one retained HTML handler |
| Switch workspace and return | Launcher recreates an invalidated palette; no stale-object exception |
| Stop / Run, including an open checker | Owned palette, launcher, native checker and handlers are removed/recreated without duplicates; unrelated UI is preserved |
| Cancel / close / browse | No preview geometry/recipes survive; captured preview visibility restores; committed attached targets retain their intended visibility |

## UI increment evidence

For the original card-based prototype on 2026-10-21, 18 local tests passed,
Python compilation passed and all three
JavaScript syntax checks passed. Browser interaction checks on the loopback-only
preview passed search and empty results, category counts, selected-tool content,
favorites add/remove, separated illustrations, hinge slider/reset behavior,
the About dialog and disabled model/diagnostic actions outside Fusion. The
1280 px wide view and 540 px palette view were checked, including no page-level
horizontal overflow and narrow guide/back navigation. These are browser results,
not native palette or CAD evidence. Direct file-URL loading in the in-app browser
was blocked by its URL policy; it was not validated there. The tested preview
uses the optional development server described in [README.md](../README.md).

The subsequent UI revision replaces that dark gallery with a soft light theme
and grouped native dropdown. The Python bridge and geometry scope are unchanged.
JavaScript syntax and HTML reference/formatting checks passed. Browser checks
passed selection across all four tool families, matching tool content, favorites
add/remove with exactly 12 unique menu entries, illustration controls/reset,
Ctrl/Cmd+K focus and guide expansion/reset on tool change. The 1280 px view used
side-by-side panes and the 540 px view stacked them, with no page or workspace
horizontal overflow. About/Close worked, Create and the browser-only diagnostic
remained disabled, and the browser reported no script warnings/errors. Native
Fusion acceptance is still pending.

SVG concept meshes are original explanatory artwork. They are not valid solid
models, planners, fit evidence or exportable CAD. Favorites and uncommitted HTML
hinge inputs are session-only. The later hinge implementation adds validated
tool-specific launch requests; only the native command can persist geometry.

## Experimental hinge implementation

See [hinge-design.md](hinge-design.md) for the exact fixture and acceptance table.
The code includes pure planning, native selection/preview, result ownership,
copy-based Create and constrained manual Edit/Rebuild. A standalone fixture
script creates a new unsaved document for native validation. Current scripted
geometry/session results are recorded above; remaining interactive and physical
gates are distinct, and are not inferred from fake-host tests.

For this development run the `py` launcher reported no installed Python. Checks
used the existing bundled interpreter at
`C:/Users/SKTech/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`.
This does not become an add-in dependency. Use `py` or an available `python` for
normal local checks. Compilation also includes `tools/fusion` for the fixture.

Local verification on 2026-10-21 used Python 3.12.14: all 80 standard-library
tests passed, compilation of `Partelier`, `tests` and `tools/fusion` passed,
and the three UI JavaScript files passed `node --check`. Formatting, manifests,
35 local documentation links, 33 unique HTML IDs and four local asset references
were checked. `git diff --check` passed, although the repository still has no
tracked baseline. Browser interaction checks passed all 12 hinge inputs,
positive-value validation, tool switching and disabled CAD actions outside
Fusion, with no script warnings/errors. These checks do not execute Autodesk's
modeling kernel. Native validation is pending because no running Fusion host
was available during this development run.

Native limitations to exercise: active root/history/end-of-timeline, coplanar
co-oriented source faces, straight A boundary edge, positive web overlap,
temporary-body minimum-distance measurement, empty Boolean outcomes, result-body
mapping after BaseFeature edit, source tokens after save/reopen, cleanup and
Undo/Redo. Hybrid Edit requires an unmoved/unmodified single owned occurrence
at the timeline end. Part Design permits an earlier independent root BaseFeature
after native and logical dependency guards; the marker must be at the end.
September 2026 safe-deletion API support is required. Unknown recipes, altered
owned results and unsafe dependencies are refused before replacement.

Successful actual preview/Create/Rebuild logs aggregate stage timings only.
Native performance baseline, physical fit and rotational motion are unvalidated.

Check source preservation by comparing geometry, tokens, counts and history.
During attached preview/commit, visibility intentionally changes under the
documented lease/backup policy; compare final cleanup against captured flags.
The current native report establishes its declared geometry/session cases only.
Broader failure/Undo/Redo, performance baselines and slicer checks remain needed.

## Approved-name rename evidence

The approved Partelier name now covers the UI, P monogram, Fusion display
names, command IDs, bundle entry files and Python package. The add-in
manifest UUID is unchanged. New hinge ownership uses the current namespace;
a read-only legacy alias requires the recipe, feature and body owner tags
to come from the same namespace. Duplicate or mixed ownership is refused.

All 84 local tests passed after the bundle/package rename, including four
new compatibility checks. Python compilation, all three JavaScript syntax
checks and whitespace checks passed. Browser checks from the new absolute
path passed the Partelier title/header/About, P monogram, tool switching
and disabled CAD actions outside Fusion, with no script warnings/errors.
Current UI evidence is saved in output/ui/partelier-branding.jpg; prior
captures are explicitly historical under output/ui/history. Native Fusion
loading and geometry validation remain pending.

The complete project was transferred to its Partelier root with identical
SHA-256 hashes for all 232 files, including hidden Git data and outputs.
Windows refused renaming/removing the previous root because an active
process holds it open. That old directory is empty; its final removal
requires closing the old workspace and releasing the lock. Continue work
from the new project root and relink the new inner bundle in Fusion.

## Split-seam correction evidence (0.1.1)

The user reached the native hinge command and reported the A-edge ownership
refusal on a split block/lid. The screenshot shows co-oriented exterior front
faces across a touching seam. This is user-reported native selection evidence,
not a successful generated hinge or a recorded Fusion build/runtime baseline.

The correction canonicalizes complete coincident A/B edges, adds explicit
Split seam controls and full rectangular-interface clearance on temporary copies,
and writes recipe version 2 with strict in-memory reading of version 1 settings.
The new HingeSplitFixture script reproduces the front-face case in a fresh document.

All 117 local tests passed. They include pure clearance bounds, rotated/reversed
placement, copy-only subtraction, mode validation, command invalidation and old
recipe reading. Python compilation including both fixtures, all three UI JS
syntax checks, manifests and direct documentation/HTML checks passed. Browser
checks passed mode switching, disabled offset/clearance fields, zero-clearance
validation and restoration, with no script warnings/errors. Current UI evidence
is output/ui/partelier-split-seam.jpg. Geometry, cancellation, ownership, legacy
Edit and source preservation still need native acceptance with both fixtures.

## Part Design and distributed-hinge correction (0.1.2)

The user supplied the native Create traceback: `Occurrences.addNewComponent`
failed because the active document is a Part Design, which permits only the
existing component. The add-in now persists an owned root BaseFeature for Part
intent and retains the generated-component path for Hybrid intent. It does not
change document intent. This follows Autodesk's
[design-intent guide](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/DesignIntent_UM.htm).
The touching fixture now explicitly creates Part intent to exercise this path.

The supplied log also confirms three one-hinge temporary previews completed
(approximately 74.8, 49.9 and 44.6 ms total), followed by failed persistence.
Those unstandardized observations do not establish geometry acceptance or a
performance baseline. No native successful Create/Edit is claimed.

New code also detects complete supported touching seams automatically, synchronizes
the native mode, and distributes 1–20 whole hinges using per-hinge length and
nonnegative end margins. Multiple units use exact barrel-end margins and equal
gaps; one unit is centered in the remaining interval. Both source copies and
the seam cut are shared; optional pins remain separate bodies. Saved recipe
version 3 strictly reads versions 1/2 as one hinge with zero margins. Source
collection indexes are recorded during BaseFeature edit and used to map the
result bodies after finishEdit; role assignment does not assume add-call order.

All 164 standard-library tests passed with Python 3.12.14. Compilation of the
bundle, tests and fixtures passed; all three UI scripts passed syntax checks.
The repository whitespace check passed with host access (the sandboxed Git
check could not recognize the renamed worktree); there is still no tracked
baseline. Direct checks passed 37 local documentation links, 36 unique static
HTML IDs, four local UI assets and three uniquely identified paired manifests.
Browser checks passed count 3, length 10 and margins 5, rejected zero count and
negative margins, and showed the new arrangement sketch without warnings/errors.
The narrow interface evidence is `output/ui/partelier-distributed-hinges.png`.

Native acceptance remains pending for Part and Hybrid Create, distributed
geometry, source preservation, Cancel, cleanup, Undo/Redo, save/reopen and
Edit/Rebuild. Restart the add-in, or Fusion if old Python modules remain loaded,
before testing. On the Part touching fixture, count 3, length 10 and margins 5
should create exactly two copied halves and three pins, with centers at
-15/0/+15 mm along the edge and 5 mm barrel gaps. Historical 0.4.3 full-result
preview and automatic source-backup hiding replace the old manual-hide step.
Error dialogs include the original exception and
show Text Commands with the full traceback.

## HTML workflow and separate leaves (0.2.0)

The user confirmed the previous attached Create succeeded. The supplied native
log records six previews between 46.907 and 97.060 ms and one Create at
206.422 ms total (127.068 ms persistence). Inputs, build and environment were
not fully recorded, so this is user-reported success and timing evidence,
not a benchmark or complete native acceptance of Edit/Undo/printing.

The new increment moves all dimensions and Preview/Create/Rebuild/Cancel to the
HTML palette. Its native command now has only geometry selections, with OK
hidden. Session UUIDs, complete setting snapshots and revisions guard updates.
Tests cover stale actions, active-document changes, explicit native execution,
invalidated inputs after Destroy, failed Cancel/opening, cleanup and failed
state/log delivery. Only native execute persists geometry. The Qt push
acknowledgement is kept out of the user action protocol.

Separate output adds rectangular or two-outer-corner rounded leaf pairs and
optional two through-holes per leaf. Temporary geometry does not copy, cut or
join sources in that mode. New plan constraints cover barrel/plate spacing,
short webs, hole containment and inactive settings. The adapter checks all
result pairs, maps BaseFeature source/result indexes and saves strict v4 recipes
with v1–v3 defaults. Preview now uses a neutral lit material instead of the
unlit blue solid-color effect; native source selection highlighting is separate.

All 215 standard-library tests passed with Python 3.12.14. Bundle/tests/fixture
compilation passed, as did all three JavaScript syntax checks and
`node tests/test_palette_ui.cjs`. The latter exercises the actual palette code
against a small DOM/host fixture, including queued settings and stale preview
responses; it is not native Fusion evidence. Repository and direct whitespace
checks passed. Direct asset/document checks passed 40 local documentation links,
50 unique static HTML IDs, four local UI assets and three paired manifests.

Browser checks passed attached/separate switching, retained rounded style,
conditional holes and inactive attachment fields, zero-hole-diameter rejection
and recovery, matching concept art, and disabled CAD actions outside Fusion.
The 318 px workspace had no horizontal overflow; output/style controls stack
below 400 px. No script warnings/errors were reported. Evidence is saved at
`output/ui/partelier-html-hinge-workflow.png`.

Native checks still required after restarting the add-in: geometry picker to
HTML selection synchronization, explicit Preview/Create/Cancel/Rebuild,
notification ordering, Undo/Redo/save/reopen, neutral lighting, independent leaf
solid/hole dimensions, and source preservation. A separate-leaf fixture can use
the existing 50 mm reference edge, one 40 mm hinge, reach 12 mm, leaf thickness
2 mm, rectangular/rounded profile, holes diameter 3.2 mm at 6 mm end offsets.
Do not reuse the attached split fixture's narrow 5.5 mm reach for these holes.
For three 10 mm hinges with holes on that edge, use 5 mm barrel margins and
3 mm hole end offsets; native results remain unverified.

Barrel, concealed and print-in-place are requested future families in the hinge
specifications. The 45-degree underside-chamfer target depends on print
direction and is not implemented by relabeling the current separate pin.

## General edge finish (0.2.1)

The user requested chamfers as an overall aesthetic finish, rather than only
local underside relief. An optional Edge finish disclosure now controls one
45-degree equal-distance size, initially 0.3 mm and disabled by default.
Generated webs, separate rectangular/rounded leaves, barrel/pin ends and bore /
screw-hole entries are finished using temporary bounded wedges and frusta.
Source geometry is excluded. Existing nominal cylindrical middles, overall
lengths and placement are retained. Recipe version 5 strictly reads v1–v4 with
the finish disabled; saved attributes are not migrated on inspection.

All 231 standard-library tests passed. The new checks cover equal-distance cut
planes, rotated/transformed mm-to-cm placement, all box edges and curved corner
caps, retained cylinder middles, positive material removal, oversized requests,
web contact, hole-mouth material and source preservation. The actual UI script
contract passed finish toggling, invalid-size rejection and illustration updates.
Browser checks passed the disabled initial size, enabling, zero rejection and
restoration to 0.3 mm with no script warnings/errors. Evidence is saved in
`output/ui/partelier-edge-finish.png`.

Python/JavaScript compilation, direct links/assets/manifests and whitespace checks
are part of the final local check. Native Fusion acceptance of the new cuts is
still pending: inspect both attached and separate outputs, rounded corners and
hole entries, measure the specified size and nominal middle diameters, then
exercise Preview/Cancel/Create/Edit and Undo/Redo. In particular, conical end
unions, rotated wedge differences and quarter-ring cuts are kernel-dependent.
Do not infer their success from fake-host tests. The earlier 206.422 ms Create
predates this finish; no finish performance comparison or printability claim is
made.

## Panel-free geometry picking (0.2.2)

The user confirmed model selections update the HTML fields, but reported that
the remaining native selector panel still opens. This increment replaces that
panel with direct UserInterface.selectEntity calls from the HTML message
callback. Begin picks A/B/edge sequentially, or one generated result for Edit;
Esc stops the sequence and retains earlier captures. Individual geometry buttons
start a repick; changing a face clears the axis reference. Interactive actions
wait for the user without the former 30-second bridge timeout.

Preview builds temporary geometry/custom graphics on the main thread without
opening a native command. Only Create/Rebuild launches a zero-input native
command with isAutoExecute true; native execute owns persistent operations and
the Undo transaction. The pending commit locks HTML settings/actions, and launch
acknowledgement never claims successful creation. Retained commandStarting and
documentDeactivating handlers clear previews or close document-bound sessions;
Stop removes those handlers and native references. Legacy native dialogs remain
available only through the compatibility bridge.

All 238 standard-library tests pass with Python 3.12.14. The 26 direct-session
checks cover abort/retry, preserved picks, stale snapshots and document changes,
zero command inputs, explicit execute success/failure, fresh settings on commit,
Edit loading, delayed acknowledgements, callback/log failures and cleanup. The
actual JavaScript contract passes unlimited interactive picking, pending-commit
locking/unlocking, effective seam mode, stale responses and retry. These are fake
host checks, not native API execution. Browser evidence of the updated selection
instructions at 318 px is output/ui/partelier-direct-selection.png; CAD actions
remain disabled outside Fusion.

After Stop/Run (restart Fusion if modules are cached), verify in a disposable
Design:

| Check | Expected behavior |
| --- | --- |
| Select geometry | A/B/edge prompts occur in the model; no separate command panel appears; each completed pick updates HTML |
| Esc during any pick, then geometry button | Earlier picks remain; the button retries only its target; no 30-second timeout |
| Replace either face | Reference edge clears and must be picked again |
| Preview twice, adjust dimensions, Cancel | Temporary graphics reuse current geometry; changes invalidate it; Cancel removes graphics without model writes |
| Create / Rebuild | No command panel; one undoable transaction; actual completion/error shown in HTML |
| Undo/Redo, Edit, save/reopen | Native ownership, geometry and source-preservation checks still pass |
| Other Fusion command, switch document, Stop/Run | Preview clears at context changes; document-bound sessions/handlers release; unrelated commands are not terminated by Cancel |

Native acceptance of this new no-panel flow, undo grouping and direct-pick
cancellation remains pending. User confirmation of the prior picker-to-HTML sync
does not validate these new paths. General chamfer and separate-leaf native
geometry checks above also remain pending.

## Blue light theme and pin-hinge variants (0.3.0)

The user requested greater contrast and a blue light theme, plus several pin
hinge designs with fillets or straight housings. White cards, navy text, darker
field borders, blue selection/focus and 12–14 px labels/helper copy replace the
sage theme. Five presets configure real geometry: Classic (round/5/sharp), Soft
(round/5/0.6 mm fillets), Linear (inscribed square/5/0.3 mm chamfers), Compact
(round/3/fillets), Piano (round/11/chamfers). Dimensions, placement/output and
mounting choices remain editable. Changes beyond a preset show Custom.

Recipe 6 stores knuckle_profile, fillet_edges and fillet_radius_mm, retaining
strict non-mutating reads of versions 1–5. Analytical temporary primitives round
webs/leaves, housing/pin ends and bore/hole entries. Concave intersections of
joined parts are not blended, and source geometry is excluded. Fillet separate
leaves use the flat outline with all corners rounded; the legacy two-free-corner
profile remains a sharp/chamfer option. Linear's square lies inside the original
radial envelope; wall/contact checks use its actual section. Failed requested
finishes fail explicitly. No native modeling or interactive pick request is
misreported as failed after a fixed 30-second bridge timeout. Local UI assets
have a release query tag to avoid mixed cached versions.

All 266 Python tests pass, including 18 analytic rounding checks and 10 style /
recipe / adapter checks. They test spherical/torus profiles, tangency, envelope,
mm/cm placement in rotated frames, explicit material removal, failed/split solids,
non-temporary rejection, overflow, source preservation and legacy recipes. The
actual JavaScript session fixture passes presets, conditional treatment fields,
strict snapshots, long native operations and prior selection/commit behavior.
Python compilation, all three JS syntax checks and direct formatting/link/asset/
manifest checks are required alongside them. These tests do not execute Autodesk's
kernel or establish fit, movement, durability or printability.

Browser checks passed the five preset states, matching concept forms, custom
finish, invalid zero radius/recovery, and disabled CAD actions outside Fusion.
The real 319 px and 1280 px views had no page-level horizontal overflow; the
540 px responsive view was inspected in a temporary same-origin iframe fixture.
Wide panes use two columns and narrow panes stack. The fixture was removed.
Proof is saved in output/ui/partelier-blue-soft-wide.png,
output/ui/partelier-blue-linear-wide.png and
output/ui/partelier-blue-designs-dock.png. These are UI/concept images, not
native solid evidence.

Required next native check: restart the add-in, select Soft then Preview/Create
in the disposable fixture, including separate leaves with holes. Inspect actual
curved ends/corners and nominal middle dimensions; exercise Cancel, Edit,
Undo/Redo and source preservation. Then compare Linear's square housings and
Piano/Compact knuckle counts. Record source_read_ms, temporary_geometry_ms and
total_ms for both sharp and filleted variants; the extra primitive booleans have
not been benchmarked in Fusion. Motion sweeps and the requested barrel,
concealed and print-in-place families remain future work, visibly marked
planned in the palette.

## Always-on live preview (0.3.1)

The user reported a hinge visible after picking geometry disappearing when the
preset/type changed. The HTML change path sent hinge_update, which cleared the
graphics without requesting a new model preview. Live preview is now permanent
for the active hinge session: begin/focus completion requests hinge_preview;
valid type/size edits refresh after a 160 ms trailing debounce. Requests remain
serialized and carry the latest complete snapshot/revision. Incomplete selection
updates remain cheap. Create/Cancel cancel pending timers; Create requires a
successful preview for the current revision. Refresh preview remains a retry.

Python prepares and draws the candidate while the previous graphics stay
visible, then retires the previous group. Errors retain the previous valid view
and explain that it is stale. previewCurrent records actual generation validity.
An aborted repick keeps its current graphics and reuses the cache. Preview-error
retry resets the failure latch. Failed deletion retains owned graphics and does
not falsely complete Cancel; a retry can clean them. Invalid input/bridge errors
show needs attention, with Create disabled; choosing a preset cannot clear the
validation error on an unfinished number field. Original solids and recipes are
unchanged until explicit Create/Rebuild.

All 273 Python tests passed. Seven new session checks cover atomic style changes,
last-valid preview/error recovery, aborted picking/cache, failed retirement,
retained candidate cleanup, failed Cancel/retry and default Fusion selection
without clearing graphics. The actual JS contract
passes automatic preview after selection and Edit, burst coalescing, newest
values after a slow prior preview, strict snapshots, invalid input/bridge error
recovery, pending Create and timer cancellation without resurrecting Cancelled
sessions. These are local/fake-host checks, not Autodesk API execution.

Browser verification passed on the unconnected 1280 px UI: the permanent Live
preview status, Refresh preview label, type/length edits and disabled CAD actions
remain correct, with no horizontal overflow. Evidence is saved as
output/ui/partelier-live-preview-ui.png; it does not claim model generation.
Changed implementation files: command.py, ui/palette.js, palette.html,
palette.css, catalog.js and the add-in manifest. Regression fixtures are
test_hinge_palette_command.py and test_palette_ui.cjs; affected README,
architecture, hinge-design and repository guidance were updated. The existing
native context cleanup remains in force when another Fusion command starts or
a document deactivates. No background model work or new native event is added.

Next native check after Stop/Run: pick A/B/edge and observe preview without
pressing Refresh; switch Classic/Soft/Linear and edit dimensions repeatedly;
verify no blank interval and only the newest geometry remains. Try an invalid
fillet, repair it and confirm Create re-enables only after a successful refresh.
Cancel during a pending edit must not redraw later. Check Edit/Rebuild and
Undo/Redo, and record preview timings for repeated fillet changes. These new
native behaviors remain pending user verification.

## Planned geometry acceptance and performance baseline

These checks belong to the future delivery gates in [mvp-plan.md](mvp-plan.md).
They have not been run. Keep exact fixture dimensions and expected relationships
with each tool's specification; do not use generated concept images as fixtures.

For the hinge, record the source bodies/visibility/timeline before work and
verify alternating attached knuckles, coaxial bores, pin diameter, axial gaps and
expected result solid count. Exercise invalid selection, changed/deleted source,
repeated preview, Cancel, interrupted command, Stop/Run, failed Create and
Undo/Redo. At the editing gate, add save/reopen, unsupported recipe versions,
failed rebuild preserving old results and replacement limited to owned objects.
Body count and volume alone are insufficient: also check the expected placements,
joins and gaps and that no unrelated object changed.

For performance work, record:

| Item | Required record |
| --- | --- |
| Environment | Fusion build, embedded Python, Windows and hardware; preview settings |
| Fixture | Exact geometry/parameters, supported boundary, source/result counts and document state |
| Workload | Fresh command, unchanged preview, changed dimension/selection, Create and later Rebuild; pattern size when applicable |
| Stages | Input/source reading, pure planning, temporary geometry, display, persistent creation and rebuild durations |
| Repetition | One separately recorded cold run, then at least five warm runs per measured case with all timings and median; expand sampling if a tail-latency claim is needed |
| Correctness | Same expected dimensions, topology and ownership checks for both baseline and candidate |
| Cleanup | No growth in retained sessions or owned temporary graphics across repeated runs; no orphaned persistent objects |

Compare approaches on the same fixture/environment and label cold/warm results.
Do not compare a wireframe-only preview with a full-solid preview as if their
work were equivalent. Use the first baseline to set a response budget for the
supported workload; record the budget before accepting an optimization. Keep
measurements local to development and add no telemetry. Native timings do not
replace geometric correctness or physical fit checks.

## Git and distribution

Local Git is initialized on `main`; no remote, initial commit, push or GitHub
repository has been created. Review the new files before committing. Connect the
intended GitHub repository when its destination is known. Do not publish local
reference projects, private Fusion designs, generated exports or logs.

The installable unit is the `Partelier/` folder. Tests, docs and task templates
are development files outside that bundle. An installer and release procedure
should be added only when there is a validated distributable version.

## User-referenced tapered supports (0.3.2)

On 2026-10-21 the reference was read from the user's local version-02 STEP/F3D
export and inspected in Fusion without changing its geometry. `support.py`
computes an exact upper tangent through the old web outer corner and extends it
into the source. All alternating attached round knuckles use this helper; flat,
square and separate behavior remains explicit. The advanced selector, illustration,
complete HTML settings snapshots and legacy native settings retention were updated.
Recipe 7 preserves versions 1-6 as flat webs until a deliberate shape change.

Local verification: 298 Python tests passed; the real JavaScript DOM/host fixture
passed; all three JavaScript syntax checks and Python compilation passed. Direct
AST/format checks covered 39 Python sources, four manifests and 56 text sources.
Compilation redirected caches to the writable development output location; this
adds no runtime dependency or product setting.

Native verification used `tools/fusion/TangentSupportProbe` through the Fusion
Scripts dialog. Fusion 2705.1.30 / embedded Python 3.14.0 passed six cases with
five alternating knuckles each: sharp/chamfer/fillet, in identity and a translated,
rotated frame. Positive source joins and separation between the halves, pin and
adjacent knuckles passed. Timings for each five-knuckle temporary test were about
44-49 ms sharp, 143-145 ms chamfered and 429-431 ms filleted; these include probe
checks and are not palette preview timings. The report is the ignored local
`output/native/tangent-support-probe.json`. The active document before/after
matched: four root bodies, seven timeline features, identical body volumes,
face/edge counts and timeline marker. No result was persisted in the user's model.

The new-profile HTML Create/Rebuild/save/reopen path still needs acceptance after
reloading the add-in. Temporary kernel success is not physical print, fit,
retention, motion sweep or strength validation. Separate-leaf and square-housing
support designs remain outside this change. See hinge-design.md for dimensions
and the larger taper footprint, which is not clipped to a source face boundary.

## Orbit-safe live preview (0.4.1)

The user reported that the first orbit gesture removed the preview and changing
style restored it. The commandStarting cleanup deleted graphics for navigation.
The palette now validates a source-only snapshot at commandTerminated. Unchanged
source geometry keeps the same graphics/revision, without preparing BRep again.
Changed or unreadable sources clear the stale preview and disable Create until
refresh/reselection succeeds. Own Create/Edit/picking callbacks avoid reentrant
checks. Cancel, document deactivation and Stop keep their cleanup behavior.
The snapshot retains no generated temporary output bodies.

The basic field now says Barrel diameter; barrel_diameter_mm remains the stored
parameter (default8 mm), so radius is half the value (default4 mm). No redundant
radius field or recipe change was added. Local regression checks cover camera
commands including unknown IDs, cancelled/nonmutating commands, source changes,
read failures, refresh recovery, cleanup and no geometry rebuild during navigation.
Native orbit/pan/zoom in the reloaded palette remains pending. Historical 0.4.3
scripted geometry/session evidence does not validate manual navigation or the
0.5.0 persistence change.
