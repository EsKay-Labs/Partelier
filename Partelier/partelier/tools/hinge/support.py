"""Tangent attachment wedges, planned in mm and built only as temporary solids.

The upper plane runs through the original web's outside top corner and meets
the upper outside of a round or square housing. Attached supports continue
below the source plane; separate supports stay within their finite plate reach.
This is a geometric construction,
not a printer-specific overhang or mechanical-strength guarantee.
"""

from dataclasses import dataclass
import itertools
import math
from numbers import Real
from types import SimpleNamespace


@dataclass(frozen=True)
class TangentSupportPlan:
    """Counterclockwise convex XZ section and extrusion interval, all in mm.

    tangent_xz_mm is the circle tangent for a round housing and the upper
    outside corner for a square housing. source_intercept_x_mm is the upper
    slope's mathematical Z=0 intercept; separate supports stop at their web
    outer edge before that intercept. bottom_intercept_x_mm is the actual
    outermost floor endpoint.
    """

    owner: str
    polygon_xz_mm: tuple
    y_min_mm: float
    y_max_mm: float
    tangent_xz_mm: tuple
    source_intercept_x_mm: float
    bottom_intercept_x_mm: float
    source_overlap_mm: float
    slope_angle_deg: float
    barrel_radius_mm: float
    area_mm2: float
    knuckle_profile: str = "round"
    attached: bool = True


def _finite(*values):
    try:
        valid = all(not isinstance(value, bool) and isinstance(value, Real)
                    and math.isfinite(value) for value in values)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("Tangent support dimensions must be finite numbers in mm.")


def _area(polygon):
    # Translate first to avoid cancellation in polygons far from the origin.
    origin = polygon[0]
    return sum((one[0] - origin[0]) * (two[1] - origin[1])
               - (one[1] - origin[1]) * (two[0] - origin[0])
               for one, two in zip(polygon, polygon[1:] + polygon[:1])) / 2


