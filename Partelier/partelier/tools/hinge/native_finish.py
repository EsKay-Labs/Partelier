"""Native finishing of joined copies inside a caller-owned command transaction.

No document or command is created here. The caller must run this on Fusion's
main thread inside executePreview/execute and abort that transaction on failure.
Only helper-owned copied bodies and native features are persisted temporarily.
"""

import math
import uuid
from dataclasses import dataclass

from .support import plan_tangent_support
from .roof_finish import validate_tangent_roofs


def _adapter():
    from . import fusion
    return fusion


def _error(message):
    return _adapter().HingeGeometryError(message)


def _xyz(point):
    return (float(point.x), float(point.y), float(point.z))


def _unit(vector):
    vector = tuple(float(value) for value in vector)
    length = math.hypot(*vector)
    if len(vector) != 3 or not math.isfinite(length) or length <= 1e-14:
        raise ValueError("A finish edge has an invalid normal.")
    return tuple(value / length for value in vector)


def classify_edge_point(point, normal_one, normal_two, contains, epsilon_cm):
    """Classify a manifold edge using outward normals and local containment.

    ``contains`` accepts a coordinate tuple and returns inside/outside/on/unknown.
    Tangency is checked before containment. Ambiguous probes are refused rather
    than guessed, because rounding a concave edge could fill movement clearance.
    """
    point = tuple(float(value) for value in point)
    if (len(point) != 3 or not all(math.isfinite(value) for value in point)
            or not math.isfinite(epsilon_cm) or epsilon_cm <= 0):
        raise ValueError("A finish edge has invalid sampling coordinates.")
    one, two = _unit(normal_one), _unit(normal_two)
    cosine = sum(a * b for a, b in zip(one, two))
    if cosine >= 1 - 1e-8:
        return "tangent"
    if cosine <= -1 + 1e-10:
        raise ValueError("Opposing finish faces cannot be classified safely.")
    direction = _unit(tuple(a - b for a, b in zip(one, two)))
    for multiplier in (1, 4, 16):
        probes = [contains(tuple(value + sign * epsilon_cm * multiplier * step
                                 for value, step in zip(point, direction)))
                  for sign in (-1, 1)]
        if probes == ["outside", "outside"]:
            return "convex"
        if probes == ["inside", "inside"]:
            return "concave"
        if all(value in {"inside", "outside"} for value in probes):
            break
    raise ValueError("A finish edge is too close to another boundary to classify safely.")


def _samples(edge):
    evaluator = edge.evaluator
    success, low, high = evaluator.getParameterExtents()
    if not success or not all(math.isfinite(value) for value in (low, high)) or high <= low:
        raise _error("Fusion could not sample a joined finish edge.")
    points = []
    for fraction in (0, .211324865405187, .5, .788675134594813, 1):
        success, point = evaluator.getPointAtParameter(low * (1 - fraction) + high * fraction)
        if not success or not all(math.isfinite(value) for value in _xyz(point)):
            raise _error("Fusion could not locate a joined finish edge.")
        points.append(point)
    return tuple(points)



# Fusion can create new sharp blend borders that are neither cap-plane edges
# nor cavity mouths. Only the bounded supports of ORIGINAL sharp side edges
# belong to the longitudinal work list. All coordinates here are world cm.
_CURVE_TOLERANCE_CM = 1e-5


def _dot(one, two):
    return sum(a * b for a, b in zip(one, two))


def _cross(one, two):
    return (one[1] * two[2] - one[2] * two[1],
            one[2] * two[0] - one[0] * two[2],
            one[0] * two[1] - one[1] * two[0])


@dataclass(frozen=True)
class _CurveSupport:
    curve: object
    kind: str
    start: tuple
    direction: tuple
    extent: float
    center: tuple = ()
    normal: tuple = ()
    radius: float = 0


