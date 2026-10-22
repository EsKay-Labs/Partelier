# Hinge families and next native checks

The user requested all three additional families: barrel, concealed and
print-in-place. This records the scope; these are not implemented choices in
the palette. Finish native acceptance of the current HTML workflow and separate
leaves before adding a new mechanism family. Each family needs its own bounded
geometry, source selection, editable recipe and motion/printing fixture.

| Family | Intended result | Required next specification |
| --- | --- | --- |
| Current pin hinge | Attached source copies, or separate rectangular/rounded leaves with optional through-holes | Native HTML selection/Preview/Create/Edit, hole dimensions, gaps and source preservation |
| Barrel | Compact cylindrical mounting form with a defined pin/retention system | Mounting-pocket axes/depth, actual barrel diameter, attachment mode, retained pin and rotation clearance |
| Concealed | Mechanism positioned inside the closed parts | Choose single-axis recessed or multi-link topology first; define internal pockets, opening angle and interference sweep |
| Print-in-place | Assembled moving geometry printed together | Print direction, captive axis/retention geometry, radial/axial gaps, supported underside slopes and slicer/physical coupon |

For print-in-place, 45-degree underside chamfers are an initial design target,
not a blanket operation on every edge. Record the angle relative to the build
plate and the selected print direction. Avoid downward-facing fillets and
unsupported internal roofs where the intended orientation cannot print them.
Do not merely relabel the current separate straight pin as print-in-place:
captive retention and motion geometry must be explicitly designed and tested.

A default 45-degree slope should be adjustable in that family's future inputs.
No universal overhang limit or clearance guarantees are implied. Prusa's
[modeling guide](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135)
explains the orientation/nozzle/settings dependence and recommends chamfers
rather than bed-facing fillets. Its
[support guide](https://help.prusa3d.com/article/support-material_1698)
also distinguishes overhang angles measured from the horizontal plane.

For every new family, add a small disposable dimensional fixture and require:
non-overlapping solids, the intended movement through its range, native
Preview/Cancel/Undo/Edit checks, a slicer layer review in the recorded orientation,
and a printed fit coupon before claiming a working print-in-place mechanism.
Source-body mounting holes and countersinks/counterbores can be separate options
after the existing through-hole leaf path passes native acceptance.

## Shared appearance

The user also requested a general chamfer finish for a consistent appearance,
not only local underside overhang relief. The current pin hinge now has one
optional cosmetic size for generated leaves/webs, barrel/pin ends and hole entries.
Future families should reuse the intended finish contract where their geometry
allows it, while protecting joint interfaces and retaining their own validated
motion/clearance rules. The cosmetic switch does not implement any planned
family or substitute for print-in-place orientation/retention design.

## Implemented design increment: pin-hinge variants (0.3.0; native checks pending)

Goal: make the existing mechanism useful in several visually distinct forms,
with a readable blue light interface. These are pin-hinge geometry variants,
not additional mechanism families. Keep direct model picking and the same
Preview/Create/Edit transaction and ownership boundaries.

- Classic: five round knuckles, sharp finish.
- Soft: five round knuckles, 0.6 mm roundovers on generated external primitive
  edges and rounded bore/hole mouths. Round the new webs/leaves and pin ends;
  preserve source geometry. This is not a general blend at the concave joints
  where generated solids meet each other or a source body.
- Linear: five square knuckle housings inscribed in the circular envelope,
  0.3 mm chamfers, flat leaves.
- Compact: three round knuckles with the Soft finish.
- Piano: eleven round knuckles with chamfer finish. Dimensions/length remain
  editable; the name does not imply a load rating or hardware standard.

Presets change only profile, knuckle count and finish; placement, dimensions,
output and screw options remain user-controlled. Store the complete resulting
settings, not an implicit preset name. Changing these values yields a custom
configuration. Rounded treatment uses radius, chamfer uses equal-distance size;
these are mutually exclusive. Legacy recipes read as round profile with no
roundovers, retaining their prior chamfer setting. Increment the recipe schema
and keep reads strict and non-mutating.

Use transient analytical boxes/cylinders/spheres/tori for exact bounded primitive
roundovers shared by Preview/Create. Do not create temporary document features
for preview, silently skip failed fillets or alter original source edges. Check
material/contact, pin/bore, hole lips and dimensions before kernel work. Native
booleans, Undo/Edit and performance remain separate acceptance checks.

Done when: all five presets map to actual geometry/settings; Linear has square
housings and Soft has curved solids rather than illustration-only changes; old
recipes load without mutation; UI has strong blue boundaries/text and usable
318 px and wide layouts. Run pure/adaptor/UI contracts, Python/JS syntax and
browser checks. Other families remain visibly planned until their own topology,
attachment and motion fixtures are implemented.
