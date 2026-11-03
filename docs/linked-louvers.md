# Mechanically linked louvers

This is a separate assembly with two frame halves, one rotating vane/crank per
row, and one common link bar. All crank arms have the same radius. Their outer
pivot centres remain one exact vane pitch apart for every requested angle, so a
single rigid link can turn every vane together. The bar moves along a circular
arc while remaining parallel to the frame; it is not a guided straight slider.

Select **Linked louvers** under Mechanical pairs. The initial 80 x 100 x 18 mm
frame has five vanes and 3 mm nominal linkage fasteners. Set angle 0–60 degrees
to review the assembled positions. Angle changes actual blade and crank poses.
The CAD output does not create native Fusion assembly joints or simulate forces.

**Assembled** places matching pivots, bearings and link bores in their working
positions. **Flat print layout** separates the frame halves, rests each on its
outer back, places vanes flat at zero angle, and lays the link on its broad face.
The split bearing sockets remain open upward; vane journal edges use diamond
sections and crank bores have 45-degree roofs. Root geometry guards reject vane
and crank sizes whose conservative swept envelopes would overlap.

This is **not print-in-place**. Assembly requires four frame screws/bolts and
one shoulder screw or pin at each crank/link pair. These are hardware interfaces,
not generated hardware pockets. Fastener diameter is nominal shaft diameter;
clearance is added radially to both crank and link bores. A space of fastener
diameter + wall thickness + twice clearance separates cranks from the frame,
providing access for separate retainers. Actual screw heads/nuts, length,
washers and retention choices must be checked against the hardware used.

Assembly order:
1. Put the back half flat and place all vanes into its open bearing channels.
2. Fit the front half, trapping the integrated journals; fasten the four corners.
3. Align the common bar with all crank eyes and install the individual pivots.
4. Confirm free axial/radial clearance before tightening retaining hardware.

Use Flat print layout for slicing. The assembled arrangement is a motion review,
not a support-free print arrangement. Physical release, wear, friction, airflow
and repeated actuation have not been validated. Native sampled motions are
finite interference checks, not a continuous collision sweep.

Developer validation: tests/test_linked_louver.py verifies exact link pitch at
61 analytical angles and conservative envelopes. LinkedLouverValidation.py
checks temporary solid geometry, simultaneous 0–60-degree poses every10degrees,
all body pairs at each pose, and the flat layout's bed contact/underside faces.


Native Fusion validation passed eight solids, seven simultaneous poses,196
pairwise interference checks and464 underside-face checks in the flat layout.
See [the validation report](validation/linked-louver-0.29.0.json). This remains
geometric evidence, not a physical printing or airflow measurement.
