"""Pure plan for exterior cantilever clasps across one straight lid seam.

Local X points out of the two coplanar wall faces, Y follows the selected rim,
and Z points from A toward B with X cross Y = Z. The rim midpoint is the origin.
A lies below Z=0; B must contain the receiving-pocket region above that seam.
The Fusion adapter verifies those attachment regions on the actual solids.

The tab is outside X=0, rooted into A below the seam. The free-end hook points
into B. The receiving recess is bounded, rather than a through-all body cut.
No source geometry, coordinate frame, or host object is mutated here.
"""

from dataclasses import dataclass
import math

from .settings import SnapFitSettings, _length


@dataclass(frozen=True)
class BoxBounds:
    x_min_mm: float
    x_max_mm: float
    y_min_mm: float
    y_max_mm: float
    z_min_mm: float
    z_max_mm: float


@dataclass(frozen=True)
class HookPrism:
    """Convex X/Z polygon extruded from y_min_mm to y_max_mm."""

    points_xz_mm: tuple[tuple[float, float], ...]
    y_min_mm: float
    y_max_mm: float


@dataclass(frozen=True)
class SnapArm:
    beam: HookPrism
    hook: HookPrism
    receiver: HookPrism
    receiver_bounds: BoxBounds
    receiver_cover: BoxBounds


@dataclass(frozen=True)
class SnapFitUnit:
    center_y_mm: float
    root: BoxBounds
    beam: BoxBounds
    hook: HookPrism
    receiver: BoxBounds
    arms: tuple[SnapArm, ...] = ()
    root_support: object = None
    root_cover: object = None


@dataclass(frozen=True)
class SnapFitPlan:
    settings: SnapFitSettings
    span_mm: float
    units: tuple[SnapFitUnit, ...]


