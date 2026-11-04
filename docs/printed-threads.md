# 3D printed threads — 0.31.0

Select **3D printed threads** in the tool menu. This release provides three
profiles and four output modes, with the same Saved features Edit/Delete flow
as other Partelier tools. The question marks show diagrams before preview.

## Defaults and fit meaning

The starting preset is **Printable V**, nominal diameter24 mm, pitch3 mm,
thread length12 mm, radial clearance0.25 mm per side, entry lead-in1 mm,
one right-hand start and automatic depth. Select the intended cylindrical face
to fit its diameter. The coarse, truncated printable profile is intended for
printing with the thread axis upright. Defaults are starting dimensions, not
a measured printer/material calibration.

| Mode | Clearance application | Existing geometry required |
| --- | --- | --- |
| External | Reduce the male radii by clearance | Complete outer cylindrical shaft face |
| Internal | Enlarge the female cavity radii by clearance | Complete inner cylindrical bore face |
| Matched pair | Male stays nominal; enlarge the female once | Outer shaft, then bore on a different body |
| Fit coupon | Nominal male and three female allowances | None; four separate bodies are generated |

For example0.25 mm per side changes the relevant diameters by0.50 mm. This is
**radial allowance**, not a measured normal gap between inclined flanks. When
making two printed parts together, use Matched pair so allowance is not applied
independently to both sides. Independently created external and internal outputs
with positive allowance would produce the sum of those allowances.

The printable profiles infer nominal diameter from the first selected cylinder:
external uses its outside diameter; internal uses bore diameter plus twice thread
depth minus twice clearance. Metric retains the chosen nominal diameter. Changing
pitch/depth after selection keeps the nominal diameter and may require a different
bore. Oversized holes are refused rather than silently filled with material.

## Profiles

- **Printable V:** custom90-degree included profile with truncated crest, auto
  depth0.35×pitch and crest width0.2×pitch. Valid custom depths retain45-degree
  flanks in the axial section. The helical normal check covers upright flanks,
  not arbitrary model orientation or printer performance.
- **Rounded:** the same printable envelope with rounded crest corners represented
  by bounded quadratic-curve chords. It is not a standard round-thread designation.
- **Metric:** nominal60-degree profile with coarse M6, M8, M10, M12, M16, M20, M24,
  M30 and M36 presets. Nominal external root depth is17H/24 and root radiusH/6,
  where H=√3×pitch/2; root arcs are approximated with bounded chords. Internal
  geometry is the radially enlarged mating envelope. This is not a certified6H/6g
  tolerance-class implementation. Actual mating with purchased hardware needs a
  fit test. Metric does not share the printable profile's45-degree flank property.

Advanced controls include exact pitch, automatic/custom depth where supported,
start offset, right/left direction and1–3 starts. Axial travel per turn equals
pitch×starts. Both mating parts must share profile, pitch, starts and handedness.
Lead-in creates45-degree conical relief at both ends, narrowing male tips and
widening female entries. The nominal diameter remains the pre-clearance size.

## Worked examples

**Printed lid and neck:** prepare a cylindrical outer neck and a smaller bore
inside a separate lid. Choose Matched pair and Printable V, select the neck first,
then the lid's inner cylindrical face. The picker advances automatically; preview
waits for both selections. Keep the axis upright when arranging each part for
printing. Use the offset to locate the thread span. The preview reveals the
inferred start end. A previously threaded or partially trimmed face is not a new
source face; use Saved features to edit an existing Partelier thread.

**Internal thread for an existing screw:** model a cylindrical bore and leave
enough surrounding wall. Select Internal, Metric and the nominal screw size/pitch.
Then select the bore. A smaller bore can be enlarged by the cutter; a bore already
larger than the thread roots is refused. This implementation requires a complete
material band around the thread and entry relief, retaining at least0.8 mm.

**Printer fit test:** choose Fit coupon. Its explicit preset uses6 mm thread
length,3 mm nut wall and0.1 mm clearance step. It creates one male grip and three
nuts at0.15/0.25/0.35 mm per-side allowance. One/two/three small raised exterior
marks identify the nuts after slicing. Body names also record the clearance;
generated names update on Rebuild, while user names are preserved. Print them as
separate parts, compare fit, then transfer the preferred value to the real model.
The coupon does not automatically calibrate a printer or store material profiles.

Sources must be native root-component solids in a history-enabled design, with
complete cylindrical faces bounded by two full circular edges. Length plus offset
must fit the selected span. Partial cylinders, conical threads, pipe standards,
trapezoidal and buttress families are not included in this first release.

## Implementation and validation

Native helix wires and ruled surfaces form closed temporary BReps; core and
ridges join before final clipping. No sketches or native features are made per
turn. Geometry is bounded to32 turns per start. Preview uses cached opaque lit
meshes. Original sources stay intact until Create; attached output consumes
owned Cut tools without duplicate source bodies. Exact recipe1 stores13 settings.
Cancel/Close restores source visibility; owned Delete restores preceding geometry.
Saved Edit retains body identities and history size. Automatic updates retain the
common source/ownership guards and may refuse an upstream diameter change that
no longer matches the saved nominal size.

Native Fusion2706.1.14 fixtures cover all four modes, all three profiles, a left-hand
two-start pair, default12 mm length, fractional-length Rebuild, mesh cleanup,
same-body persistence and Delete. Every fixture restored the caller document.
Male containment inside its matching female cutter was checked at the assembled
pose; this is not a full motion or force test. Separate staged production-command
checks cover preview, Cancel, Create, saved Edit preview, Cancel and Delete.

Initial small fixture preparation observations: about0.38 s external Printable V,
0.36 s internal,1.02 s matched pair,1.49 s coupon,1.50 s Rounded pair and3.83 s
Metric pair. The12 mm Printable V pair took2.22 s. These measure fixture preparation,
not guaranteed complete UI response times.

All1220 local Python tests and seven Node suites passed. Browser checks at
300/380/520 px cover all profiles/modes, illustrated help and layout overflow.
Programmatic native selections and browser simulation do not certify real pointer
selection, printed fit, strength or repeated-use durability.

Evidence: [native geometry/lifecycle](validation/printed-threads-0.31.0.json),
[production commands](validation/thread-session-0.31.0.json),
[UI](validation/thread-ui-0.31.0.json).
