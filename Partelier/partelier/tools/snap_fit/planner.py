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
class SnapFitUnit:
    center_y_mm: float
    root: BoxBounds
    beam: BoxBounds
    hook: HookPrism
    receiver: BoxBounds


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
    pocket_half_width = half_width + settings.clearance_mm
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
        # The right two vertices lie at the beam's outside surface. This gives
        # the hook a positive-volume overlap with the beam before their join.
        hook = HookPrism(((-settings.hook_depth_mm, shoulder_z),
                          (outer_x, shoulder_z),
                          (outer_x, settings.reach_mm),
                          (settings.clearance_mm, settings.reach_mm)), low_y, high_y)
        receiver = BoxBounds(-settings.hook_depth_mm - settings.clearance_mm,
                             outer_x + settings.clearance_mm,
                             pocket_low_y, pocket_high_y,
                             shoulder_z - settings.clearance_mm,
                             settings.reach_mm + settings.clearance_mm)
        units.append(SnapFitUnit(center, root, beam, hook, receiver))
        previous_receiver_end = pocket_high_y
    return SnapFitPlan(settings, span, tuple(units))
