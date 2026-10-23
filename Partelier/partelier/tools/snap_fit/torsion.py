"""Exterior torsion-bar latch: two fixed posts, a round bar and one lever.

The Y-axis bar is suspended above the fixed root, with its ends embedded in
posts. The central lever joins the bar, without an additional root connection.
All plans are in local millimetres; native geometry is detached temporary BRep.
No material-specific torsion, stress, printability or durability is established.
"""

from dataclasses import dataclass, replace
import math

from .planner import BoxBounds, HookPrism, SnapArm, SnapFitUnit


@dataclass(frozen=True)
class TorsionGeometry:
    radius_mm: float
    axis_x_mm: float
    axis_z_mm: float
    start_y_mm: float
    end_y_mm: float
    posts: tuple[BoxBounds, ...]
    lever_width_mm: float


@dataclass(frozen=True)
class TorsionUnit(SnapFitUnit):
    torsion_geometry: object = None


def _positive(name, value):
    try:
        valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                 and math.isfinite(value) and value > 0)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(name + " must be a positive finite number in mm.")
    return float(value)


def adapt_unit(unit, settings):
    """Replace the straight hook tab with one bar-supported central lever."""
    if not isinstance(unit, SnapFitUnit) or not unit.arms:
        raise ValueError("Torsion geometry needs a complete snap-fit unit plan.")
    radius = _positive("Torsion radius", settings.torsion_radius_mm)
    width = _positive("Width", settings.width_mm)
    thickness = _positive("Thickness", settings.thickness_mm)
    clearance = _positive("Clearance", settings.clearance_mm)
    root_length = _positive("Root length", settings.root_length_mm)
    reach = _positive("Reach", settings.reach_mm)
    lead_in = _positive("Lead in", settings.lead_in_mm)
    hook_depth = _positive("Hook depth", settings.hook_depth_mm)
    post_width = max(2 * radius, thickness)
    lever_width = width / 3
    axis = clearance + radius
    shoulder = reach - lead_in
    if not all(math.isfinite(value) for value in (post_width, axis, axis + radius,
                                                  width - 2 * post_width - 2 * clearance)):
        raise ValueError("Torsion dimensions must produce finite post, bar and lever envelopes.")
    if not 0 < lever_width < width - 2 * post_width - 2 * clearance:
        raise ValueError("Increase width or reduce torsion radius/thickness to leave clearance between the lever and both posts.")
    if not shoulder > axis + radius + clearance:
        raise ValueError("Increase reach or reduce lead in/radius so the retaining shoulder stays above the torsion bar.")
    if settings.chamfer_edges and not settings.chamfer_size_mm < min(lever_width, thickness) / 2:
        raise ValueError("Chamfer size must stay below half the central torsion lever width and thickness.")
    center = unit.center_y_mm
    half = width / 2
    post_low = BoxBounds(clearance, clearance + max(2 * radius, thickness),
                         center - half, center - half + post_width,
                         -root_length / 2, axis + radius)
    post_high = replace(post_low, y_min_mm=center + half - post_width,
                         y_max_mm=center + half)
    start_y = (post_low.y_min_mm + post_low.y_max_mm) / 2
    end_y = (post_high.y_min_mm + post_high.y_max_mm) / 2
    geometry = TorsionGeometry(radius, axis, axis, start_y, end_y,
                                (post_low, post_high), lever_width)
    lever_low, lever_high = center - lever_width / 2, center + lever_width / 2
    outer = clearance + thickness
    beam = HookPrism(((clearance, axis), (outer, axis),
                       (outer, reach), (clearance, reach)), lever_low, lever_high)
    hook = HookPrism(((-hook_depth, shoulder), (outer, shoulder),
                       (outer, reach), (clearance, reach)), lever_low, lever_high)
    original = unit.arms[0]
    receiver = replace(original.receiver, y_min_mm=lever_low - clearance,
                        y_max_mm=lever_high + clearance)
    bounds = replace(original.receiver_bounds, y_min_mm=receiver.y_min_mm,
                      y_max_mm=receiver.y_max_mm)
    margin = max(clearance, settings.chamfer_size_mm if settings.chamfer_edges else 0)
    cover = replace(original.receiver_cover, y_min_mm=receiver.y_min_mm - margin,
                     y_max_mm=receiver.y_max_mm + margin)
    arm = SnapArm(beam, hook, receiver, bounds, cover)
    envelope = BoxBounds(clearance, outer, lever_low, lever_high, axis, reach)
    receiver_alias = replace(unit.receiver, y_min_mm=receiver.y_min_mm,
                             y_max_mm=receiver.y_max_mm)
    # Match the fixed root to the full post/bar depth. A post protruding a
    # fraction beyond its root would introduce a spurious step and bevel band.
    mount_outer = max(unit.root.x_max_mm, clearance + 2 * radius)
    root = replace(unit.root, x_max_mm=mount_outer)
    root_support = unit.root_support
    root_cover = unit.root_cover
    if root_support is not None:
        bottom = -root_length - mount_outer - settings.attachment_overlap_mm
        root_support = HookPrism(((-settings.attachment_overlap_mm, bottom),
                                   (mount_outer, -root_length),
                                   (-settings.attachment_overlap_mm,
                                    -root_length+settings.attachment_overlap_mm)),
                                  root.y_min_mm, root.y_max_mm)
        root_cover = replace(root_cover, z_min_mm=bottom)
    return TorsionUnit(unit.center_y_mm, root, envelope, hook, receiver_alias,
                       (arm,), root_support, root_cover, geometry)


def add_torsion_bodies(manager, frame, unit, settings):
    """Return posts first, then bar, so every sequential root union connects."""
    if not isinstance(unit, TorsionUnit) or not isinstance(unit.torsion_geometry, TorsionGeometry):
        raise ValueError("Build the torsion unit plan before making its temporary solids.")
    from ..hinge import fusion as adapter
    geometry = unit.torsion_geometry
    posts = tuple(adapter._box(manager, frame, bounds) for bounds in geometry.posts)
    return posts + (bar_body(manager, frame, unit),)


def bar_body(manager, frame, unit):
    """Make the exact round core, also used to protect it during finishing."""
    from ..hinge import fusion as adapter
    geometry = unit.torsion_geometry
    bar = manager.createCylinderOrCone(
        adapter._point(frame, geometry.axis_x_mm, geometry.start_y_mm, geometry.axis_z_mm),
        geometry.radius_mm / 10,
        adapter._point(frame, geometry.axis_x_mm, geometry.end_y_mm, geometry.axis_z_mm),
        geometry.radius_mm / 10)
    adapter._require_body(bar, "Fusion could not construct the temporary torsion bar.")
    return bar
