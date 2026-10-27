# Selection and saved features — 0.24.1

0.24.1 labels the per-tool card **Saved features**. Edit and Delete use matching
full-width buttons in a two-column grid. Delete replaces that toolbar with an
inset confirmation and a spaced **Keep feature / Delete feature** pair; it does
not append a second toolbar. Opening confirmation reveals it in the workspace
and focuses Keep feature; keeping it returns focus to Delete. The existing
exact-ID routes, native deletion and dependency guards are unchanged.

Headless Edge verifies button containment, spacing, equal heights and no
overlaps at 280/300/380/520 px, including confirmation in both lists and
125%/150% zoom. Evidence:
[feature-actions-0.24.1.json](validation/feature-actions-0.24.1.json).

Each tool shows **Saved features** above its geometry controls.
Planar trusses and grilles have their own lists; Surface patterns, Perforations
and Surface texture share the ordinary surface-pattern list so a saved feature
remains discoverable after changing shape or relief mode. Hinges, snap-fits and
each small-detail tool also show their own features. **Saved** in the header
remains the optional list of all operations in the active design.

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

Choose the tool and find its saved feature directly under the dropdown. Each
entry has its saved name and explicit **Edit / Delete…** actions. **Edit** opens
that exact saved anchor, loads its dimensions and highlights the row in blue;
change the settings and use **Rebuild** in the bottom action bar. **Cancel** ends
the edit without changing the saved result. Other saved-feature actions stay
disabled while a selection, preview or native deletion is active.

The lists read small recipe records only: no face walks, solid hashes, geometry
generation or polling loop. They refresh on connection, tool changes and
Create/Rebuild/Cancel; native deletion pushes its resulting list. An older
acknowledgement cannot restore rows removed by a newer push. Use **Refresh**
after external timeline changes, Undo/Redo or switching designs without changing
the selected tool. **Select an existing result from the model** remains available
inside the optional **Saved** browser.

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

**Delete… → Delete feature** confirms the chosen name and removes the complete operation in a native
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

0.24.0 adds a focused Node controller suite for section membership, exact IDs,
Edit/Cancel, explicit Delete/Keep, legacy rows, native pending deletion, failure
messages and push-versus-acknowledgement ordering. The four existing UI suites
and 1,082 Python tests still pass. Headless Edge checks the full palette at
300/380/520 px: scoped lists, correct saved style/dimensions, Rebuild without an
extra row, deletion confirmation, shared ordinary patterns, separate grilles and
no horizontal overflow. The previous compact-workflow browser suite also passes.

The existing native history probe was rerun against the 0.24.0 sources in Fusion
2705.1.30 for pattern and Planar truss: grouped Edit/Rebuild/Delete preserves the
original bodies and restores the unchanged caller after disposable documents
close. These are native geometry/history checks, separate from browser UI
checks; manual Fusion CEF pointer acceptance is not claimed. See
[section-features-0.24.0.json](validation/section-features-0.24.0.json).

Historical 0.19.0 evidence:

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
