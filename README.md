# Partelier

An Autodesk Fusion add-in foundation for automating small, repetitive CAD tasks
on existing 3D-print designs: hinges, snap-fits, sliding guides, connections and
surface patterns and later reinforcement tools. **Partelier is the approved product name**,
combining part and atelier: a workshop for the details that complete a design.

**New in 0.24.0:** every tool shows **Features in this section** with direct
**Edit / Delete…** actions for each saved operation. Trusses and grilles have
separate lists; ordinary surface patterns stay together. Edit highlights the
chosen feature and loads its dimensions for Rebuild. Source-body ownership and
existing timeline dependency guards remain. See [saved features](docs/selection-history.md).

**Current code:** experimental 0.13.0 provides surface patterns, an editable separate-pin hinge
and four snap-fit families: Hook latch, Ball detent, Torsion latch and Annular
ring. Hook latch also offers straight, tapered or twin arms. Snap-fits include
optional 45-degree root/receiver roofs and complete eligible outer-edge chamfers;
receiver pockets and mating/contact edges are protected. Both tools use
direct model selection, full-result live preview and manual Edit/Rebuild. Hinges
include five presets.
Attached output integrates the hinge into the two selected root bodies, retaining
their identities, names and visibility. Only optional pins add separate bodies.
Separate-leaf output creates independent hinge parts.
Preview uses the existing Fusion body appearances at full opacity and crisp
black outlines; plain Shaded display omits those outlines. It adds no document
appearances or permanent display overrides.
Edit accepts a hinge body, face, edge, or a Part containing exactly one owned
hinge. One existing selection is reused when Edit opens. If a Part contains
several hinges, choose a specific hinge body or pin. Failed selection loads
retain their actual error through automatic previews and parameter changes.

Version 9 recipes support this attached persistence model. A safe deliberate
Rebuild migrates earlier attached copy-based results; it never deletes unrelated
bodies. Upstream geometry changes require explicit Rebuild to recalculate the
stored tool shapes. Preview and Cancel leave no persisted changes.

The final 0.5.0 native report passes 53 stated expectations: 40 generated
geometry cases, six explicit larger-fillet refusals, six in-place/migration
cases and one production-session workflow. Four attached fixture treatments each
pass four Rebuilds without replacing the selected bodies or accumulating history.
Local checks pass 914 Python tests, all three Node DOM suites and syntax/compilation
checks. The current hinge workflow has been user-confirmed
in Fusion. Broader interaction coverage, save/reopen, Undo/Redo, motion and
physical printing remain acceptance items. See
[native evidence and limits](docs/fusion-validation.md). The snap-fit passes
56 native geometry/persistence/refusal/session cases, including source rollback
and stable body identities. Patterns pass 61 native geometry and workflow checks,
including full cylinder wraps, regular cone/sphere regions and cached preview
creation after rollback. The original model, document and camera are restored.
Other tools remain planned. The older honeycomb input checker remains a separate
diagnostic and creates no geometry.

**New in 0.13.0:** **Flat colour** adds flush, separately colourable material
regions and a two-part 3MF export. **Patterns > Grilles** adds parallel bars,
crossed ribs and inclined channels on supported planar plates, with in-place
Create/Edit/Rebuild. See [surface patterns](docs/surface-patterns.md) for scope.

**New in 0.12.1:** new patterns start in **Auto fit**, with **7 mm Minimum gap** and **7 mm Border**. Existing saved patterns keep their settings.