def plan_tangent_support(web, barrel_radius, *, knuckle_profile="round", attached=True):
    """Plan a mirrored convex gusset from the existing WebBounds contract.

    A occupies negative X; B occupies positive X. Round housings use an exact
    upper circle tangent. Square housings use the upper outside corner of the
    existing inscribed square, with an embedded cap reaching X=0 for positive
    housing overlap. The nominal reach and thickness locate the web's outside
    top corner. Attached floors reach below the source plane. Separate floors
    stay at Z=0 and never extend beyond the web's original outside X limit.
    Invalid bounds or an unsupported profile raise ValueError.
    """
    if type(attached) is not bool or knuckle_profile not in ("round", "square"):
        raise ValueError("Use a round or square housing and an attached true/false flag.")
    try:
        owner = web.owner
        xmin, xmax = web.x_min_mm, web.x_max_mm
        ymin, ymax = web.y_min_mm, web.y_max_mm
        zmin, thickness = web.z_min_mm, web.z_max_mm
    except AttributeError as error:
        raise ValueError("Tangent support needs all six web bounds and an A/B owner.") from error
    _finite(xmin, xmax, ymin, ymax, zmin, thickness, barrel_radius)
    floor_valid = zmin < 0 if attached else zmin == 0
    if (owner not in ("A", "B") or not xmin < xmax or not ymin < ymax
            or not floor_valid or not 0 < thickness < barrel_radius):
        raise ValueError("Tangent support needs valid A/B web bounds, a top below the "
                         "barrel centre and a negative attached floor or a separate floor at Z=0.")
    reach, inner = (-xmin, -xmax) if owner == "A" else (xmax, xmin)
    half_side = barrel_radius / math.sqrt(2)
    housing_width = half_side if knuckle_profile == "square" else barrel_radius
    if not 0 < inner < housing_width < reach or not barrel_radius < reach:
        raise ValueError("Tangent support needs outer reach beyond the housing and "
                         "an inner web end inside it.")
    if knuckle_profile == "square":
        contact_height = barrel_radius - half_side
    else:
        inner_ratio = inner / barrel_radius
        contact_height = barrel_radius * (1 - math.sqrt((1 - inner_ratio) * (1 + inner_ratio)))
    if not thickness > contact_height:
        raise ValueError("The original web must positively overlap the housing. Increase leaf thickness.")

    # Work on A, then reflect. The round calculation avoids squaring a long reach.
    if knuckle_profile == "round":
        distance = math.hypot(reach, barrel_radius - thickness)
        _finite(distance)
        ux, uz = -reach / distance, (thickness - barrel_radius) / distance
        ratio = barrel_radius / distance
        sine = math.sqrt(max(0.0, (1 - ratio) * (1 + ratio)))
        tx = barrel_radius * (ratio * ux + sine * uz)
        tz = barrel_radius * (1 + ratio * uz - sine * ux)
        inner_stop = tx
    else:
        tx, tz = -half_side, barrel_radius + half_side
        inner_stop = 0.0
    _finite(tx, tz)
    if not tx + reach > 0 or not tz - thickness > 0:
        raise ValueError("Tangent support loses a distinct upper transition at this scale.")
    slope = (tz - thickness) / (tx + reach)
    _finite(slope)
    if slope <= 0:
        raise ValueError("Tangent support needs a positive finite slope.")
    source_x = -reach - thickness / slope
    bottom_x = -reach - (thickness - zmin) / slope if attached else -reach
    polygon = ((bottom_x, zmin), (inner_stop, zmin), (inner_stop, tz))
    if knuckle_profile == "square":
        polygon += ((tx, tz),)
    if not attached:
        polygon += ((-reach, thickness),)
    _finite(tx, tz, source_x, bottom_x, ymax - ymin)
    if not (source_x < -reach < tx < 0 and barrel_radius < tz < 2 * barrel_radius
            and (bottom_x < source_x if attached else bottom_x == -reach)):
        raise ValueError("Tangent support dimensions lose a distinct slope or attachment at this scale.")
    if owner == "B":
        polygon = tuple((-x, z) for x, z in reversed(polygon))
        tx, source_x, bottom_x = -tx, -source_x, -bottom_x
    area = _area(polygon)
    _finite(area)
    if area <= 0:
        raise ValueError("Tangent support must have a positive finite cross-section.")
    return TangentSupportPlan(owner, polygon, ymin, ymax, (tx, tz), source_x,
                              bottom_x, -zmin, math.degrees(math.atan(slope)),
                              barrel_radius, area, knuckle_profile, attached)


def _adapter():
    # Keep the planner adsk-independent and permit fusion.py to import us.
    from . import fusion
    return fusion


def _temporary(body, message):
    adapter = _adapter()
    adapter._require_body(body, message)
    if getattr(body, "isTemporary", False) is not True:
        raise adapter.HingeGeometryError("Tangent support may use temporary generated solids only.")
    try:
        volume = float(body.volume)
    except (AttributeError, TypeError, ValueError, OverflowError) as error:
        raise adapter.HingeGeometryError("Tangent support needs a finite, positive temporary solid volume.") from error
    if not math.isfinite(volume) or volume <= 0:
        raise adapter.HingeGeometryError("Tangent support needs a finite, positive temporary solid volume.")
    return body


def _frame(frame):
    try:
        origin = tuple(frame.origin_mm)
        axes = tuple(tuple(axis) for axis in (frame.x_axis, frame.y_axis, frame.z_axis))
        if len(origin) != 3 or any(len(axis) != 3 for axis in axes):
            raise ValueError()
        _finite(*origin, *(value for axis in axes for value in axis))
        adapter = _adapter()
        if (any(abs(adapter._dot(axis, axis) - 1) > 1e-6 for axis in axes)
                or any(abs(adapter._dot(axes[a], axes[b])) > 1e-6
                       for a, b in ((0, 1), (0, 2), (1, 2)))
                or adapter._dot(adapter._cross(axes[0], axes[1]), axes[2]) < 1 - 1e-6):
            raise ValueError()
    except (AttributeError, TypeError, ValueError) as error:
        raise _adapter().HingeGeometryError("Tangent support needs a finite orthonormal hinge frame.") from error


