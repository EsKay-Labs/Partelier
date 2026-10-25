# Compact workflow — 0.20.0

**0.20.1 contrast correction:** the off-white workspace and white cards were too
close in tone. The header is now graphite, the workspace slate gray, the cards
pale blue-gray and the inputs nearly white. Size and workflow are unchanged.
The new HTML was refreshed in Fusion at 380 px with the model unchanged. Evidence:
[contrast-ui-0.20.1.json](validation/contrast-ui-0.20.1.json).

The palette opens at **380 × 760** instead of 540 × 840. Fusion docking can
override the height; the native check measured a 380 px width and 691 px docked
height. White/graphite surfaces replace the broad blue theme. A small selection
highlight remains for the current native pick. Error styling stays distinct.

The default screen follows **Geometry → Configure → Create**:

- The dropdown contains the ten implemented tool entries. Planned tools,
  favorite controls, repeated tool headings and stage badges leave the main UI.
- Geometry begins with one clear selection button. Its numbered references
  appear during picking, and the card folds when the references are complete.
  Change reopens it, and stays open across ordinary parameter edits. Reset
  reopens selection without changing dimensions. Multi-face patterns remain open
  until Done; picking individual faces never triggers early completion.
- Basic style, size and count remain visible. Hinge pin fit and end margins move
  to Advanced; pattern density and size locking do too. Optional grille mounting
  is inside Advanced. All existing controls and their values remain available.
- Each tool has one basic configuration card. Long explanatory paragraphs move
  out of the default screen; illustrated field help and detailed Examples stay
  accessible. The action dock keeps the existing Create/Rebuild and Cancel flow.
- Saved opens the existing operation browser on demand. Its Edit still loads an
  exact saved anchor. The alternate model picker is available from that panel.
  Esc closes Saved or a help dialog before resetting geometry selections.

Opening an operation also fixes a session-adoption issue: revision numbers are
compared within their session. A newly loaded operation at revision zero must
replace dimensions left by a prior higher-revision session. Same-session stale
responses and retired-session guards remain in place. The three Node suites
cover this for hinge, snap-fit and pattern; the browser workflow covers details.

No geometry algorithms, geometry defaults, ownership records, CAD operation
types, native selection protocol or model data are changed.

## Checks

- 29 palette lifecycle tests, including the requested initial dimensions.
- Three Node session suites, including exact settings adoption on operation Edit.
- Headless Edge at 320/380/440 px: all ten tools, no horizontal overflow, compact
  initial view, automatic folding, persistent Change, reset, Done gating, Saved
  Edit/tool switching and Esc priority. Screenshots were inspected locally.
- Native palette reload verifies width and preserves the active design's body
  identities, names, visibility, volumes and timeline. This does not constitute
  manual CEF pointer/wheel acceptance or a new native geometry validation run.

Evidence: [compact-ui-0.20.0.json](validation/compact-ui-0.20.0.json).
