# Selection and operation history — 0.19.0

Goal: make every geometry-selection step visible; advance reference picking automatically; Esc resets captured references; distinguish saved operations and their native timeline features; keep wheel scrolling usable.

Implementation:
- Share selection progress/reset presentation across hinge, snap, patterns and Small details. Publish the active native reference before each prompt; never compute preview while reference picking is active. A/B/edge flows continue automatically after a repick. Esc clears only temporary selections/preview, retaining dimensions.
- Add a local operation browser that lists saved recipes already present in the active design, chooses the correct tool, and opens its exact anchor for Edit without ambiguous body picking.
- Name and group new operations using stable Fusion timeline groups, preserving native child features (including distinct Lip and Groove names). Existing geometry is not migrated merely by listing it. Expand owned groups before history-sensitive reads. Respect existing ownership/dependency guards; do not pretend arbitrary earlier-feature rebuild is supported.
- Add deletion of complete, explicitly chosen owned operations via a native transaction, guarded to the timeline end. Native group context menus remain available. Never delete selected source bodies.
- Route wheel input over palette chrome/number fields to the scroll area, preserve standard wheel behaviour in dialogs, and avoid rebuilding the operation list on unchanged live state.

Checks: Python ownership/protocol/selection tests, Node session suites, headless Edge selection/progress/scroll/operation browsing at narrow widths, a small disposable Fusion fixture through the existing MCP add-in. No desktop input control. Native work starts only if Fusion is idle and will restore the caller document.