def _point_on_support(point, support):
    tolerance = _CURVE_TOLERANCE_CM
    if support.kind == "line":
        delta = tuple(value - origin for value, origin in zip(point, support.start))
        along = _dot(delta, support.direction)
        distance = math.hypot(*(value - along * axis
                                for value, axis in zip(delta, support.direction)))
        return distance <= tolerance and -tolerance <= along <= support.extent + tolerance
    radial = tuple(value - origin for value, origin in zip(point, support.center))
    if (abs(_dot(radial, support.normal)) > tolerance
            or abs(math.hypot(*radial) - support.radius) > tolerance):
        return False
    radial = _unit(radial)
    angle_tolerance = tolerance / support.radius
    if abs(support.extent) >= math.tau - angle_tolerance:
        return True
    angle = math.atan2(_dot(support.normal, _cross(support.direction, radial)),
                       _dot(support.direction, radial))
    # Accept a tiny negative angle at the start before wrapping to [0, 2pi).
    if abs(angle) <= angle_tolerance:
        return True
    progress = (angle if support.extent > 0 else -angle) % math.tau
    return progress <= abs(support.extent) + angle_tolerance


def _freeze_curve_support(edge, core):
    """Snapshot an original trimmed analytic curve without retaining topology.

    Point membership uses analytic distances, never getParameterAtPoint: native
    evaluators may raise and leave an API error for routine off-curve queries.
    Arc trim orientation is reconstructed from five ordered original samples.
    """
    points = tuple(_xyz(point) for point in _samples(edge))
    geometry = edge.geometry
    try:
        curve = geometry.copy()
    except Exception as error:
        raise _error("Fusion could not snapshot an original joined side edge: " + str(error)) from error
    if curve is None:
        raise _error("Fusion could not snapshot an original joined side edge.")
    line_type = getattr(core, "Line3D", None)
    if line_type is not None and line_type.cast(curve) is not None:
        delta = tuple(end - start for start, end in zip(points[0], points[-1]))
        length = math.hypot(*delta)
        if not math.isfinite(length) or length <= _CURVE_TOLERANCE_CM:
            raise _error("An original joined side edge is too short to track safely.")
        support = _CurveSupport(curve, "line", points[0], _unit(delta), length)
    else:
        circular = None
        for name in ("Circle3D", "Arc3D"):
            curve_type = getattr(core, name, None)
            if curve_type is not None:
                circular = curve_type.cast(curve)
                if circular is not None:
                    break
        if circular is None:
            raise _error("An original joined side edge is not a supported line, circle or arc. "
                         "Simplify that edge before finishing.")
        center, normal, radius = _xyz(circular.center), _unit(_xyz(circular.normal)), float(circular.radius)
        if not all(math.isfinite(value) for value in center) or not math.isfinite(radius) or radius <= _CURVE_TOLERANCE_CM:
            raise _error("An original joined side edge has an invalid circular support.")
        radial = tuple(_unit(tuple(value - origin for value, origin in zip(point, center)))
                       for point in points)
        sweep = sum(math.atan2(_dot(normal, _cross(one, two)), _dot(one, two))
                    for one, two in zip(radial, radial[1:]))
        if not _CURVE_TOLERANCE_CM / radius < abs(sweep) <= math.tau + _CURVE_TOLERANCE_CM / radius:
            raise _error("Fusion could not resolve the trimmed span of an original joined side arc.")
        support = _CurveSupport(curve, "circle", points[0], radial[0], sweep, center, normal, radius)
    if not all(_point_on_support(point, support) for point in points):
        raise _error("Fusion returned inconsistent geometry for an original joined side edge.")
    return support


def _edge_on_support(edge, support):
    return all(_point_on_support(_xyz(point), support) for point in _samples(edge))



def classify_edge(edge, body, core, fusion, size_mm):
    """Return convex/concave/tangent using the BRepFace (outward) evaluator."""
    if edge.isDegenerate:
        return "tangent"
    if edge.faces.count == 1:
        # A periodic cylinder seam has one incident face, not a sharp corner.
        if edge.coEdges.count == 2:
            return "tangent"
        raise _error("A finish edge is not a closed manifold edge.")
    if edge.faces.count != 2:
        raise _error("A finish edge is not a closed manifold edge.")
    containment = fusion.PointContainment
    labels = {containment.PointInsidePointContainment: "inside",
              containment.PointOutsidePointContainment: "outside",
              containment.PointOnPointContainment: "on"}

    def contains(coordinates):
        result = body.pointContainment(core.Point3D.create(*coordinates))
        return labels.get(result, "unknown")

    classifications = set()
    for point in _samples(edge)[1:-1]:
        normals = []
        for index in range(2):
            success, normal = edge.faces.item(index).evaluator.getNormalAtPoint(point)
            if not success:
                raise _error("Fusion could not evaluate a joined finish face normal.")
            # Face evaluators already account for isParamReversed.
            normals.append(_xyz(normal))
        try:
            classification = classify_edge_point(_xyz(point), *normals, contains,
                                                 min(2e-5, size_mm / 1000))
        except ValueError as error:
            raise _error(str(error) + " Reduce the finish size or inspect the selected geometry.") from error
        classifications.add(classification)
    if len(classifications) != 1:
        raise _error("A joined finish edge changes curvature. Split or simplify that edge before finishing.")
    return classifications.pop()


