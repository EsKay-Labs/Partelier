# Cancel without reopening the palette

In 0.34.1, a modal pick could hold its Begin/Focus request open while the UI
disabled Cancel or queued it behind that same pick. Close used a separate native
cleanup route, explaining why reopening the palette appeared to fix the problem.

Version 0.34.2 gives Cancel a separate path in hinges, snap-fits, surface patterns
(including grilles/trusses), Small details, fans, mechanical pairs, face details,
threads and knob knurling. It remains available while selecting, preparing a
preview or awaiting creation. The backend validates the exact session, cancels
owned preview/selection work and restores visibility through the existing cleanup.
It does not close the palette or cancel an unrelated native command.

The shared UI queue invalidates old pending acknowledgments and drops queued
updates/commits. A matching native cancelled/created push can settle the operation
without waiting forever for a lost Cancel reply. Late messages cannot retire a
new session. Cleanup failures remain visible and permit a retry; a timeout is
never treated as proof that native work stopped. Already committed geometry is
not undone by a late Cancel. Use Undo or Saved Delete for completed features.

Fusion geometry calls are synchronous. A single long kernel operation can delay
processing Cancel until Fusion returns to its event loop; this change does not
promise immediate preemption of those calculations.

## Evidence

- 1,245 Python tests and nine Node UI suites pass.
- Regression cases withhold Begin/Preview/Create replies, cancel, begin again,
  then deliver late replies/pushes. They also cover queued commits and retry after
  cleanup failure.
- A headless Edge test loads the complete HTML UI and cancels all nine tools while
  both Begin and Cancel replies are withheld; terminal pushes unlock every tool.
  This uses a simulated native bridge, not the Fusion browser.
- Native Fusion tests enter and cancel the real modal Saved Edit picker twice for
  each of the nine tools via the production palette route. All 18 cancellations
  permit another selection, leave no geometry and restore the caller document.
  These are programmatic native requests, not physical mouse acceptance tests.

See [validation](validation/cancellation-0.34.2.json). Local diagnostics include
palette.cancel.request and palette.cancel.complete with tool/session identity.
