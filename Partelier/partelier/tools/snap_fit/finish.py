"""Bounded equal-setback bevels on the generated clasp and recess entry.

The oriented-box bisector construction follows hinge.finish's box wedges,
extended to an explicit line and two incident normals. It never scans user
edges. Root contact and the negative-X retaining shoulder are excluded.
All right-angle incident faces receive the requested 45-degree chamfer.
"""

from dataclasses import dataclass
import math


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


def _dot(a, b):
    return sum(one * two for one, two in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _unit(values):
    length = math.sqrt(_dot(values, values))
    if not math.isfinite(length) or length <= 0:
        raise ValueError("A chamfer edge or incident face collapsed.")
    return tuple(value / length for value in values)


def bevel_cut(start, end, normal_one, normal_two, size, label):
    """Cut the equal-setback bisector around one bounded generated edge."""
    delta = tuple(b - a for a, b in zip(start, end))
    length = math.sqrt(_dot(delta, delta))
    along = _unit(delta)
    one, two = _unit(normal_one), _unit(normal_two)
    if max(abs(_dot(along, one)), abs(_dot(along, two))) > 1e-8:
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
    return BevelCut(center, along, tangent, normal, length + 2 * size, 4 * size, 4 * size, label)


def plan_detail_chamfers(unit, settings):
    """Only known exposed edges, after all generated primitives are united."""
    if not settings.chamfer_edges:
        return ()
    settings.validate()
    size = settings.chamfer_size_mm
    root = unit.root
    outer = root.x_max_mm
    shoulder = settings.reach_mm - settings.lead_in_mm
    cuts = []
    for side, y in ((-1, root.y_min_mm), (1, root.y_max_mm)):
        cuts.append(bevel_cut((outer, y, root.z_min_mm), (outer, y, 0),
                              (1, 0, 0), (0, side, 0), size, "root outer side"))
        if unit.root_support is not None:
            start_x = 2 * size
            cuts.append(bevel_cut((start_x, y, root.z_min_mm - outer + start_x),
                                  (outer, y, root.z_min_mm), (1, 0, -1),
                                  (0, side, 0), size, "root ramp side"))
    for arm in unit.arms:
        low, high = arm.beam.y_min_mm, arm.beam.y_max_mm
        tip_outer = max(x for x, z in arm.beam.points_xz_mm if z == settings.reach_mm)
        outer_normal = _unit((settings.reach_mm, 0, outer - tip_outer))
        for side, y in ((-1, low), (1, high)):
            cuts.append(bevel_cut((outer, y, 0), (tip_outer, y, settings.reach_mm),
                                  outer_normal, (0, side, 0), size, "beam outer side"))
            cuts.append(bevel_cut((settings.clearance_mm, y, 2 * size),
                                  (settings.clearance_mm, y, shoulder - 2 * size),
                                  (-1, 0, 0), (0, side, 0), size, "beam inner side"))
        cuts.append(bevel_cut((tip_outer, low, settings.reach_mm),
                              (tip_outer, high, settings.reach_mm), outer_normal,
                              (0, 0, 1), size, "free outer tip"))
    if not settings.print_support:
        cuts.append(bevel_cut((outer, root.y_min_mm, root.z_min_mm),
                              (outer, root.y_max_mm, root.z_min_mm),
                              (1, 0, 0), (0, 0, -1), size, "root underside outer edge"))
    return tuple(cuts)


def plan_receiver_chamfers(arm, settings):
    """Bevel the two entrance sides while reserving the flat lower catch lip."""
    if not settings.chamfer_edges:
        return ()
    size = settings.chamfer_size_mm
    bottom = arm.receiver_bounds.z_min_mm + 2 * size
    top = settings.reach_mm + settings.clearance_mm - size
    cuts = []
    for side, y in ((-1, arm.receiver.y_min_mm), (1, arm.receiver.y_max_mm)):
        cuts.append(bevel_cut((0, y, bottom), (0, y, top),
                              (1, 0, 0), (0, -side, 0), size, "receiver entry side"))
    return tuple(cuts)


def apply_chamfers(manager, frame, body, cuts):
    """Subtract bounded analytic cutters; never silently reduce the size."""
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
        message = "Could not apply the requested snap-fit " + cut.label + " chamfer. Reduce its size or turn chamfers off."
        adapter._require_body(cutter, message)
        adapter._boolean(manager, body, cutter, fusion.BooleanTypes.DifferenceBooleanType, message)
        after = float(body.volume)
        if not math.isfinite(after) or not 0 < after < before:
            raise ValueError(message)
    return body