def _local_mm(point, frame):
    delta = tuple(value * 10 - origin for value, origin in zip(_xyz(point), frame.origin_mm))
    return tuple(sum(value * axis for value, axis in zip(delta, direction))
                 for direction in (frame.x_axis, frame.y_axis, frame.z_axis))


def _eligible(edge, role, frame, settings, plan, layout):
    if settings.output_mode == "separate" or role.startswith("pin"):
        return True
    samples = tuple(_local_mm(point, frame) for point in _samples(edge))
    tolerance = .0001
    if (max(point[2] for point in samples) <= tolerance
            or min(point[2] for point in samples) < -tolerance):
        return False
    owner = role.split("_", 1)[0]
    radius = settings.barrel_diameter_mm / 2
    far = settings.leaf_reach_mm
    if settings.web_profile == "tangent" and plan is not None:
        for web in plan.webs:
            if web.owner == owner:
                support = plan_tangent_support(web, radius,
                                               knuckle_profile=settings.knuckle_profile, attached=True)
                far = max(far, abs(support.source_intercept_x_mm))
    x_min, x_max = (-far, radius) if owner == "A" else (-radius, far)
    centers = (tuple(placement.center_mm for placement in layout.placements)
               if layout is not None else (0,))
    return any(all(x_min - tolerance <= x <= x_max + tolerance
                   and center - settings.length_mm / 2 - tolerance <= y
                   <= center + settings.length_mm / 2 + tolerance
                   and z <= 2 * radius + tolerance for x, y, z in samples)
               for center in centers)



# Solve cap perimeters on the original plane/cylinder surfaces before side
# blends introduce additional endpoint arcs. Cavity mouths are finished last.
_STAGE_ORDER = ("caps", "longitudinal", "bores")


def _edge_category(edge, role, frame, settings, plan, layout, core):
    """Group actual circular cavity mouths separately from outer cap edges.

    Radius alone is insufficient: a plate corner or housing can have the same
    radius. Require an actual Circle3D, its axis and its planned center/position.
    """
    centers = (tuple(placement.center_mm for placement in layout.placements)
               if layout is not None else (0,))
    circle_type = getattr(core, "Circle3D", None)
    circle = circle_type.cast(edge.geometry) if circle_type is not None else None
    tolerance = .0001
    if circle is not None and not role.startswith("pin"):
        center = _local_mm(circle.center, frame)
        normal = _unit(_xyz(circle.normal))
        radius = float(circle.radius) * 10
        owner = role.split("_", 1)[0]
        axis_y = abs(sum(a*b for a, b in zip(normal, frame.y_axis)))
        axis_z = abs(sum(a*b for a, b in zip(normal, frame.z_axis)))
        bore = (settings.pin_diameter_mm + settings.diametral_clearance_mm) / 2
        housing_center_z = settings.barrel_diameter_mm / 2
        if (axis_y > 1 - 1e-8 and abs(radius - bore) <= tolerance
                and abs(center[0]) <= tolerance
                and abs(center[2] - housing_center_z) <= tolerance
                and any(abs(center[1] - shift - endpoint) <= tolerance
                        for shift in centers for knuckle in plan.knuckles
                        if knuckle.owner == owner
                        for endpoint in (knuckle.start_mm, knuckle.end_mm))):
            return "bores"
        if (settings.output_mode == "separate" and settings.screw_holes
                and axis_z > 1 - 1e-8
                and abs(radius - settings.screw_diameter_mm / 2) <= tolerance
                and any(abs(center[0] - hole.x_mm) <= tolerance
                        and abs(center[1] - shift - hole.y_mm) <= tolerance
                        and min(abs(center[2]), abs(center[2] - settings.leaf_thickness_mm)) <= tolerance
                        for shift in centers for hole in plan.mounting_holes
                        if hole.owner == owner)):
            return "bores"
    y_values = tuple(_local_mm(point, frame)[1] for point in _samples(edge))
    return "caps" if max(y_values) - min(y_values) <= tolerance else "longitudinal"


