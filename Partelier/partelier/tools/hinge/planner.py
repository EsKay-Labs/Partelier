"""Pure geometry plan for an alternating separate-pin hinge.

The axis runs along local Y, centered on the hinge length. The attachment
plane is Z=0 and the barrel center is (X=0, Z=barrel_radius). Owner A extends
in negative X; B extends in positive X. Placement and attachment selection
belong to the Fusion adapter. No source-body geometry is mutated here.
"""

from dataclasses import dataclass


from .settings import HingeSettings


@dataclass(frozen=True)
class Knuckle:
    owner: str
    start_mm: float
    end_mm: float

    @property
    def length_mm(self):
        return self.end_mm - self.start_mm


@dataclass(frozen=True)
class WebBounds:
    owner: str
    x_min_mm: float
    x_max_mm: float
    y_min_mm: float
    y_max_mm: float
    z_min_mm: float
    z_max_mm: float


@dataclass(frozen=True)
class LeafPlate:
    """One separate plate; radius rounds only the two free outer corners.

    For A the free edge is x_min_mm; for B it is x_max_mm. The edge nearest
    the barrel stays straight so the alternating attachment webs can join it.
    """

    owner: str
    x_min_mm: float
    x_max_mm: float
    y_min_mm: float
    y_max_mm: float
    z_min_mm: float
    z_max_mm: float
    corner_radius_mm: float


@dataclass(frozen=True)
class MountingHole:
    """A through-hole normal to the leaf plane, in the unit's local frame."""

    owner: str
    x_mm: float
    y_mm: float
    diameter_mm: float


@dataclass(frozen=True)
class HingePlan:
    settings: HingeSettings
    knuckles: tuple[Knuckle, ...]
    barrel_radius_mm: float
    bore_radius_mm: float
    pin_start_mm: float
    pin_end_mm: float
    webs: tuple[WebBounds, ...]
    plates: tuple[LeafPlate, ...] = ()
    mounting_holes: tuple[MountingHole, ...] = ()


def build_hinge_plan(settings):
    """Plan bounded knuckles and attachment webs without importing Fusion."""
    if not isinstance(settings, HingeSettings):
        raise ValueError("Build the hinge plan from HingeSettings.")
    settings.validate()
    radius = settings.barrel_diameter_mm / 2.0
    bore_radius = (settings.pin_diameter_mm + settings.diametral_clearance_mm) / 2.0
    span = (
        settings.length_mm - (settings.knuckle_count - 1) * settings.axial_gap_mm
    ) / settings.knuckle_count
    knuckles = []
    webs = []
    separate = settings.output_mode == "separate"
    plate_inner_x = radius + settings.leaf_barrel_clearance_mm
    plate_width = settings.leaf_reach_mm - plate_inner_x
    web_reach = (plate_inner_x + min(plate_width / 2.0, settings.leaf_thickness_mm)
                 if separate else settings.leaf_reach_mm)
    if separate and settings.screw_holes and settings.web_profile == "tangent":
        finish = (settings.fillet_radius_mm if settings.fillet_edges else
                  settings.chamfer_size_mm if settings.chamfer_edges else 0.0)
        # Use most of the hole-safe span rather than halving it: a narrow
        # derived neck can disappear under a uniform cap fillet. Reserve 15%
        # before the finished screw-hole lip; user dimensions stay unchanged.
        available = plate_width / 2 - settings.screw_diameter_mm / 2 - finish
        web_reach = min(web_reach, plate_inner_x + .85 * available)
        if not plate_inner_x < web_reach < plate_inner_x + available:
            raise ValueError("Screw-hole entries must leave room for the tapered attachment. "
                             "Increase leaf reach or reduce hole diameter/edge finish.")
    for index in range(settings.knuckle_count):
        owner = "A" if index % 2 == 0 else "B"
        start = -settings.length_mm / 2.0 + index * (span + settings.axial_gap_mm)
        end = settings.length_mm / 2.0 if index == settings.knuckle_count - 1 else start + span
        knuckles.append(Knuckle(owner, start, end))
        if owner == "A":
            x_min, x_max = -web_reach, -radius / 2.0
        else:
            x_min, x_max = radius / 2.0, web_reach
        webs.append(WebBounds(
            owner=owner,
            x_min_mm=x_min,
            x_max_mm=x_max,
            y_min_mm=start,
            y_max_mm=end,
            z_min_mm=0.0 if separate else -settings.attachment_overlap_mm,
            z_max_mm=settings.leaf_thickness_mm,
        ))
    plates = []
    mounting_holes = []
    if separate:
        corner_radius = (min(plate_width / 4.0, settings.length_mm / 8.0,
                             settings.leaf_thickness_mm / 2.0)
                         if settings.leaf_profile == "rounded" else 0.0)
        for owner in ("A", "B"):
            x_min, x_max = ((-settings.leaf_reach_mm, -plate_inner_x) if owner == "A"
                            else (plate_inner_x, settings.leaf_reach_mm))
            plates.append(LeafPlate(owner, x_min, x_max,
                                    -settings.length_mm / 2.0, settings.length_mm / 2.0,
                                    0.0, settings.leaf_thickness_mm, corner_radius))
            if settings.screw_holes:
                hole_x = (-1 if owner == "A" else 1) * (plate_inner_x + plate_width / 2.0)
                end_y = settings.length_mm / 2.0 - settings.screw_end_margin_mm
                for hole_y in (-end_y, end_y):
                    mounting_holes.append(MountingHole(owner, hole_x, hole_y,
                                                        settings.screw_diameter_mm))
    return HingePlan(
        settings=settings,
        knuckles=tuple(knuckles),
        barrel_radius_mm=radius,
        bore_radius_mm=bore_radius,
        pin_start_mm=-settings.length_mm / 2.0 - settings.pin_overhang_mm,
        pin_end_mm=settings.length_mm / 2.0 + settings.pin_overhang_mm,
        webs=tuple(webs),
        plates=tuple(plates),
        mounting_holes=tuple(mounting_holes),
    )
