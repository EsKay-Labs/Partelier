# Fixed grille families

Version0.26.1 slopes the external raised frame through its full Height, including
mounting recesses. **Rib top bevel** independently finishes the thin fins.
Auto screw centres retain the0.8mm inward shift. **Screw inset** is beside Screw size
under Advanced → Mounting holes. See [grille controls](grilles.md).

The Grilles dropdown now exposes five real geometric choices:

| Choice | Result |
| --- | --- |
| Linear bars | Existing parallel full-length openings; horizontal/vertical/custom direction |
| Standard · crossed grid | Existing intersecting ribs and square openings |
| Fixed louvers | Existing one-direction inclined apertures |
| Two-way deflection | Opposing fixed banks, separated by a full central rib |
| Four-way diffuser | Nested rectangular aperture rings, a solid centre and diagonal support ribs |

The three directional types use **Louver tilt**, 0–45° from the plate normal,
default 45°. Changing this setting changes the CAD geometry; the resulting
production grille is fixed. It does not have moving vanes or a linked damper.
The two-way style is opposed deflection, not the two independently adjustable
crossed vane layers of an industrial double-deflection grille.

Opening width, Rib width, Border, Cell fillet, Flat/Raised/Raised + chamfer and
mounting holes remain shared controls. Optional screw/head sizes establish the
minimum border before aperture planning. The new designs remain in Saved
features under Grilles and use the same exact-anchor Edit/Rebuild/Delete path.

Four-way diffuser stays centred and aligned to the rectangular face. Choosing
it explicitly zeros Direction/U/V offsets and hides those inapplicable controls;
public settings reject nonzero offsets rather than silently ignoring them.
Its diagonal ribs retain the requested perpendicular Rib width. A narrow final
ring can be partial, while the centre remains solid. Two-way deflection retains
the ordinary rotated-band layout and adds an actual centre rib.

Numeric layouts have at most 200 apertures per face and 400 overall. Density
refusals remain explicit. Per-aperture direction vectors drive the existing
first-wall cutters and raised sections. A raised result uses one perforated base
and at most two loft segments; it creates no native feature per aperture or
corner. The bed-relative side-normal proof still refuses underside slopes beyond
45°. These are geometry checks, not physical print or airflow guarantees.

The settings snapshot has exactly28 fields. Recipe15 defines the full-height
frame transition. Recipe14 added the independent
rib bevel size; recipe13 first admitted the two new shape enums. Exact versions1–14
remain readable without rewriting them; versions1–12 refuse the new enums.
Explicit Create/Rebuild writes15. Existing source-body ownership is preserved.

## Print-in-place trial

The user also approved a real moving-louver experiment. The separate
[print test](../examples/print-tests/pip-louver/README.md) supplies 3MF/STL and
three clearances, 0.25/0.35/0.45 mm. Six captive blades print upright with the
frame back on the bed. Nine closed solids, bed orientation, a 45° underside
bound and sampled motion are checked in Fusion; release and friction have not
been physically tested. There is no production moving-louver/register option
until that print test validates the mechanism. No static grille is labelled a
functional adjustable register.

## Evidence

Local checks include spacing/diagonal thickness, convexity, centred symmetry,
bank directions, rotated central ribs, density preflight, 45° loft bounds,
recipe compatibility and HTML control/help transitions. Browser checks at
300/380/520 px cover all five choices and the two new illustrated help views.

Fusion 2705.1.30 validates the two new styles in Flat/Raised/Chamfer (six cases),
then at 45° with mounting, fillets, cached-mesh preview and a 0/20/45° edit cycle
(two cases). A rotated old-louver case is retained as a regression. All keep the
same source body and restore the caller after the disposable document closes.
Two additional named-history cases verify grouped Edit/Delete and restoration
of the original source after deleting either new grille family.
The multi-case MCP request exceeded its transport timeout, but all three final
case reports completed successfully; this is not a failed geometry result.
See [grille-families-0.25.0.json](validation/grille-families-0.25.0.json).

Manufacturer terminology references: [Price linear bar grilles](https://priceindustries.com/product/lbp-linear-bar/),
[Titus double-deflection grilles](https://www.titus-hvac.com/products/Grilles/122RS),
and [Price opposed-blade dampers](https://priceindustries.com/product/vcs3-opposed-blade-damper/).
The references do not establish airflow, acoustic or printing ratings for these
Partelier shapes.