def build_snap_fit_plan(settings, span_mm):
    """Space receiving envelopes equally within explicit end margins.

    Margins are measured from the selected rim's ends to the outside of each
    receiving recess. A single clasp is centered in that remaining interval;
    multiple clasps use its two extreme centers and equal center spacing.
    Receiver envelopes must have a positive gap, so neighboring cuts do not
    silently coalesce. The adapter may impose further source-solid checks.
    """
    if not isinstance(settings, SnapFitSettings):
        raise ValueError("Build the snap-fit plan from SnapFitSettings.")
    settings.validate()
    span = _length("span_mm", span_mm)
    half_span = span / 2.0
    half_width = settings.width_mm / 2.0
    # Receiver contact surfaces are never chamfered.
    pocket_half_width = max(half_width, settings.ball_radius_mm if settings.snap_family == "ball_detent" else 0) + settings.clearance_mm
    first = -half_span + settings.start_margin_mm + pocket_half_width
    last = half_span - settings.end_margin_mm - pocket_half_width
    if not all(math.isfinite(value) for value in (first, last)) or last < first:
        raise ValueError("Selected rim is too short for the snap width, clearance and end margins.")
    if settings.snap_count == 1:
        centers = (first / 2.0 + last / 2.0,)
    else:
        # Division before addition avoids overflowing the full usable span.
        step = last / (settings.snap_count - 1) - first / (settings.snap_count - 1)
        if not math.isfinite(step) or not step > 2.0 * pocket_half_width:
            raise ValueError("Snap count, width and clearance must leave a positive gap between receiving recesses.")
        centers = tuple(first + index * step if index < settings.snap_count - 1 else last
                        for index in range(settings.snap_count))
    outer_x = settings.clearance_mm + settings.thickness_mm
    shoulder_z = settings.reach_mm - settings.lead_in_mm
    units = []
    previous_receiver_end = None
    for center in centers:
        low_y, high_y = center - half_width, center + half_width
        pocket_low_y, pocket_high_y = center - pocket_half_width, center + pocket_half_width
        if (not all(math.isfinite(value) for value in (center, low_y, high_y,
                                                     pocket_low_y, pocket_high_y))
                or not pocket_low_y < low_y < high_y < pocket_high_y
                or (previous_receiver_end is not None and not pocket_low_y > previous_receiver_end)):
            raise ValueError("Placement and clearance must produce distinct finite snap-fit intervals.")
        root = BoxBounds(-settings.attachment_overlap_mm, outer_x,
                         low_y, high_y, -settings.root_length_mm, 0.0)
        beam = BoxBounds(settings.clearance_mm, outer_x,
                         low_y, high_y, -settings.root_length_mm, settings.reach_mm)
        gap = max(settings.thickness_mm, 4 * settings.clearance_mm + .2)
        intervals = (((low_y, center - gap / 2), (center + gap / 2, high_y))
                     if settings.snap_style == "twin" else ((low_y, high_y),))
        tip_outer = settings.clearance_mm + settings.thickness_mm * (.65 if settings.snap_style == "tapered" else 1)
        shoulder_outer = outer_x + (tip_outer - outer_x) * shoulder_z / settings.reach_mm
        depth = settings.hook_depth_mm + settings.clearance_mm
        flat_top = settings.reach_mm + settings.clearance_mm
        pocket_xmin = -depth
        pocket_xmax = outer_x + settings.clearance_mm
        margin = max(settings.clearance_mm, settings.chamfer_size_mm if settings.chamfer_edges else 0)
        arms = []
        for arm_low, arm_high in intervals:
            beam_points = ((settings.clearance_mm, -settings.root_length_mm),
                           (outer_x, -settings.root_length_mm), (outer_x, 0.0),
                           (tip_outer, settings.reach_mm), (settings.clearance_mm, settings.reach_mm))
            if settings.snap_style != "tapered":
                beam_points = (beam_points[0], beam_points[1], beam_points[3], beam_points[4])
            arm_beam = HookPrism(beam_points, arm_low, arm_high)
            hook = HookPrism(((-settings.hook_depth_mm, shoulder_z),
                              (shoulder_outer, shoulder_z),
                              (tip_outer, settings.reach_mm),
                              (settings.clearance_mm, settings.reach_mm)), arm_low, arm_high)
            roof_front = flat_top + pocket_xmax - pocket_xmin if settings.print_support else flat_top
            receiver = HookPrism(((pocket_xmin, shoulder_z - settings.clearance_mm),
                                  (pocket_xmax, shoulder_z - settings.clearance_mm),
                                  (pocket_xmax, roof_front), (pocket_xmin, flat_top)),
                                 arm_low - settings.clearance_mm, arm_high + settings.clearance_mm)
            bounds = BoxBounds(pocket_xmin, pocket_xmax, receiver.y_min_mm,
                               receiver.y_max_mm, shoulder_z - settings.clearance_mm, roof_front)
            opening_top = flat_top + (depth if settings.print_support else 0)
            cover = BoxBounds(pocket_xmin - margin, 0.0,
                              receiver.y_min_mm - margin, receiver.y_max_mm + margin,
                              bounds.z_min_mm - margin, opening_top + margin)
            arms.append(SnapArm(arm_beam, hook, receiver, bounds, cover))
        root_support = None
        root_bottom = -settings.root_length_mm
        if settings.print_support:
            root_bottom -= outer_x + settings.attachment_overlap_mm
            root_support = HookPrism(((-settings.attachment_overlap_mm, root_bottom),
                                      (outer_x, -settings.root_length_mm),
                                      (-settings.attachment_overlap_mm,
                                       -settings.root_length_mm + settings.attachment_overlap_mm)), low_y, high_y)
        root_cover = BoxBounds(-settings.attachment_overlap_mm, 0.0, low_y, high_y,
                               root_bottom, 0.0)
        receiver = BoxBounds(pocket_xmin, pocket_xmax, pocket_low_y, pocket_high_y,
                             shoulder_z - settings.clearance_mm, flat_top)
        units.append(SnapFitUnit(center, root, beam, arms[0].hook, receiver,
                                 tuple(arms), root_support, root_cover))
        previous_receiver_end = pocket_high_y
    return SnapFitPlan(settings, span, tuple(units))