def _bounds(polygon, ymin, ymax):
    return SimpleNamespace(x_min_mm=min(x for x, _ in polygon),
                           x_max_mm=max(x for x, _ in polygon),
                           y_min_mm=ymin, y_max_mm=ymax,
                           z_min_mm=min(z for _, z in polygon),
                           z_max_mm=max(z for _, z in polygon))


def _corners(bounds):
    return tuple(itertools.product((bounds.x_min_mm, bounds.x_max_mm),
                                   (bounds.y_min_mm, bounds.y_max_mm),
                                   (bounds.z_min_mm, bounds.z_max_mm)))


def _side_planes(polygon):
    planes = []
    for one, two in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dz = two[0] - one[0], two[1] - one[1]
        length = math.hypot(dx, dz)
        if not math.isfinite(length) or length <= 0:
            raise ValueError("Tangent support has a collapsed polygon edge.")
        normal = (dz / length, -dx / length)
        planes.append((normal, normal[0] * one[0] + normal[1] * one[1]))
    return tuple(planes)


def _inset_polygon(polygon, radius):
    """Erode a convex polygon by a Euclidean radius, before any host calls."""
    result = polygon
    for normal, constant in _side_planes(polygon):
        constant -= radius
        clipped = []
        for one, two in zip(result, result[1:] + result[:1]):
            first = normal[0] * one[0] + normal[1] * one[1] - constant
            last = normal[0] * two[0] + normal[1] * two[1] - constant
            if first <= 0:
                clipped.append(one)
            if (first < 0 < last) or (last < 0 < first):
                fraction = first / (first - last)
                clipped.append(tuple(a + fraction * (b - a) for a, b in zip(one, two)))
        result = tuple(clipped)
        if len(result) < 3:
            raise ValueError("Edge finish consumes the tapered support. Reduce its size.")
    area = _area(result)
    if not math.isfinite(area) or area <= 0 or len(result) != len(polygon):
        raise ValueError("Edge finish collapses a tapered support face. Reduce its size.")
    for one, two in zip(result, result[1:] + result[:1]):
        if math.hypot(two[0] - one[0], two[1] - one[1]) <= radius * 1e-9:
            raise ValueError("Edge finish leaves an indistinct tapered support edge. Reduce its size.")
    return result


