# Palette startup and optional docking

## 0.29.0: recover from pArea during display

Fusion can also raise `InternalValidationError : pArea` from `isVisible=True`,
before the optional docking request. Partelier now makes one bounded recovery:
remove its event handlers and failed palette, recreate the HTML palette with a
fresh ID and visibility enabled at creation, and request floating placement.
The fresh ID bypasses the previous native dock-area entry. Close still destroys
the replacement and cancels previews. Other display errors propagate normally;
a failed recovery is cleaned up and never retried in a loop.

Two regression cases cover successful recovery and a second failing display,
including handler retirement and cleanup. A native fault-injection fixture
exercises the actual replacement, floating display and Close/reopen in Fusion
2706.1.14, preserving the caller's document, timeline, bodies and visibility.
Normal reload also starts 0.29.0 successfully. See
[native recovery](validation/palette-recovery-0.29.0.json).

## Historical 0.27.1 docking correction

The reported 0.27.0 startup failure was recorded as
`RuntimeError: 2 : InternalValidationError : pArea` from the native
`Palette.dockingState` setter. It propagated through `ToolLibrary.show()` and
caused add-in startup to tear down all managers before the library appeared.

The library now attaches its HTML/Close handlers, makes its palette visible,
and only then requests right docking. A RuntimeError from this optional layout
setting records `palette.docking.unavailable` and leaves the live palette open
without docking. Creation, display and handler-registration failures still
propagate. An existing palette is shown without forcing its docking position
again; Close still cancels sessions and retires the page.

Autodesk's [palette sample](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/PaletteSample_Sample.htm)
also displays a palette before setting its docking state. Its
[docking property documentation](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Palette_dockingState.htm)
describes docking as a layout setting. This fix does not assume that visibility
alone guarantees docking on every startup state; the nonfatal fallback is
covered independently.

Validation on 2026-11-03:

- Three new local regression tests reproduce a hidden-palette docking failure,
  an unavailable native docking area with a usable HTML bridge and Close/reopen,
  and a genuine display failure that must still propagate.
- 1,132 Python tests, six Node UI suites, compilation and whitespace checks pass.
- Installed 0.27.1 starts in Fusion 2706.1.14 with a valid visible palette and
  right docking. Actual HTML `ready`, `operations_list` and `ui.connected`
  events complete with UI build 0.27.1.
- The active document, two open documents, timeline state, body objects, names
  and visibility match the state before reload. No geometry test or document
  creation is required for this startup correction.

Native unavailable-docking fallback is simulated by the local tests; the native
check observed successful docking. See
[palette-startup-0.27.1.json](validation/palette-startup-0.27.1.json).
