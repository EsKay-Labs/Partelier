# Automatic updates (0.29.0)

Saved features has an **Update features after source edits** switch, stored per
design. It defaults to on. Keep the Partelier palette open, finish the current
Partelier preview, then edit an upstream sketch or extrusion normally in Fusion.
After the native modeling command finishes, Partelier rebuilds dependent features
in history order in one undoable native transaction.

New features enroll automatically. Features from earlier releases need one
explicit **Edit → Rebuild** to save their initial source and ownership baseline.
Listing a feature never enrolls it or overwrites its baseline. Independent
mechanisms without source references have nothing to follow.

The service uses completed command events and inexpensive body/sketch revision checks.
There is no timer, orbit callback, continuous geometry scan or background Fusion
API worker. It does not rebuild during a preview, after Undo/Redo, while the
palette is closed, or while another native command is active. Reopen and make a
modeling edit or use explicit Rebuild if a source was changed while it was closed.

## Ownership and failure behavior

Only the exact owned operation receives temporary permission to rebuild against
changed upstream geometry. Target identity, tool ownership, contiguous native
history and recipe checks remain in force. Source references must still resolve
unambiguously. Split/deleted faces, manually edited generated tools, unsupported
feature insertions or invalid dimensions stop the update with an explanation.
The automatic native transaction rolls back if any operation or baseline renewal
fails; the user's preceding source edit remains a separate action. After failure,
updates pause for that design, preventing repeated attempts. Fix the cause or use
explicit Edit to reselect references, then re-enable the Saved switch for subsequent
source edits. Do not change generated tools directly and expect
Partelier to infer a new recipe.

Supported adapters include hinges, snap-fits, patterns/grilles/trusses, lip/groove
and other small details, face details/labels, referenced fans and attached
mechanical pairs. Circular fan references refit the rotor diameter while retaining
the requested tip gap; other feature dimensions remain the saved settings.

## Evidence

On Fusion 2706.1.14, an actual external native command changed a scratch plate
from 4 to 6 mm. The production command-terminated/custom-event service updated
two saved face details without a direct test call to the refresh function.
Source body identity, name, visibility, settings and history count were preserved.
The scratch document was closed and the caller restored.

A second production test deliberately moved the second operation's owned cutter.
The first feature rebuilt, the second ownership guard refused, and Fusion rolled
back the complete batch, including recipes and baselines. The source edit remained.
Exactly one rebuild attempt occurred; the failure latch prevented retry loops.
See [rollback evidence](validation/auto-update-rollback-0.29.0.json).

Separate native adapter checks cover sharp/filleted hinges, snap hook, attached
slider, through patterns, grille, circular-fit blower, sketch blade outline and lip/groove. Repeated
refreshes with unchanged sources are no-ops. See the reports in
[validation](validation/). These checks do not establish every possible topology
change or acceptance across arbitrary downstream Fusion features.
