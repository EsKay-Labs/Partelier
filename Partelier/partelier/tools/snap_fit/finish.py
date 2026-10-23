"""Bevel complete exterior convex edges of the joined generated clasp only.

Edge candidates come from the actual raw BRep after root/arms/ramps are united.
No inner beam, wall contact, retaining shoulder, or receiver edge is finished.
The bounded bisector cutter follows hinge.finish's equal-setback construction;
its along-edge interval is the actual complete trimmed edge, without extension.
"""

from dataclasses import dataclass, replace
from itertools import product
import math
from types import SimpleNamespace


TOLERANCE_MM = .0001
ANGLE_TOLERANCE = .000001


@dataclass(frozen=True)
class EdgePath:
    start_mm: tuple
    end_mm: tuple
    normal_one: tuple
    normal_two: tuple
    label: str
    source_edge_count: int = 1


@dataclass(frozen=True)
class BevelCut:
    center_mm: tuple
    edge_axis: tuple
    tangent_axis: tuple
    normal_axis: tuple
    length_mm: float
    width_mm: float
    depth_mm: float
    label: str
    start_mm: tuple
    end_mm: tuple
    normal_one: tuple
    normal_two: tuple
    source_edge_count: int = 1

    def diagnostic(self):
        return {"label": self.label, "start_mm": self.start_mm, "end_mm": self.end_mm,
                "normal_one": self.normal_one, "normal_two": self.normal_two,
                "source_edge_count": self.source_edge_count, "length_mm": self.length_mm}


