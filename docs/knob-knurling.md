# Knurling for knobs

Select one complete external cylindrical face of an existing solid knob in a
root, history-enabled Fusion design. Ten styles are available: Diamond, Straight
V grooves, Helical, Chevron, Waves, Rounded flutes, Scallops, Dimples, Pyramids
and Rings. This dedicated tool is separate from Surface patterns → Grip texture.

Version 0.34.1 fixes startup defaults being overwritten by the last completed
session. Reopening the palette starts with Full cylinder; active sessions and
Saved Edit retain their own settings.

## Workflow and defaults

1. Design the cylinder and shaft bore first. Open Knob knurling and use the
   illustrated `?` help to inspect a style before selecting geometry.
2. Choose **Cut inward** (default) or **Raised outward**. Depth is radial:
   0.6 mm outward relief can increase the diameter by up to 1.2 mm.
3. Select the outside cylindrical face. **Full cylinder** is the default:
   border 0 takes the texture to both ends, with no mandatory smooth bands.
4. Optionally choose **End borders** and their width. These smooth bands include
   45-degree transitions into the texture.
5. Configure **Top edge** and **Bottom edge** independently: None, Chamfer or
   Fillet, each with its own size. Finishes may trim the texture near the ends.
6. Review the opaque preview and Create. Saved features provides Edit/Delete.

Other defaults are target spacing 6 mm, depth 0.6 mm, pattern angle 30 degrees
and rotation 0. Whole repeats fit the circumference; actual spacing may differ
slightly. Finish size defaults to 0.6 mm when enabled. With raised relief and
end borders, each finish must fit within its border; Full cylinder permits
larger finishes. Incompatible settings are refused, never silently reduced.

Preview and Cancel leave the source unchanged. Create and Rebuild modify the
original body, preserving a sufficiently thick shaft bore. They do not create a
duplicate knob. Existing 0.33 features keep their old geometry until explicitly
rebuilt through **Saved → Edit → Rebuild**; opening them does not migrate the model.

## Edge shape and printing orientation

Print **bottom-down with the cylinder axis upright**. Top and bottom refer to
the tool's cylinder frame; inspect the preview before choosing the print end.
The cylinder can be oriented differently in the CAD document. Turning the print
onto its side or swapping the ends with a top fillet invalidates this assumption.

Chamfers have equal rise and run (45 degrees). The top fillet is a full circular
quarter-round. The bottom fillet is a true circular **partial round starting at
45 degrees**, then turning into the vertical side. This avoids the shallow
unsupported underside of a full lower quarter-round. For radius r, its axial
height is about 0.707r and its radial trim about 0.293r. It is intentionally
different from the top fillet.

Slope checks apply to the generated grip and transitions, not every pre-existing
feature of the knob. Physical print quality and fit still require a print test.

## CAD geometry and limits

Version 0.34 replaces the faceted envelope with native CAD: planar V cuts,
helical ruled surfaces, cylindrical flutes, spherical dimples, conical rings
and toroidal fillets. Waves use C1 cubic curves with bounded slopes. Sharp
edges defining a diamond or pyramid remain real design edges; they are not
mesh triangulation. The display preview still uses a cached lit mesh for speed,
while the saved result is a solid BRep.

Planning is cached and bounded to 64 circumference repeats and 128 cutters.
No geometry is recomputed during orbit. Dense settings request a wider spacing
rather than creating unlimited geometry. Native timings depend on shape and
size; a tested diameter 30 × height 20 mm diamond prepared in about 1.08 s and
created in about 0.87 s on the test machine.

The source must retain 0.8 mm of continuous wall below its deepest texture or
finish cut. A clear outer carrier prevents accidental changes to nearby material.
Full-height texture may require a free end: an abrupt return to the original
diameter above an inward cut, or raised ridges starting above the base, can
create unsupported ledges. Use smooth end borders for those cases. This check
is deliberately conservative for knobs with connected geometry beyond the face.

## Runtime and validation

Strict eleven-field settings and recipe2 belong to `tools/knurl`, alias
`knurling`. Recipe1 reads with inward mode and no finishes while retaining its
saved borders. The owned operation graph can be Cut, Join, Cut+Join or Join+Cut.
Graph changes rebuild only the exact owned suffix and keep the source identity.

Native checks run individually in disposable documents, restoring the caller
and camera. They cover all ten styles, inward/outward mode conversions,
top/bottom finishes, optional bands, hollow and tilted knobs, guarded refusals,
preview cleanup and same-body Create/Rebuild/Delete. Analytic slope bounds are
supplemented by sampled native surface normals; these are not physical print
certification. See [0.34 evidence](validation/knurling-0.34.0.json).
