"""Read-only witnesses for the joined round/tangent cap contour.

Native finishing owns the complete solid. This module only checks analytic
roof/cylinder continuity on detached copies; it adds no material, constructs
no helper solids and changes no requested dimensions. Samples outside the
actual raw surface neighborhood cannot assert a contour requirement.
"""

from dataclasses import dataclass
import math

from .support import plan_tangent_support


def _adapter():
    from . import fusion
    return fusion


@dataclass(frozen=True)
class CapContourWitness:
    cap: str
    depth_mm: float
    u_mm: float
    side: str
    raw_inside_point_mm: tuple
    raw_outside_point_mm: tuple
    inside_point_mm: tuple
    outside_point_mm: tuple


def plan_tangent_contour_witnesses(web, barrel_radius, fillet, *, attached, shift_mm=0):
    """Exact planar and circular cap profiles, all in the original hinge frame.

    U points along the roof toward the shared tangent. A reflected B uses the
    reflected U, so negative u is always roof-side. At cap depth d the normal
    setback is e=r-sqrt(r^2-(r-d)^2). For u<=0 the roof has v=-e;
    for u>0 the circular side has v=-R+sqrt((R-e)^2-u^2).
    """
    values = (barrel_radius, fillet, shift_mm)
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not math.isfinite(value) for value in values):
        raise ValueError("Cap contour dimensions must be finite numbers in mm.")
    if not 0 < fillet < barrel_radius or not web.y_max_mm - web.y_min_mm > 2 * fillet:
        raise ValueError("Cap contour checks need a positive fillet below the barrel radius and half the knuckle length.")
    taper = plan_tangent_support(web, barrel_radius, attached=attached)
    tx, tz = taper.tangent_xz_mm
    nx, nz = tx / barrel_radius, (tz - barrel_radius) / barrel_radius
    sign = 1 if web.owner == "A" else -1
    ux, uz = sign * nz, -sign * nx
    delta = min(.005, fillet / 50)
    offsets = (-2 * fillet, -fillet, -fillet / 2, -fillet / 30,
               0, fillet / 30, fillet / 2, fillet)
    depths = (min(.05, fillet / 4), fillet / 2, .9 * fillet)
    witnesses = []
    for cap, position, inward in (("start", web.y_min_mm + shift_mm, 1),
                                  ("end", web.y_max_mm + shift_mm, -1)):
        for depth in depths:
            setback = fillet - math.sqrt(depth * (2 * fillet - depth))
            remaining_radius = barrel_radius - setback
            for u in offsets:
                if u > 0 and u >= remaining_radius:
                    continue
                raw_v = 0 if u <= 0 else -barrel_radius + math.sqrt(barrel_radius ** 2 - u ** 2)
                finish_v = -setback if u <= 0 else -barrel_radius + math.sqrt(remaining_radius ** 2 - u ** 2)
                y = position + inward * depth
                def point(v):
                    return (tx + ux * u + nx * v, y, tz + uz * u + nz * v)
                points = (point(raw_v - delta), point(raw_v + delta),
                          point(finish_v - delta), point(finish_v + delta))
                if not all(math.isfinite(value) for sample in points for value in sample):
                    raise ValueError("Cap contour coordinates overflow at these dimensions.")
                witnesses.append(CapContourWitness(cap, depth, u,
                    "roof" if u <= 0 else "cylinder", *points))
    return tuple(witnesses)


def _placement_shifts(settings, role, layout):
    placements = tuple(layout.placements) if layout is not None else ()
    if settings.output_mode == "attached":
        return tuple(item.center_mm for item in placements) if placements else (0,)
    if "_" not in role:
        if len(placements) > 1:
            raise ValueError("A separate roof result is missing its hinge placement index.")
        return (placements[0].center_mm,) if placements else (0,)
    try:
        index = int(role.split("_", 1)[1]) - 1
    except ValueError as error:
        raise ValueError("A separate roof result has an invalid placement index.") from error
    matches = tuple(item.center_mm for item in placements if item.index == index)
    if len(matches) != 1:
        raise ValueError("A separate roof result does not match one hinge placement.")
    return matches


def validate_tangent_roofs(frame, settings, role, raw, finished, *, plan, layout=None):
    """Refuse an observed C1 discontinuity; return the SAME unmodified solid.

    Both sides must be checkable at each sampled cap/depth. Farther roof/root
    samples are considered only where raw containment proves the intended
    analytic surface and enough material for that inward contour witness.
    This is bounded geometry evidence, not a proof of the complete solid.
    """
    if (not settings.fillet_edges or settings.web_profile != "tangent"
            or settings.knuckle_profile != "round" or role.startswith("pin")):
        return finished
    adapter = _adapter()
    adapter._require_main_thread()
    for body in (raw, finished):
        adapter._require_body(body, "Cap contour checks need one valid temporary solid.")
        if body.isTemporary is not True or not math.isfinite(body.volume) or body.volume <= 0:
            raise adapter.HingeGeometryError("Cap contour checks need one positive temporary solid.")
    _, fusion = adapter._api()
    containment = fusion.PointContainment
    inside_labels = {containment.PointInsidePointContainment, containment.PointOnPointContainment}
    outside_label = containment.PointOutsidePointContainment
    def occupied(body, point):
        result = body.pointContainment(adapter._point(frame, *point))
        if result in inside_labels:
            return True
        if result == outside_label:
            return False
        raise adapter.HingeGeometryError("Fusion could not classify a tangent cap contour witness.")
    try:
        owner = role.split("_", 1)[0]
        shifts = _placement_shifts(settings, role, layout)
        webs = tuple(web for web in plan.webs if web.owner == owner)
        if owner not in {"A", "B"} or not webs:
            raise ValueError("Cap contour checks need matching A/B attachment webs.")
        for shift in shifts:
            for web in webs:
                witnesses = plan_tangent_contour_witnesses(web, plan.barrel_radius_mm,
                    settings.fillet_radius_mm, attached=settings.output_mode == "attached", shift_mm=shift)
                coverage = {}
                for witness in witnesses:
                    key = (witness.cap, witness.depth_mm)
                    checked = coverage.setdefault(key, set())
                    if (not occupied(raw, witness.raw_inside_point_mm)
                            or occupied(raw, witness.raw_outside_point_mm)
                            or not occupied(raw, witness.inside_point_mm)):
                        continue
                    if (not occupied(finished, witness.inside_point_mm)
                            or occupied(finished, witness.outside_point_mm)):
                        raise adapter.HingeGeometryError(
                            "Fusion's joined fillet is discontinuous at the " + role + " " + witness.side
                            + " cap contour (" + witness.cap + ", depth " + format(witness.depth_mm, ".6g")
                            + " mm). Reduce the fillet radius or use chamfer edges. "
                            "No repair or size change was applied.")
                    checked.add(witness.side)
                if not coverage or any(sides != {"roof", "cylinder"} for sides in coverage.values()):
                    raise adapter.HingeGeometryError(
                        "The raw geometry does not expose both sides of the tangent cap contour. "
                        "Inspect the attachment or use chamfer edges; the fillet could not be verified.")
        return finished
    except (ValueError, TypeError, OverflowError, ZeroDivisionError) as error:
        if isinstance(error, adapter.HingeGeometryError):
            raise
        raise adapter.HingeGeometryError(str(error)) from error