def _candidate_edges(body, role, frame, settings, plan, layout, core, fusion, size_mm,
                     category_filter=None, cap_plane=None, curve_supports=None):
    edges = []
    for edge in _adapter()._items(body.edges):
        if not _eligible(edge, role, frame, settings, plan, layout):
            continue
        category = _edge_category(edge, role, frame, settings, plan, layout, core)
        if category_filter is not None and category != category_filter:
            continue
        # Filter completed cap planes before probing normals/containment. New
        # miter borders elsewhere may be too close to a blend for that probe.
        if cap_plane is not None and abs(_cap_plane(edge, frame) - cap_plane) > _CAP_PLANE_TOLERANCE_MM:
            continue
        # Reject newly created side/blend borders before probing their nearby
        # normals/containment; those borders are not original finish targets.
        if curve_supports is not None and not any(_edge_on_support(edge, support)
                                                  for support in curve_supports):
            continue
        if classify_edge(edge, body, core, fusion, size_mm) == "convex":
            edges.append((category, edge))
    return tuple(edges)



_CAP_PLANE_TOLERANCE_MM = .0001


def _cap_plane(edge, frame):
    values = tuple(_local_mm(point, frame)[1] for point in _samples(edge))
    low, high = min(values), max(values)
    if high - low > _CAP_PLANE_TOLERANCE_MM:
        raise _error("A cap finish edge does not lie in one end plane.")
    return low + (high - low) / 2


def _cap_groups(edges, frame):
    """Group a frozen set of unfinished cap edges by their local end plane."""
    groups = []
    for plane, edge in sorted(((_cap_plane(edge, frame), edge) for edge in edges),
                              key=lambda pair: pair[0]):
        if not groups or abs(plane - groups[-1][0]) > _CAP_PLANE_TOLERANCE_MM:
            groups.append((plane, [edge]))
        else:
            groups[-1][1].append(edge)
    return tuple((plane, tuple(group)) for plane, group in groups)



def _apply_stage(root, body, edges, role, stage, settings, core, fusion, owned_features):
    is_cap = stage.startswith("caps")
    tangent_chain = False
    # Bounded stage membership is explicit. A rounded plate perimeter may be
    # G1-continuous across cap and side categories; automatic expansion would
    # include unowned stage edges and defeat original-curve ownership.
    chains = (tuple(edges),)
    size_mm = settings.fillet_radius_mm if settings.fillet_edges else settings.chamfer_size_mm
    value = core.ValueInput.createByReal(size_mm / 10)
    if settings.fillet_edges:
        collection = root.features.filletFeatures
        feature_input = collection.createInput()
        if feature_input is None:
            raise _error("Fusion could not define the joined fillet.")
        if is_cap:
            feature_input.isRollingBallCorner = True
    else:
        collection = root.features.chamferFeatures
        feature_input = collection.createInput2()
        if feature_input is None:
            raise _error("Fusion could not define the joined chamfer.")
        if is_cap:
            feature_input.cornerType = fusion.ChamferCornerTypes.MiterCornerType
    for chain in chains:
        collection_input = core.ObjectCollection.create()
        for edge in chain:
            if not collection_input.add(edge):
                raise _error("Fusion could not collect a joined finish edge.")
        if settings.fillet_edges:
            edge_set = feature_input.edgeSetInputs.addConstantRadiusEdgeSet(collection_input, value, tangent_chain)
            if edge_set is None:
                raise _error("Fusion could not define a joined fillet chain.")
        elif not feature_input.chamferEdgeSets.addEqualDistanceChamferEdgeSet(collection_input, value, tangent_chain):
            raise _error("Fusion could not define a joined chamfer chain.")
    label = role + "/" + stage + " (" + str(len(edges)) + " edges)"
    try:
        feature = collection.add(feature_input)
    except Exception as error:
        raise _error("Fusion could not finish joined " + label
                     + " at the requested size. Reduce the finish size. " + str(error)) from error
    if feature is None:
        raise _error("Fusion could not finish joined " + label + " at the requested size.")
    owned_features.append(feature)
    if not feature.isValid or feature.healthState != fusion.FeatureHealthStates.HealthyFeatureHealthState:
        detail = feature.errorOrWarningMessage if feature.isValid else "Invalid native feature."
        raise _error("Fusion could not finish joined " + label + ": " + detail)
    if feature.bodies.count != 1:
        raise _error("The joined finish changed the number of result solids.")
    return _solid(feature.bodies.item(0), temporary=False)


