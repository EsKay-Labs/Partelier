# Close cancels the active tool — 0.25.1

The main Partelier palette's native **Close / X** now cancels active work and
disposes the HTML page. Previously Fusion hid the palette while sessions,
selection handlers and queued preview requests remained active.

- Pin hinges, snap-fits, patterns, grilles, trusses and small details release
  their active references/pickers and preview graphics, restoring leased body
  visibility. Shared managers cover the related tool sections.
- Pending preview requests are cancelled before cleanup, so a delayed completion
  cannot draw again. A cancelled native command drains without computation or
  persistence; its registration remains available for a new session.
- Pending Create/Rebuild/Delete dispatches cannot apply after Close. A Close
  received during the opening-state notification is checked before launching
  the native transaction. A queued hinge command cannot fall back to opening a
  legacy configuration dialog after cancellation.
- Completed features remain in the design. Close does not delete or Undo them.
- Reopening creates a fresh HTML page. Per-page generation checks reject old
  messages and delayed Close callbacks even after the new page becomes active.
  Ordinary settings, recipes and protocol snapshots are unchanged.

Fusion API operations execute on the main thread. A synchronous geometry call
that has already entered the SDK cannot be interrupted from the palette while
that thread is blocked. Cancellation takes effect when Fusion next processes
the event; it does not forcibly kill Fusion or interrupt an arbitrary native
transaction belonging to another tool. Cleanup failures are reported and the
other tool cleanups still run.

## Checks

1,103 Python tests and the five existing Node UI suites pass. Added cases cover
queued and ready previews, opening-state reentrancy, blocked old-page requests,
picker interruption, side-picker release, pending deletion, cleanup failures,
Close handler removal, reopening and unrelated-command preservation.

The native [PaletteCloseProbe](../tools/fusion/PaletteCloseProbe.py) uses a
disposable document and invokes the registered Close callback programmatically.
It verifies a ready editing preview is removed, original visibility returns,
the previously created operation remains, the reopened page rejects old
callbacks, and a delayed queued driver performs no computation or drawing.
The caller document is restored unchanged. Setup and completion run outside
the Fusion MCP outer transaction, and the check waits for the owned native
command's Destroy before asserting that it is idle. This is native callback
and graphics evidence, not manual pointer testing of Fusion's X button.
Evidence: [palette-close-0.25.1.json](validation/palette-close-0.25.1.json).