**New in 0.12.0:** the Pattern dropdown has **15 real choices**, adding alternating
and rounded triangles, pentagons, Cairo pentagons, octagons, hexagon/triangle and
octagon/square mosaics, a rhombille cube grid, rounded hexagons and elongated
hexagons. They share Auto fit, size locks and Through/Engrave/Emboss. Local samples
come from the actual polygon planner. See the [variety and dimension contract](docs/surface-patterns.md#polygon-varieties).

Version 0.11.0 added **Layout > Auto fit** to propose opening size and count
from the selected surface, with **Sparse / Balanced / Dense** density. Editing
Cell size locks it; choose **Size > Automatic** to resume suggestions. The search
compares at most 16 numeric grids and only two reach surface acceptance before
the selected layout creates exact geometry. Gap/border and existing source,
curvature and solid guards remain. Saved v1/v2/v3 recipes retain their original
layout; new recipes use v4. See the [Auto fit contract](docs/surface-patterns.md#auto-fit).

Version 0.10.8 made **Balanced** preserve the requested **Cell size** and
uses wider gaps to keep its sparse layout within 48 cells per face. Changing
Cell size updates the actual openings even on large faces.

Version 0.10.7 introduced **5 mm Minimum gap** by default, stable **Cell size / Minimum
gap / Border** labels in every layout mode, and **Clip at border** for partial
hexagons, circles and other shapes at face edges, notches and holes. The **?**
dialogs explain each setting with an image. See the
[layout and help contract](docs/surface-patterns.md).

**Surface patterns:** choose **Honeycomb**, **Perforations** or **Texture** in the
tool dropdown. Each opens the same workflow with a different preset. Choose
hexagons, circles, diamonds, squares or slots and **Through holes**, **Engrave** or
**Emboss**. Pick a face to start preview; **Add face** adds another face on the
same solid. **Balanced** preserves Cell size and uses wider gaps for fewer cells.
**Fill face** preserves Cell size, keeps at least Minimum gap and Border,
and includes partial edge cells by default. A **?** beside each setting explains its behavior
with an image. Review the live preview before Create.
Edit/Rebuild updates that same body. Plane and cylinder charts, multiple faceted
sides and bounded regular regions of smooth surfaces are implemented. Distorted
or singular regions can be refused or omitted conservatively. Dense curved
patterns can take noticeably longer to preview. See the
[surface contract, examples and limits](docs/surface-patterns.md).
The hard limits remain 200 cells per face / 400 total. Balanced adjusts spacing;
Fill face asks for larger cells when too dense. Automatic size and Exact pitch
retain the previous behaviors for existing recipes. Saved settings are restored
unchanged by Edit; new defaults apply only to new patterns. Short trim edges near
hinges no longer exclude distant columns beneath them: real borders remain protected.

Version 0.10.1 also recovers the pattern palette when a preview acknowledgment
or completion notification is lost. It reads the existing native session status
without recomputing geometry. A completed preview can release a waiting UI
request; late acknowledgments cannot restore an obsolete loading state.

Version 0.10.2 accelerates pattern preparation: exact temporary prisms are
constructed directly, planar faces avoid redundant ring evaluations, and
disjoint Through cutters can be applied together. The original first-wall,
border, web and final-solid checks remain. Refused batches use the exact
sequential fallback. Edit/Rebuild retains its three owned history features;
Through preview preparation creates no timeline features.

Version 0.10.3 records local diagnostics for actual pattern interactions,
including disabled-button clicks, native picking, bridge request IDs, preview
driver delivery, geometry stages and errors. Logs are written automatically to
`%LOCALAPPDATA%/Partelier/logs/partelier.jsonl`, with three rotating backups.
Reload Partelier once to activate the instrumentation, then reproduce the issue;
copying the Fusion console is unnecessary. See [diagnostic details](docs/fusion-validation.md#local-interaction-diagnostics-0103).

Version 0.10.4 fixes the selection wait confirmed by the new native logs: a
face click now ends picking and starts preview immediately. **Add face** selects
one additional face on the same body; the existing **Faces** button replaces the
selection. Preselected multiple faces and whole-body selection remain available.
The UI distinguishes surface picking from preview computation.

Version 0.10.5 caches pattern preview triangles using Fusion's standard binary
STL exporter. A single opaque mesh retains the source appearance and bounded
edge outlines, so camera movement does not redraw a custom BRep body. Exact CAD
geometry remains separate for Create/Rebuild. Display scratch geometry is
removed inside the rollback computation; temporary files are deleted. The
unstable direct mesh-calculator experiment remains removed.

**Try the updated tools:** Stop then Run Partelier to load 0.13.0. The tool library opens
automatically; choose **Snap-fit**, then **Snap type**. For Hook latch, Ball detent
or Torsion latch, pick the base exterior wall A, the coplanar lid wall B,
then either facing straight rim. Matching rims may have a gap between them;
internal lid lips may cross the exterior seam. The selected wall regions need
enough material for the root and blind recess. Size and fit stay
visible; count, margins and root dimensions are under Advanced. The source seam
is preserved and the two parts are printed separately.
For Annular ring, pick A's outer cylinder, B's coaxial inner cylinder, and the
complete circular rim on A. It creates one continuous bead and a matching
groove. Only the dimensions relevant to the selected family are shown.
Hook latch offers **Hook style** for straight, tapered or twin arms. **45° print ramps** changes
the root/receiver shape; **Advanced > Edge finish** controls exposed-edge
chamfers on the joined detail, including free edges inside a fork. Tip corners
meet the sloping nose without triangular caps; fork-foot bevels meet without
flat shelves. Mating faces, the retaining shoulder and the entire receiver remain
unchanged by that finish. Printing ramps assume build-up
from A toward B; inspect your actual slicer orientation.

Existing snap-fits load their saved dimensions and finishing choices. Version 1
loads sharp, without print ramps; version 2 preserves its saved choices. Neither
format is rewritten on selection. A successful deliberate Rebuild saves version
3 with the full family settings. Compatible planar mechanisms can change family
during Edit; changing between planar and annular references requires a new snap-fit.

For a new unsaved reference model, run **tools/fusion/SnapFitFixture** as a Fusion
script. See the [snap-fit specification](docs/snap-fit-design.md).

## Direction

Select relevant geometry on an existing design, enter a few dimensions, preview
the detail, and create it. The proposed first release contains a pin hinge,
snap-fit pair and sliding guide. Hardware pockets, clips, pivots, bayonet closures,
ribs, trusses and honeycomb follow in scoped stages. Read the
[MVP plan](docs/mvp-plan.md) for the consolidated feature set and priorities.
Its ordered delivery gates start with one editable hinge, then verify that the
same architecture accommodates snap-fit and sliding-guide tools. The
[architecture](docs/architecture.md) records module boundaries, the performance
approach and the selected StructForge reference techniques.

The user subsequently prioritized surface patterns after confirming hinges and
snap-fits; these precede sliding guides. The existing honeycomb input check
remains a diagnostic; the pattern generator is an independent tool. The hinge is an independent
tool module. Its supported scenario and exact fixture are in the
[hinge specification](docs/hinge-design.md).

The user selected an HTML palette inspired by StructForge instead of the earlier
native-only UI proposal. Its event bridge and palette lifetime informed this
implementation; its HTML/styles were not copied. StructForge is not a runtime
dependency. All artwork, styles and scripts are local; no account or remote asset
is required.

## Explore the UI prototype

Open `Partelier/partelier/ui/palette.html` in a desktop browser. The grouped
tool dropdown, favorites, guides and illustration controls work without Fusion.
The selected tool opens immediately. Up to 720 px the image and inputs stack;
wider views place them alongside one another. Workflow and design notes are
collapsed until requested. Ctrl/Cmd+K focuses the tool menu. Favorites move to a
menu group without duplicating entries and are session-only. Hinge and snap-fit
dimensions are editable here, but launching Create/Edit requires a live Fusion connection.
The drawing is a concept illustration, not the native geometry preview.

For local browser development, an optional loopback-only preview server can be
run from the repository root:

```powershell
py -m http.server 8766 --bind 127.0.0.1 --directory Partelier/partelier/ui
```

Visit `http://127.0.0.1:8766/palette.html`. This is a development convenience, not
an add-in backend or distribution requirement. Stop it after development.

## Run inside Fusion on Windows

Clone or download this repository:

```powershell
git clone https://github.com/EsKay-Labs/Partelier.git
```

The repository root contains the source, tests and development tools. The add-in
folder to link in Fusion is the **Partelier** subfolder inside that checkout:

```text
<checkout>/Partelier/
    Partelier.py
    Partelier.manifest
    partelier/
```

Renaming the project does not update Fusion's existing installation links.
If an earlier development bundle is already linked, Stop it and remove its old
link before adding this folder. Restart Fusion if the previous modules remain
loaded. Existing saved hinge recipes remain readable; a successful Edit/Rebuild
saves its replacement under Partelier. Native save/reopen validation is pending.

1. Start Fusion with a history-based Design. For the first test, add/run the
   standalone **tools/fusion/HingeFixture** folder under **Scripts**. It creates
   a new unsaved document with two exact reference boxes; it does not change
   the previously open model.
2. Open **Utilities > Scripts and Add-Ins** and use **Add / Link** (or **+** in
   the older dialog) to select this repository's **Partelier** subfolder. Select
   the folder containing `Partelier.py` and `Partelier.manifest`, not the repo
   root. Under **Add-Ins**, select **Partelier** and click **Run**.
3. In the Design workspace's **Add-Ins** panel, open
   **Partelier: Tool library** for the HTML palette. It opens on the right and
   can be resized or closed/reopened.
4. Select **Pin hinge**, choose a **Design preset**, then **Attached to parts**
   or **Separate hinge leaves**. Set dimensions in the HTML panel; fit, attachment
   and holes are in grouped sections. Separate leaves can have rectangular or rounded free corners
   and optional two through-holes per leaf.
5. Click **Select geometry**, then pick Face A, Face B and the reference edge
   directly in the model, following Fusion's prompts. No second parameter or
   selection panel is created. Esc stops the sequence and keeps earlier picks;
   use the Face A / Face B / Reference edge buttons to retry or replace a pick.
   Changing a face clears the reference edge. In the reference fixture, select
   the top faces and A's inner top edge at X=-4 mm. **Edit existing** prompts for
   one generated hinge body and loads its saved dimensions here.
6. **Live preview** starts after the geometry is selected and updates as you
   change designs or dimensions. **Refresh preview** is available for retry;
   **Create** / **Rebuild** confirms the current valid preview. **Cancel**
   clears the temporary preview and selections. Create/Rebuild runs a zero-input
   native command for a single undoable transaction; its panel is not opened.
   Attached creation uses owned tool geometry and native combines in the root;
   the selected A/B bodies become the final hinge-bearing bodies. Only optional
   pins increase the final body count. Full-result preview temporarily hides
   the current geometry; Cancel restores its prior visibility. Separate leaves
   retain their independent Part/Hybrid output path.
7. The original **Partelier: Check honeycomb inputs** remains available directly
   or through **? > Open input checker in Fusion**. Stop the add-in when finished.

Fusion supplies Python and `adsk` for the add-in. There is no package install,
web server, API key, database, or separate build step. Running `Partelier.py`
with an ordinary Python interpreter is not the application launch method.

## Pin-hinge designs and edge treatment

The blue light palette uses darker text, white cards, stronger field outlines
and distinct selection/focus states. The **Design preset** dropdown configures
actual geometry, not just the concept drawing:

| Preset | Housing / knuckles | Treatment |
| --- | --- | --- |
| Classic | Round / 5 | Sharp |
| Soft | Round / 5 | 0.6 mm fillets |
| Linear | Square within the circular envelope / 5 | 0.3 mm chamfers |
| Compact | Round / 3 | 0.6 mm fillets |
| Piano | Round / 11 | 0.3 mm chamfers |

Live preview is always enabled during the hinge session. Parameter edits are
grouped over 160 ms and render the newest complete values. The last valid
graphics stay visible until a replacement is ready; an invalid request is
marked clearly and cannot enable Create.

Presets keep your dimensions, placement, output and hole choices. **Housing &
edge treatment** lets you customize the profile, finish and size. The housing
envelope is the circular outside diameter; square housings fit inside that same
circle. Fillets round generated webs/leaves, housing/pin ends and hole mouths;
they do not blend concave intersections between joined solids or alter source
edges. In separate mode, fillet treatment rounds all corners of the flat leaf
outline. The older two-free-corner outline remains available with sharp/chamfer
finish. Invalid combinations explain what needs changing rather than skipping
a requested finish. Declared native fixtures pass; some 0.6 mm round fillets
remain explicit limits rather than being silently reduced. Exact sizes and
refusals are in [fusion-validation.md](docs/fusion-validation.md).

Barrel, concealed and print-in-place remain separate planned families under
**More hinge families**; they are not enabled Create options. See the
[family plan](docs/hinge-families.md).

## Hinge on two touching split parts

The reported first-use case selects the lower block's large front face and the
lid's narrow front strip above it. These exterior faces must be coplanar and
point outward together. Select their shared straight edge; a full shared seam
automatically activates **Split seam (touching parts)**. Either coincident A/B edge is accepted. The mode centers
the hinge and opens the adjustable **Seam clearance** in the selected bodies,
across the complete matching rectangular interface. Axis offset is disabled.
The first split mode requires planar polyhedral sources and rectangular mating
faces; other shapes are refused with an actionable message.

Full-result preview shows the cleared gap without persisting cuts. The selected
bodies are temporarily hidden; Cancel restores their captured visibility.
Successful attached Create applies the gap and hinge to those same bodies.
The standalone **tools/fusion/HingeSplitFixture** script provides exact touching
blocks for validation. Full dimensions and limits are in the
[hinge specification](docs/hinge-design.md). Restart the add-in to load this
increment; if the new checkbox is missing, restart Fusion after saving your work.
The historical 0.4.3 native matrix checks fixture seam separation; actual interactive
picking and the standalone split-fixture workflow still need acceptance.

For a general aesthetic finish, open **Edge finish**, enable **Chamfer exposed
edges** and set **Chamfer size** (0.3 mm is the initial value). It covers
generated leaves/webs, barrel/pin ends and hole entries; source-body edges stay
as designed. Overlarge values are refused rather than silently reduced.

The preview uses neutral lit gray shading. Fusion may still highlight selected
source faces separately. Additional barrel, concealed and print-in-place styles
are planned in [hinge families](docs/hinge-families.md), not implemented choices.

For multiple mechanisms, set **Number of hinges**, **Length per hinge**,
**Start margin** and **End margin**. Two or more hinges use exact barrel-end
margins and equal gaps; a single hinge is centered between the minimum margins.
Pins extend beyond the barrels. For example, a 50 mm edge fits three 10 mm
hinges with 5 mm margins and equal 5 mm gaps. Impossible layouts are refused
with a fit message. **Knuckles per hinge** controls fingers inside each hinge.

A Part Design supports results in its existing component. Partelier does not
convert it into a Hybrid/Assembly document. Error dialogs now show the native
reason and expose the full traceback in **View > Show Text Commands**.

Edit loads an owned hinge recipe. For attached version 9 results, Rebuild updates
the owned tool BaseFeature and recomputes the native combines on the same target
bodies. Earlier attached recipes migrate only after strict ownership, topology
and dependency checks. Independent earlier Part Design results may be handled
when those checks permit it; separate Hybrid results retain their last-feature
restriction. No automatic recalculation of generated tool shapes is promised.

During repicking, current geometry is temporarily revealed. Output-mode changes
transfer the preview visibility lease. Cancel, failed creation and Stop restore
captured preview flags. Successful attached commits preserve the selected
bodies' names and visibility; no hidden source backups are added.

## Check locally

A separate Python installation is only needed for development checks:

```powershell
py -m unittest discover -s tests -v
node tests/test_palette_ui.cjs
py -m compileall -q Partelier tests tools/fusion
git diff --check
```

On systems without the Windows Python launcher, use `python` instead of `py`.
There is no configured linter. Local tests check inputs, units, the bridge
allowlist and lifecycle behavior against a fake UI. They do not validate the
actual Fusion browser/events or generated geometry. See
[development and manual checks](docs/development.md).

For unattended native checks, run the opt-in development bridge once in Fusion,
then use `tools/run_fusion_validation.py status`, `submit --scenario joined_finish`
and `poll REQUEST_UUID`. This never controls mouse/keyboard or launches Fusion.
See [bridge setup and final native report](docs/fusion-validation.md).

The 0.5.0 architecture changes attached persistence and recipe versioning. The
[architecture](docs/architecture.md) describes the owned tool/native-combine
boundary and [hinge specification](docs/hinge-design.md) records the supported
selection, migration and acceptance contract.

## Repository map

```text
Partelier/                 Self-contained Fusion add-in bundle
  Partelier.py             Fusion run/stop entry points
  Partelier.manifest       Add-in metadata
  partelier/
    addin.py                Native dialog and Fusion event lifecycle
    settings.py             Pure, immutable honeycomb input contract
    palette.py              Tool-library launcher, palette and HTML bridge
    palette_protocol.py     Pure allowlist and message validation
    ui/                     Local HTML, CSS, catalogue, SVG rendering and UI logic
    tools/hinge/            Pure hinge plan, native commands and Fusion adapter
tests/                      Host-independent unit tests
tools/fusion/HingeFixture/  Standalone reference-document script
docs/                       Plan, architecture, development and AI workflow
.ai/templates/              Six reusable scoped task prompt templates
.ai/next-task.md             Ready-to-copy next implementation prompt
AGENTS.md                   Persistent repository instructions
```

Use the [AI workflow](docs/ai-workflow.md) for the ChatGPT/GitHub/Codex loop and
copy the [Custom GPT instructions](docs/chatgpt-bot-instructions.md) manually.
No GitHub remote or Custom GPT has been configured. The
[bootstrap report](docs/bootstrap-report.md) records what was delivered and what
remains unverified.
