# Parallel-lift linkage

This is an equal-arm four-bar linkage. Two mounting plates are joined by two
arms of the same length and four spaced pivot axes. As the arms turn, the
moving plate remains parallel to the fixed plate and translates along an arc.
It is useful for a raised cover or guided lift. It is **not** a swinging
furniture concealed hinge and does not rotate a lid through90degrees.

Select **Parallel-lift linkage** in Mechanical pairs. The initial dimensions are
30mm arm length,50mm pivot spacing,16mm mounting-plate height,2mm wall/plate
thickness and3mm nominal pivot hardware. Angle0–60degrees selects an actual
assembled pose; at60degrees the nominal lift is30×sin60≈25.98mm. The model does
not contain physical end stops or native Fusion assembly joints.

Eight printable bodies are generated:
- Fixed and moving mounting plates, each with two pivot and two mounting bores.
- Two matching arms, with a bore at each end.
- Four spacer collars that maintain axial spacing at the pivot joints.

Assembly requires four shoulder screws/pins with suitable retention, plus
hardware to mount each plate to its part. The shafts, heads and nuts are not
included as generated hardware. Bore radius is half nominal shaft diameter
plus Clearance. Spacer length is nominal shaft diameter + wall thickness +
twice Clearance; verify this against the actual fastener head and nut dimensions.
The plate/arm separation permits access to retainers without placing the unused
opposite mounting plate directly against a joint head.

**Assembled** presents the physical pivot alignment. **Flat print layout** lays
all eight parts on their broad backs in separate columns, with bores vertical.
Both layouts produce the same part geometry and count. Printed fit, friction,
wear, load capacity and mounting clearances need real-world tests. Near the
zero-angle aligned position a four-bar can be mechanically singular; the
geometry controls do not predict the force needed to start movement.

The first supported arrangement is a separate assembly. It does not cut recesses
into arbitrary user bodies, conceal itself automatically, or establish a safe
lifting load. Place it into the design using the app position/direction controls.

Developer checks: test_parallel_lift.py verifies exact equal-arm lengths and
parallel plate spacing across61analytical angles, and rejects thin/overlapping
input envelopes. ParallelLiftValidation.py checks all eight native solids,
seven poses every10degrees from0to60, all pairs for interference, and the flat
print layout for bed contact and underside orientation. Discrete motion samples
are not a continuous collision sweep.


Native Fusion checks passed eight solids, seven simultaneous poses,196pairwise
interference checks and44underside-face checks in the flat layout. The sampled
maximum lift is25.98mm. See [the validation report](validation/parallel-lift-0.29.0.json).
