# Face details

Six bounded helpers share one planar-face workflow. Select a detail, select the
existing face, adjust dimensions/Position, review live preview, then Create.
Geometry joins or cuts the selected original body; no duplicate result body is
left. Each saved operation has its own editable recipe and BaseFeature/Combine.
Rebuild requires this operation at the timeline end, preserving later edits.

| Detail | Existing geometry | Result |
| --- | --- | --- |
| Finger notch | Planar face with a straight rectangular outer boundary | Half-round cut centred on one boundary; Across/Along move its centre |
| Keyhole slot | Planar face with room for the head and shaft | Circular head entry joined to a narrow rounded hanging slot |
| Motion stop | Planar material below the entire footprint | Attached rectangular stop block |
| Text label | Planar face, installed outline font | Raised or engraved actual font outlines |
| Direction arrow | Planar face | Joined rectangular shaft/triangular arrowhead, raised or engraved |
| Scale marks | Planar face | Evenly spaced ticks, every Nth mark longer |

Depth is explicit, normal to the face; it is not automatically through-all. To
make a through keyhole/notch set depth to the actual wall thickness. Keyhole
width is the head opening diameter, shaft opening is independent, and Length
is the total end-to-end footprint. A motion stop is a fixed block; this tool
does not calculate a moving assembly's travel or contact force.

Position starts at the face bounding-box centre projected into its plane, with
a straight edge giving the direction when available. Finger notch instead
starts at the chosen rectangular boundary side, and ignores Direction.
Across/Along then offset its centre in the common face frame. Try a 100 x 80 x 4 mm plate, a 12 mm notch, or a 12 mm head /
4.3 mm shaft / 20 mm keyhole. These are examples, not hardware fit standards.

Text defaults to Arial. The font must be installed and must yield closed
outlines. Text is bounded to 80 characters, with no rich formatting tags. Height
controls characters; relief depth is separate. Rotation and offsets apply in
the face plane. Scale marks are geometry only, without automatic numeric labels.

Preview uses cached opaque meshes and original material when available. Text
uses a short scratch sketch/extrusion, copies its solid tools, then removes all
scratch history before preview. Every raised footprint is checked for original
material beneath its root. Invalid or disconnected output is refused.

Local evidence: eight tests in tests/test_finishing.py cover settings, footprints,
ownership recipe shape and malformed inputs. All six isolated native Create/Edit
cases pass, including engraving-to-embossing changes for text, arrows and scales.
Three further native cases (text/keyhole/scale) pass cached preview cleanup,
Saved capture/Delete with exact source restoration, and out-of-bound raised
root refusal where applicable. Headless Edge checks all six choices at 320/380 px
with no overflow or JavaScript errors. See [validation](validation/face-details-0.28.0.json).
Physical printability, fit, visual UI acceptance and printed text legibility
remain user acceptance tasks.