def _clip(manager, frame, target, normal, constant, bounds):
    """Intersect a temporary solid with n.point <= constant using one box cut.

    The cutter's inside face is the exact clipping plane. Its other five faces
    extend beyond the original bounds, so this uses only documented oriented
    boxes and boolean differences, without a persistent sketch or extrusion.
    """
    adapter = _adapter()
    core, fusion = adapter._api()
    corners = _corners(bounds)
    projections = [adapter._dot(normal, point) for point in corners]
    outside = max(projections) - constant
    if outside <= 0:
        return target
    spans = (bounds.x_max_mm - bounds.x_min_mm, bounds.y_max_mm - bounds.y_min_mm,
             bounds.z_max_mm - bounds.z_min_mm)
    margin = max(min(spans) * .01, max(spans) * 1e-9)
    seed = min(((1, 0, 0), (0, 1, 0), (0, 0, 1)), key=lambda axis: abs(adapter._dot(axis, normal)))
    first = adapter._cross(seed, normal)
    length = math.sqrt(adapter._dot(first, first))
    first = tuple(value / length for value in first)
    second = adapter._cross(normal, first)
    ranges = tuple((min(adapter._dot(axis, point) for point in corners),
                    max(adapter._dot(axis, point) for point in corners))
                   for axis in (first, second))
    depth = outside + margin
    coordinates = tuple(low / 2 + high / 2 for low, high in ranges) + (constant + depth / 2,)
    center = tuple(sum(value * axis[index] for value, axis in zip(coordinates, (first, second, normal)))
                   for index in range(3))
    dimensions = tuple(high - low + 2 * margin for low, high in ranges) + (depth,)
    _finite(*center, *dimensions)
    if any(value <= 0 for value in dimensions):
        raise adapter.HingeGeometryError("Tangent support cutter collapsed. Adjust dimensions.")
    world_center = frame.point_mm(*center)
    _finite(*world_center)
    oriented = core.OrientedBoundingBox3D.create(
        adapter._point(frame, *center),
        core.Vector3D.create(*adapter._world_direction(frame, first)),
        core.Vector3D.create(*adapter._world_direction(frame, second)),
        *(value / 10 for value in dimensions))
    if oriented is None:
        raise adapter.HingeGeometryError("Could not orient a tapered support clipping tool.")
    cutter = _temporary(manager.createBox(oriented), "Could not create a tapered support clipping tool.")
    adapter._boolean(manager, target, cutter, fusion.BooleanTypes.DifferenceBooleanType,
                     "The tapered support clipping failed. Reduce edge finish or adjust dimensions.")
    return _temporary(target, "The tapered support must remain one temporary solid.")


def _prism(manager, frame, polygon, ymin, ymax):
    adapter = _adapter()
    bounds = _bounds(polygon, ymin, ymax)
    spans = (bounds.x_max_mm - bounds.x_min_mm, ymax - ymin,
             bounds.z_max_mm - bounds.z_min_mm)
    # Preflight the exact midpoint arithmetic used by the shared box adapter.
    # Finite corners can still have a nonfinite min+max sum at extreme scales.
    midpoints = ((bounds.x_min_mm + bounds.x_max_mm) / 2,
                 (bounds.y_min_mm + bounds.y_max_mm) / 2,
                 (bounds.z_min_mm + bounds.z_max_mm) / 2)
    _finite(*spans, *midpoints,
            *(value for point in _corners(bounds) for value in frame.point_mm(*point)))
    if any(span <= 0 for span in spans):
        raise adapter.HingeGeometryError("Tangent support prism has collapsed bounds.")
    body = _temporary(adapter._box(manager, frame, bounds), "Could not create a tapered support blank.")
    for (nx, nz), constant in _side_planes(polygon):
        _clip(manager, frame, body, (nx, 0, nz), constant, bounds)
    return body


def _join(manager, target, tool):
    adapter = _adapter()
    _, fusion = adapter._api()
    adapter._boolean(manager, target, tool, fusion.BooleanTypes.UnionBooleanType,
                     "The tapered support finish did not join into one solid. Reduce its size.")
    return _temporary(target, "The tapered support finish must remain one temporary solid.")


def _rounded_prism(manager, frame, ymin, ymax, radius, inner):
    """Exact Minkowski sum of an inset convex prism with a radius sphere.

    Face slabs, edge cylinders and vertex spheres cover the closest-point
    regions of the inset prism. Corners are spherical, not planar bevels.
    """
    adapter = _adapter()
    ylow, yhigh = ymin + radius, ymax - radius
    target = _prism(manager, frame, inner, ymin, ymax)
    for (one, two), (normal, _) in zip(zip(inner, inner[1:] + inner[:1]), _side_planes(inner)):
        # Include the inward half as well to positively overlap the prism.
        slab = tuple((point[0] + direction * radius * normal[0],
                      point[1] + direction * radius * normal[1])
                     for point, direction in ((one, -1), (two, -1), (two, 1), (one, 1)))
        if _area(slab) < 0:
            slab = tuple(reversed(slab))
        _join(manager, target, _prism(manager, frame, slab, ylow, yhigh))
    def cylinder(start, end):
        return _temporary(manager.createCylinderOrCone(
            adapter._point(frame, *start), radius / 10,
            adapter._point(frame, *end), radius / 10), "Could not create a tapered support round edge.")
    for one, two in zip(inner, inner[1:] + inner[:1]):
        for y in (ylow, yhigh):
            _join(manager, target, cylinder((one[0], y, one[1]), (two[0], y, two[1])))
        _join(manager, target, cylinder((one[0], ylow, one[1]), (one[0], yhigh, one[1])))
        for y in (ylow, yhigh):
            sphere = _temporary(manager.createSphere(adapter._point(frame, one[0], y, one[1]), radius / 10),
                                "Could not create a spherical tapered support corner.")
            _join(manager, target, sphere)
    return target


