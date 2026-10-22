# Goal
Validate the experimental separate-pin hinge inside Autodesk Fusion on the exact
fixture before expanding the supported geometry or adding another tool.

# Context
The first reported native attempt used a split block/lid with touching bodies
and coplanar front exterior faces. Validate explicit Split seam as well as the
original gapped fixture, either coincident edge pick and version 1 recipe reads.
Read AGENTS.md, docs/hinge-design.md and the native section of docs/development.md.
The planner, temporary BRep adapter, native Create/Edit commands, versioned recipe
and HTML launch controls have local/fake-host checks. The user reached the native
hinge dialog and reported the original axis ownership refusal; the Fusion build
has not been recorded. Temporary-body distance measurements, persistent topology,
Undo and save/reopen still lack native acceptance. Do not call this a finished
generator yet.

# Relevant files/folders
- tools/fusion/HingeFixture/ and tools/fusion/HingeSplitFixture/
- Partelier/partelier/tools/hinge/
- Partelier/partelier/palette.py and palette_protocol.py
- docs/hinge-design.md and docs/development.md

# Constraints
- Use a disposable new document. The fixture script creates one without changing
  the previously active document; do not use a private production model.
- Record the Fusion build/embedded Python. Start with the exact supported root,
  parametric, coplanar-face fixture and default dimensions.
- Preserve source bodies/visibility and unrelated UI. No installer or dependency
  changes. Do not edit or run changes against the StructForge checkout.
- Keep Edit limited to an unchanged, unmoved owned result at the timeline end.
  Refuse absent September 2026 safe-deletion support rather than deleting blindly.
- Repair observed failures in small steps; do not broaden scope to work around a
  failing gate. Keep host geometry and pure planning checks separate.

# Done when
- Native checklist has recorded actual outcomes for preview/Cancel, default and
  no-pin Create, geometry/gaps, source preservation, failure cleanup, Stop/Run,
  Undo/Redo, save/reopen and constrained Edit/Rebuild.
- Temporary BRep minimum-distance and empty-intersection behavior are verified
  explicitly or repaired using a supported equally non-persistent approach.
- Any code fixes pass relevant local checks and the affected native case.
- Stage timings are recorded for the same fixture; no universal speed/fit claims.

# Checks/tests
- Run local unittest discovery, compilation including tools/fusion, and diff/
  direct checks appropriate for the repository's untracked files.
- Run the fixture from Fusion Scripts, link/run Partelier, choose Pin hinge,
  then Set up hinge in Fusion. Follow docs/hinge-design.md selections and outputs.
- If no live Fusion session/control is available, report that condition and leave
  native criteria pending; do not invent native results or substitute mock tests.