def _solid(body, *, temporary=None):
    if (body is None or not body.isValid or not body.isSolid or body.lumps.count != 1
            or not math.isfinite(body.volume) or body.volume <= 0
            or (temporary is not None and body.isTemporary != temporary)):
        raise _error("Fusion did not return one valid solid for the joined finish.")
    return body


def _counts(design, root):
    return (root.bRepBodies.count, root.features.count, design.timeline.count,
            design.timeline.markerPosition)


def finish_native_results(design, manager, frame, settings, result_bodies, *, plan=None, layout=None):
    """Finish fully joined, raw bored bodies and return detached temporary copies.

    Requires an existing command transaction. No native command orchestration or
    document switching is performed. All modes, profiles and pin roles use the
    same kernel operation. Cleanup failure requires the caller to abort its
    transaction; this helper never removes pre-existing bodies or features.
    """
    adapter = _adapter()
    adapter._require_main_thread()
    settings.validate()
    inputs = tuple(result_bodies.items() if isinstance(result_bodies, dict) else result_bodies)
    if not settings.fillet_edges and not settings.chamfer_edges:
        return inputs
    if not inputs or len({role for role, _ in inputs}) != len(inputs):
        raise _error("Provide unique joined hinge result roles for finishing.")
    for role, body in inputs:
        if not isinstance(role, str) or not (role.startswith("pin") or role.split("_", 1)[0] in {"A", "B"}):
            raise _error("A joined hinge body has an unknown finish role.")
        _solid(body, temporary=True)
    if plan is None:
        from .planner import build_hinge_plan
        plan = build_hinge_plan(settings)
    core, fusion = adapter._api()
    root = design.rootComponent
    before = _counts(design, root)
    if before[2] != before[3]:
        raise _error("Move the history marker to the end before finishing the hinge.")
    original_bodies = adapter._items(root.bRepBodies)
    parametric = design.designType == fusion.DesignTypes.ParametricDesignType
    size_mm = settings.fillet_radius_mm if settings.fillet_edges else settings.chamfer_size_mm
    base = None
    editing = False
    owned_features = []
    owned_bodies = []
    owned_names = []
    cleanup_errors = []
    token = uuid.uuid4().hex
    outputs = []
    try:
        if parametric:
            base = root.features.baseFeatures.add()
            if base is None or not base.isValid:
                raise _error("Fusion could not allocate the temporary finishing feature.")
            if not base.startEdit():
                raise _error("Fusion could not edit the temporary finishing feature.")
            editing = True
        for index, (_, body) in enumerate(inputs):
            copied = root.bRepBodies.add(body, base) if parametric else root.bRepBodies.add(body)
            if copied is not None:
                owned_bodies.append(copied)
            _solid(copied, temporary=False)
            name = "__Partelier_finish_" + token + "_" + str(index)
            copied.name = name
            owned_names.append(name)
        if editing:
            if not base.finishEdit():
                raise _error("Fusion could not close the temporary finishing feature.")
            editing = False
            candidates = adapter._items(base.bodies)
        else:
            candidates = tuple(owned_bodies)
        if len(candidates) != len(inputs):
            raise _error("Fusion changed the number of copied finish bodies.")
        # BaseFeature result order is not an ownership contract. Resolve the
        # unique names assigned only to our own copies after leaving edit mode.
        by_name = {}
        for candidate in candidates:
            name = candidate.name
            if name in by_name:
                raise _error("Fusion returned duplicate temporary finish body names.")
            by_name[name] = candidate
        if set(by_name) != set(owned_names):
            raise _error("Fusion could not identify the owned finish body copies.")
        persisted = tuple(by_name[name] for name in owned_names)
        for (role, raw), body in zip(inputs, persisted):
            initial = _candidate_edges(body, role, frame, settings, plan, layout,
                                       core, fusion, size_mm)
            if not initial:
                raise _error("No convex generated edges were found for " + role + ". Inspect the hinge geometry.")
            initial_categories = {category for category, edge in initial}
            original_side_supports = (() if role.startswith("pin") else tuple(
                _freeze_curve_support(edge, core) for category, edge in initial
                if category == "longitudinal"))
            stages = ("all",) if role.startswith("pin") else _STAGE_ORDER
            for stage in stages:
                current = _candidate_edges(body, role, frame, settings, plan, layout,
                                           core, fusion, size_mm,
                                           None if stage == "all" else stage,
                                           curve_supports=original_side_supports if stage == "longitudinal" else None)
                selected = tuple(edge for category, edge in current
                                 if stage == "all" or category == stage)
                if not selected:
                    # A healthy cap feature may consume a short original side
                    # edge completely. Only surviving original sharp supports
                    # require this stage; new blend borders are never targets.
                    if stage in initial_categories and stage != "longitudinal":
                        raise _error("The earlier finish consumed all " + role + "/" + stage
                                     + " edges. Reduce the finish size; no edge treatment was skipped.")
                    continue
                if stage == "caps":
                    # Freeze only the original cap planes, not BRep references.
                    # New chamfer borders may occupy shifted parallel planes;
                    # they are intentionally absent from this work list.
                    planes = tuple(plane for plane, group in _cap_groups(selected, frame))
                    for plane in planes:
                        refreshed = _candidate_edges(body, role, frame, settings, plan, layout,
                                                     core, fusion, size_mm, "caps", cap_plane=plane)
                        on_plane = tuple(edge for category, edge in refreshed
                                         if abs(_cap_plane(edge, frame) - plane)
                                         <= _CAP_PLANE_TOLERANCE_MM)
                        if not on_plane:
                            raise _error("An earlier cap finish consumed the end plane of " + role
                                         + ". Reduce the finish size; no cap finish was skipped.")
                        body = _apply_stage(root, body, on_plane, role,
                                            "caps@y=" + format(plane, ".9g") + "mm",
                                            settings, core, fusion, owned_features)
                else:
                    body = _apply_stage(root, body, selected, role, stage, settings,
                                        core, fusion, owned_features)
            finished = _solid(manager.copy(body), temporary=True)
            finished = _solid(validate_tangent_roofs(frame, settings, role, raw, finished,
                                                     plan=plan, layout=layout), temporary=True)
            if finished.volume > raw.volume + max(1e-10, raw.volume * 1e-8):
                raise _error("The joined finish added unexpected material. Reduce the finish size.")
            if not finished.volume < raw.volume:
                raise _error("The joined finish did not remove material. Adjust the finish size or inspect the geometry.")
            outputs.append((role, finished))
    finally:
        if editing:
            try:
                if not base.finishEdit():
                    cleanup_errors.append("could not leave the finishing feature")
            except Exception as error:
                cleanup_errors.append(str(error))
        for feature in reversed(owned_features):
            try:
                if feature.isValid and not feature.deleteMe():
                    cleanup_errors.append("could not delete an owned finish feature")
            except Exception as error:
                cleanup_errors.append(str(error))
        if base is not None:
            try:
                if base.isValid and not base.deleteMe():
                    cleanup_errors.append("could not delete the owned finishing feature")
            except Exception as error:
                cleanup_errors.append(str(error))
        elif not parametric:
            for index, body in enumerate(owned_bodies):
                try:
                    if not body.isValid and index < len(owned_names):
                        body = root.bRepBodies.itemByName(owned_names[index])
                    if body is not None and body.isValid and not body.deleteMe():
                        cleanup_errors.append("could not delete an owned finish body")
                except Exception as error:
                    cleanup_errors.append(str(error))
        try:
            if _counts(design, root) != before or any(not body.isValid for body in original_bodies):
                cleanup_errors.append("body or history counts were not restored")
        except Exception as error:
            cleanup_errors.append(str(error))
        if cleanup_errors:
            raise _error("Temporary finishing cleanup failed; abort this command transaction. "
                         + "; ".join(cleanup_errors))
    return tuple(outputs)