def _dot(a, b):
    return sum(one * two for one, two in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _subtract(a, b):
    return tuple(one - two for one, two in zip(a, b))


def _unit(values):
    length = math.sqrt(_dot(values, values))
    if not math.isfinite(length) or length <= 0:
        raise ValueError("A chamfer edge or incident face collapsed.")
    return tuple(value / length for value in values)


def bevel_cut(start, end, normal_one, normal_two, size, label, source_edge_count=1):
    """Equal setback on two incident faces, over the exact bounded edge."""
    delta = _subtract(end, start)
    length = math.sqrt(_dot(delta, delta))
    along = _unit(delta)
    one, two = _unit(normal_one), _unit(normal_two)
    if max(abs(_dot(along, one)), abs(_dot(along, two))) > 1e-7:
        raise ValueError("Chamfer face normals must be perpendicular to the bounded edge.")
    summed = tuple(a + b for a, b in zip(one, two))
    norm_length = math.sqrt(_dot(summed, summed))
    normal = _unit(summed)
    cosine = max(-1.0, min(1.0, _dot(one, two)))
    sine = math.sqrt(max(0.0, (1 - cosine) * (1 + cosine)))
    tangent = _cross(normal, along)
    offset = 2 * size - size * sine / norm_length
    center = tuple(a / 2 + b / 2 + n * offset for a, b, n in zip(start, end, normal))
    if not all(math.isfinite(value) for value in center + (length, size)) or size <= 0:
        raise ValueError("Chamfer cutter dimensions must stay finite and positive.")
    return BevelCut(center, along, tangent, normal, length, 4 * size, 4 * size, label,
                    tuple(start), tuple(end), one, two, source_edge_count)


def _local_point(frame, world_cm):
    delta = tuple(value * 10 - origin for value, origin in zip(world_cm, frame.origin_mm))
    return tuple(_dot(delta, axis) for axis in (frame.x_axis, frame.y_axis, frame.z_axis))


def _local_normal(frame, world):
    return _unit(tuple(_dot(world, axis) for axis in (frame.x_axis, frame.y_axis, frame.z_axis)))


def _outside_segment(start, end):
    """Trim only the wall-embedded portion, retaining the complete outer path."""
    if max(start[0], end[0]) <= TOLERANCE_MM:
        return None
    if min(start[0], end[0]) < 0:
        fraction = -start[0] / (end[0] - start[0])
        crossing = tuple(a + fraction * (b - a) for a, b in zip(start, end))
        crossing = (0.0, crossing[1], crossing[2])
        if start[0] < 0:
            start = crossing
        else:
            end = crossing
    return tuple(start), tuple(end)


def _eligible(path, settings, y_bounds=None):
    start, end, one, two = path.start_mm, path.end_mm, path.normal_one, path.normal_two
    # A side facing the space between arms/posts is inside the mechanism.
    if y_bounds is not None:
        for normal in (one, two):
            if abs(normal[1]) > 1 - ANGLE_TOLERANCE:
                exterior = y_bounds[1] if normal[1] > 0 else y_bounds[0]
                if max(abs(start[1]-exterior), abs(end[1]-exterior)) > TOLERANCE_MM:
                    return False
    # Any negative-X incident face belongs to an inward/contact-facing surface.
    if one[0] < -ANGLE_TOLERANCE or two[0] < -ANGLE_TOLERANCE:
        return False
    shoulder = settings.reach_mm - settings.lead_in_mm
    if (abs(start[2] - shoulder) <= TOLERANCE_MM
            and abs(end[2] - shoulder) <= TOLERANCE_MM
            and min(start[0], end[0]) <= settings.clearance_mm + TOLERANCE_MM):
        return False
    if max(one[0], two[0]) > ANGLE_TOLERANCE:
        return True
    # Side/top or side/bottom edges of the free outside region. Embedded root
    # edges and the lower catch profile cannot enter through this branch.
    side_top = ((abs(one[1]) > 1 - ANGLE_TOLERANCE and abs(two[2]) > 1 - ANGLE_TOLERANCE)
                or (abs(two[1]) > 1 - ANGLE_TOLERANCE and abs(one[2]) > 1 - ANGLE_TOLERANCE))
    return side_top and min(start[0], end[0]) >= settings.clearance_mm - TOLERANCE_MM


def _convex(body, frame, path, size):
    from ..hinge import fusion as adapter
    _, fusion = adapter._api()
    outside = fusion.PointContainment.PointOutsidePointContainment
    inside = fusion.PointContainment.PointInsidePointContainment
    one, two = path.normal_one, path.normal_two
    difference = _unit(_subtract(one, two))
    bisector = _unit(tuple(a + b for a, b in zip(one, two)))
    midpoint = tuple(a / 2 + b / 2 for a, b in zip(path.start_mm, path.end_mm))
    length = math.sqrt(_dot(_subtract(path.end_mm, path.start_mm), _subtract(path.end_mm, path.start_mm)))
    epsilon = min(size * .05, length * .01)
    if epsilon <= TOLERANCE_MM / 10:
        raise ValueError("An exterior edge is too short to prove its convexity at the requested chamfer size.")
    def classify(direction, sign):
        point = tuple(value + sign * epsilon * normal for value, normal in zip(midpoint, direction))
        return body.pointContainment(adapter._point(frame, *point))
    sides = (classify(difference, 1), classify(difference, -1))
    if sides == (inside, inside):
        return False
    if sides != (outside, outside) or classify(bisector, -1) != inside or classify(bisector, 1) != outside:
        raise ValueError("Fusion could not prove whether an exterior edge is convex. No chamfer was applied.")
    return True


def _same_normals(a, b):
    return ((_dot(a.normal_one, b.normal_one) > 1 - ANGLE_TOLERANCE
             and _dot(a.normal_two, b.normal_two) > 1 - ANGLE_TOLERANCE)
            or (_dot(a.normal_one, b.normal_two) > 1 - ANGLE_TOLERANCE
                and _dot(a.normal_two, b.normal_one) > 1 - ANGLE_TOLERANCE))


def _merge_paths(paths):
    """Merge continuous collinear edges with the same two outward planes."""
    merged = list(paths)
    changed = True
    while changed:
        changed = False
        for index, a in enumerate(merged):
            direction = _unit(_subtract(a.end_mm, a.start_mm))
            length = math.sqrt(_dot(_subtract(a.end_mm, a.start_mm), _subtract(a.end_mm, a.start_mm)))
            for other_index in range(index + 1, len(merged)):
                b = merged[other_index]
                if not _same_normals(a, b):
                    continue
                b_direction = _unit(_subtract(b.end_mm, b.start_mm))
                if abs(_dot(direction, b_direction)) < 1 - ANGLE_TOLERANCE:
                    continue
                offsets = tuple(_subtract(point, a.start_mm) for point in (b.start_mm, b.end_mm))
                if any(math.sqrt(_dot(_cross(offset, direction), _cross(offset, direction))) > TOLERANCE_MM
                       for offset in offsets):
                    continue
                positions = sorted(_dot(offset, direction) for offset in offsets)
                if positions[0] > length + TOLERANCE_MM or positions[1] < -TOLERANCE_MM:
                    continue
                low, high = min(0.0, positions[0]), max(length, positions[1])
                start = tuple(value + low * axis for value, axis in zip(a.start_mm, direction))
                end = tuple(value + high * axis for value, axis in zip(a.start_mm, direction))
                merged[index] = replace(a, start_mm=start, end_mm=end,
                                        source_edge_count=a.source_edge_count + b.source_edge_count)
                del merged[other_index]
                changed = True
                break
            if changed:
                break
    return tuple(merged)


def plan_detail_chamfers(body, frame, settings):
    """Classify the complete edges of the actual joined generated detail."""
    if not settings.chamfer_edges:
        return ()
    settings.validate()
    from ..hinge import fusion as adapter
    paths = []
    edges = adapter._items(body.edges)
    local_y = [point[1] for edge in edges for point in (
        tuple(_local_point(frame, value) for value in adapter._straight_endpoints(edge))
        if adapter._straight_endpoints(edge) is not None else ())]
    y_bounds = (min(local_y), max(local_y)) if local_y else None
    core, _ = adapter._api()
    for edge in edges:
        if edge.isDegenerate or edge.faces.count != 2:
            continue
        endpoints = adapter._straight_endpoints(edge)
        if endpoints is None:
            continue  # Curved detents and torsion bars keep their functional profile.
        faces = adapter._items(edge.faces)
        if any(core.Plane.cast(face.geometry) is None for face in faces):
            continue
        one, two = tuple(_local_normal(frame, adapter._plane_normal(face)) for face in faces)
        cosine = _dot(one, two)
        if cosine > 1 - ANGLE_TOLERANCE:
            continue
        if cosine < -1 + ANGLE_TOLERANCE:
            raise ValueError("The generated clasp has an ambiguous pair of incident faces.")
        segment = _outside_segment(*tuple(_local_point(frame, point) for point in endpoints))
        if segment is None:
            continue
        path = EdgePath(*segment, one, two, "exterior convex edge")
        if not _eligible(path, settings, y_bounds) or not _convex(body, frame, path, settings.chamfer_size_mm):
            continue
        paths.append(path)
    paths = _merge_paths(paths)
    if not paths:
        raise ValueError("No supported exterior convex edges were found on the joined clasp.")
    return tuple(bevel_cut(path.start_mm, path.end_mm, path.normal_one, path.normal_two,
                           settings.chamfer_size_mm, "exterior edge " + str(index + 1), path.source_edge_count)
                 for index, path in enumerate(paths))


def plan_receiver_chamfers(arm, settings):
    """The receiving recess and its contact surfaces remain exactly sharp."""
    return ()


def _clip_outside_wall(manager, frame, cutter, cut):
    from ..hinge import fusion as adapter
    _, fusion = adapter._api()
    axes = (cut.edge_axis, cut.tangent_axis, cut.normal_axis)
    halves = (cut.length_mm / 2, cut.width_mm / 2, cut.depth_mm / 2)
    corners = tuple(tuple(cut.center_mm[index] + sum(sign * half * axis[index]
                                                    for sign, half, axis in zip(signs, halves, axes))
                          for index in range(3)) for signs in product((-1, 1), repeat=3))
    minima = tuple(min(point[index] for point in corners) for index in range(3))
    maxima = tuple(max(point[index] for point in corners) for index in range(3))
    if maxima[0] <= 0:
        raise ValueError("An exterior chamfer cutter has no outside-wall region.")
    if minima[0] >= 0:
        return cutter
    margin = max(cut.width_mm, cut.depth_mm) / 4
    bounds = SimpleNamespace(x_min_mm=0.0, x_max_mm=maxima[0] + margin,
                             y_min_mm=minima[1] - margin, y_max_mm=maxima[1] + margin,
                             z_min_mm=minima[2] - margin, z_max_mm=maxima[2] + margin)
    outside = adapter._box(manager, frame, bounds)
    adapter._boolean(manager, cutter, outside, fusion.BooleanTypes.IntersectionBooleanType,
                     "Fusion could not restrict a chamfer to the exterior of the wall.")
    return cutter


def apply_chamfers(manager, frame, body, cuts):
    """Subtract the exterior-only cutters; never silently reduce the size."""
    if not cuts:
        return body
    from ..hinge import fusion as adapter
    core, fusion = adapter._api()
    for cut in cuts:
        before = float(body.volume)
        bounds = core.OrientedBoundingBox3D.create(
            adapter._point(frame, *cut.center_mm),
            core.Vector3D.create(*adapter._world_direction(frame, cut.edge_axis)),
            core.Vector3D.create(*adapter._world_direction(frame, cut.tangent_axis)),
            cut.length_mm / 10, cut.width_mm / 10, cut.depth_mm / 10)
        cutter = manager.createBox(bounds)
        message = "Could not apply the complete snap-fit " + cut.label + " chamfer. Reduce its size or turn chamfers off."
        adapter._require_body(cutter, message)
        cutter = _clip_outside_wall(manager, frame, cutter, cut)
        adapter._boolean(manager, body, cutter, fusion.BooleanTypes.DifferenceBooleanType, message)
        after = float(body.volume)
        if not math.isfinite(after) or not 0 < after < before:
            raise ValueError(message)
    return body