def _chamfer_prism(manager, frame, polygon, ymin, ymax, size):
    adapter = _adapter()
    body = _prism(manager, frame, polygon, ymin, ymax)
    before = float(body.volume)
    sides = tuple(((nx, 0, nz), constant) for (nx, nz), constant in _side_planes(polygon))
    pairs = list(zip(sides, sides[1:] + sides[:1]))
    for side in sides:
        pairs.extend(((side, ((0, -1, 0), -ymin)), (side, ((0, 1, 0), ymax))))
    bounds = _bounds(polygon, ymin, ymax)
    for (one, c_one), (two, c_two) in pairs:
        # The bisector meets each incident face at the same along-face
        # distance `size` from their original edge, for every dihedral angle.
        cosine = max(-1.0, min(1.0, adapter._dot(one, two)))
        sine = math.sqrt(max(0.0, (1 - cosine) * (1 + cosine)))
        normal = tuple(a + b for a, b in zip(one, two))
        length = math.sqrt(adapter._dot(normal, normal))
        normal = tuple(value / length for value in normal)
        constant = (c_one + c_two - size * sine) / length
        _clip(manager, frame, body, normal, constant, bounds)
    after = float(body.volume)
    if not math.isfinite(before) or not math.isfinite(after) or not 0 < after < before:
        raise adapter.HingeGeometryError("The tapered support chamfer did not remove positive material.")
    return body


def make_tangent_support(manager, frame, web, settings):
    """Build one transient support for any available housing/output mode.

    Requested fillets round the convex support primitive. They do not add a
    concave blend after its later union with a barrel, source body or plate.
    Separate support material can rise above the plate inward of its outer
    web edge; screw bores that cross this region must cut the whole support.
    """
    adapter = _adapter()
    adapter._require_main_thread()
    _frame(frame)
    try:
        settings.validate()
        if settings.web_profile != "tangent":
            raise ValueError("Choose the tangent web profile for tapered supports.")
        plan = plan_tangent_support(web, settings.barrel_diameter_mm / 2,
                                    knuckle_profile=settings.knuckle_profile,
                                    attached=settings.output_mode == "attached")
        rounded, chamfered = settings.fillet_edges, settings.chamfer_edges
        size = settings.fillet_radius_mm if rounded else settings.chamfer_size_mm
        if rounded or chamfered:
            _finite(size)
            if not 0 < size < (plan.y_max_mm - plan.y_min_mm) / 2:
                raise ValueError("Edge finish must be positive and smaller than half the support length.")
            inner = _inset_polygon(plan.polygon_xz_mm, size)
        if rounded:
            return _rounded_prism(manager, frame, plan.y_min_mm, plan.y_max_mm, size, inner)
        if chamfered:
            return _chamfer_prism(manager, frame, plan.polygon_xz_mm,
                                  plan.y_min_mm, plan.y_max_mm, size)
        return _prism(manager, frame, plan.polygon_xz_mm, plan.y_min_mm, plan.y_max_mm)
    except (ValueError, AttributeError, TypeError, ZeroDivisionError, OverflowError) as error:
        if isinstance(error, adapter.HingeGeometryError):
            raise
        raise adapter.HingeGeometryError(str(error)) from error
