# Fan guards — 0.30.0

Open **Fans & Propellers → Output → Standalone guard**, choose a PC size or
Custom, then choose **Guard design**. The question mark beside Guard design shows
an illustration before New guard or any native preview. Click **New guard** to
preview, then **Create guard**. Saved features provides Edit/Rebuild and Delete.

| Design | Controls |
| --- | --- |
| Radial spokes | Spoke count, bar width and centre diameter |
| Concentric rings | Ring spacing, spoke count, bar width and centre diameter |
| Parallel bars | Spacing and bar width |
| Crossed grid | Spacing and bar width in both directions |
| Honeycomb | Spacing and web width; partial cells end at the circular opening |

Standalone output is one connected body, with a square mounting rim, four through
holes and a flat back at local Z=0. No rotor, deep fan housing or shaft bore is
generated. All five designs are also available under **Rotor + frame + guard**,
which retains three separately owned bodies.

PC presets cover40–140 mm mounting envelopes. **Frame width** is the outer square;
**Fan diameter** plus twice **Radial tip gap** defines the circular patterned area.
**Mount hole spacing** is the horizontal/vertical distance between hole centres.
Hole diameter is an exact clearance bore, not a thread or screw-head seat.
**Guard thickness** controls extrusion depth. **Guard spacing** is the pitch
between repeated bars, rings or hexagon centres, not the clear opening width.
The centre diameter and spoke count appear only for radial/ring designs.

The planner rejects collapsed webs and holes that leave insufficient mounting
rim. Honeycomb is bounded to180 openings; increase spacing when needed. Dimensions
are not silently reduced. Standalone generation bypasses blade construction;
combined output reuses the rotor cache when only guard settings change.

Current saves use52-field recipe4. Exact recipes1–3 remain readable without writes;
explicit Rebuild saves the current schema. Existing guards default to radial
spokes. Preview uses the same opaque shaded mesh as fans, with no permanent
preview geometry.

## Validation

Fusion2706.1.14 disposable PC80 tests passed for all five standalone designs and
one axial rotor/frame/honeycomb combination. Each checked connected guard solid,
four open mounting bores, dimensions, shaded-mesh cleanup, Create, same-body
Rebuild without extra history, and owned Delete. Standalone tests additionally
forbid blade, blower and shaft-bore construction. Every test restored the caller.

Observed standalone preparation times were approximately24 ms spokes,55 ms rings,
51 ms parallel,167 ms grid and578 ms honeycomb. The combined fixture took1.24 s.
These are fixture geometry timings, not promises for every size or machine.
See [native reports](validation/fan-guards-0.30.0.json).

All1203 Python tests and six Node UI suites passed. Headless browser checks at
300/380/520 px verified the relevant controls, five illustrated help entries,
no horizontal overflow and no JavaScript errors; this does not test native pointer
interaction. See [UI report](validation/fan-guards-ui-0.30.0.json).

Physical print quality, airflow and protective performance have not been measured.
