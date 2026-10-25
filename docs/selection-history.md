# Selection and saved operations — 0.19.0

Reference buttons are numbered, full-width rows. The current native pick is solid
blue, captured references show their body names, and the next missing reference
has a strong outline. A/B/edge reference sequences continue automatically after
each pick, including when replacing a reference. Small details now asks for B
immediately after A. Preview waits until the complete sequence finishes.

**Esc resets references and temporary preview while keeping dimensions.** The
same action is available as Reset selection. Esc in a help dialog closes that
dialog first. In the additive pattern picker, Esc clears the selected faces and
keeps selection open; **Done** still confirms the complete set before preview.
Reset retires pending preview work and advances the session revision so old
callbacks cannot restore a discarded preview.

## Finding and editing one operation

Open **In this design** at the top of the palette. It lists small saved recipe
records from the active design; it does not scan faces, hash solids or rebuild
geometry. Each entry has a unique name. **Edit** selects its exact saved anchor,
opens the corresponding tool and loads the dimensions. **Pick from model**
remains an alternative to the list. Refresh the list after external timeline
changes, Undo/Redo or switching designs.

New operations have a native **Partelier** timeline group containing their real
Fusion features. A lid operation includes separately named **Lip · body name**
and **Groove · body name** features; pins have Pins/Pin holes, and ribs have Ribs.
Hinges, snap-fits, patterns, grilles and trusses use the same operation grouping.
Expand a group to inspect or select its individual native features. This uses
released TimelineGroups functionality, not Autodesk's preview Custom Features
API; it does not introduce a single custom feature with a double-click editor.

Saved operations from earlier releases appear without rewriting their geometry.
A successful explicit Rebuild can adopt exact consecutive recipe-owned history
into a group. Existing user groups are preserved. Collapsed Partelier groups are
expanded before history-sensitive reads because Fusion gives hidden children
timeline index -1. Pattern colour-mode and grille history conversions refresh
the recorded native children without grouping unrelated features.

## Deletion and dependency limits

**Delete… → Delete operation** removes the complete chosen operation in a native
command transaction. Each child must still have its saved ownership and token;
duplicates, missing/foreign children and inserted unrelated features are refused.
The operation must be a consecutive suffix at the end of the timeline. Source
bodies are preserved. One Undo restores the operation; Redo removes it again.

Earlier-feature Edit guards remain in the geometry stores: this release does not
enable arbitrary rebuilding through later dependent model edits. Use Fusion's
timeline to review those dependencies. Editing or deleting individual child
features manually can invalidate the paired operation recipe; Partelier then
refuses Rebuild rather than overwriting those external changes.

## Scrolling

The palette retains one scrollable workspace. Wheel gestures over number/select
fields scroll the workspace instead of changing dimensions. Gestures over the
header and action dock also reach the workspace. Dialogs retain their own wheel
and Esc handling. The workspace is keyboard-focusable. This addresses routing in
HTML; headless browser checks are distinct from manual Fusion CEF pointer and
wheel acceptance.

## Validation

- 1,033 Python tests pass, including protocol, ownership, automatic A/B picking,
  Esc/reset, late-preview cancellation and exact-anchor routing.
- Three existing Node session suites pass.
- Headless Edge at 300/380/520 px checks eight tool selectors, active pick styling,
  all four reset flows, dimension preservation, help-dialog Esc, wheel over
  numbers/header, exact operation Edit/tool switching and explicit deletion.
- Fusion 2705.1.30 passes twelve disposable history cases: lip/groove, pins, ribs,
  attached/separate hinges, snap-fit, pattern, colour conversion, grilles, truss, legacy lip
  adoption and flat-to-raised grille history promotion. They cover grouped Edit,
  source preservation and exact deletion; the lip case also refuses deletion
  across a later unrelated feature.
- The installed add-in's actual operation browser route and native deletion
  command pass in a separate disposable document, including one Undo and Redo.
  The transaction check is queued outside the Fusion MCP add-in's outer
  PTransaction, which otherwise interferes with Undo testing.

The caller document's body identities/names/visibility/volumes and timeline are
unchanged after each native case. Save/reopen, arbitrary downstream edits and
manual mouse selection/CEF wheel behaviour are not claimed by these scripts.
Evidence: [selection-history-0.19.0.json](validation/selection-history-0.19.0.json).
