# Compact UI — 0.20.0

Goal: reduce visual noise and improve the select → configure → create workflow.

- Neutral white/graphite surfaces; one restrained highlight for native picking.
- Initial Fusion palette 380 × 760, with narrow layouts checked at 320/380/440.
- Working tools only in the dropdown; hide redundant category/stage headings and favorites. Keep all implemented mechanisms, patterns and detail helpers.
- Saved operations opens from a compact header button. Exact Edit/Delete remain available; alternate model picking moves into this panel.
- Geometry is a disclosure that stays open while picking, folds once references are complete, and can be reopened to Change. Reset reopens it. Multi-face patterns still require Done.
- Keep basic size/style/count visible; put pin fit, end margins and secondary pattern layout controls in Advanced. Examples and per-field help stay available.
- Do not change geometry settings, defaults, ownership, preview, selection protocol or Create/Edit semantics.

Checks: existing Node session suites, palette lifecycle unit suite, headless real HTML workflow/scroll/screenshots; native palette reload/dimensions only, preserving any safe active preview and the caller document. No geometry probe needed for this presentation change.
