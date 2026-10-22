"""Immutable, host-independent separate-pin hinge dimensions.

The bounds below establish a finite, nondegenerate geometry request. They do
not establish a printer-specific fit or a mechanical load rating.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
import math

from .finish import validate_edge_finish


def _length_value(name, value, *, allow_zero=False):
    label = name.removesuffix("_mm").replace("_", " ").capitalize()
    try:
        valid = (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
            and (value >= 0 if allow_zero else value > 0)
        )
    except OverflowError:
        valid = False
    if not valid:
        qualifier = "nonnegative finite number" if allow_zero else "finite number greater than zero"
        raise ValueError(f"{label} must be a {qualifier} (mm).")
    return float(value)


@dataclass(frozen=True)
class HingeSettings:
    """Lengths are millimetres; clearance is diametral, not radial."""

    length_mm: float = 40.0
    hinge_count: int = 1
    start_margin_mm: float = 0.0
    end_margin_mm: float = 0.0
    knuckle_count: int = 5
    barrel_diameter_mm: float = 8.0
    pin_diameter_mm: float = 3.0
    diametral_clearance_mm: float = 0.3
    axial_gap_mm: float = 0.3
    rotation_clearance_mm: float = 0.3
    leaf_reach_mm: float = 12.0
    leaf_thickness_mm: float = 2.0
    attachment_overlap_mm: float = 0.5
    pin_overhang_mm: float = 2.0
    axis_offset_mm: float = 4.0
    include_pin: bool = True
    split_seam: bool = False
    seam_clearance_mm: float = 0.3
    output_mode: str = "attached"
    leaf_profile: str = "rectangular"
    leaf_barrel_clearance_mm: float = 0.3
    screw_holes: bool = False
    screw_diameter_mm: float = 3.2
    screw_end_margin_mm: float = 6.0
    knuckle_profile: str = "round"
    web_profile: str = "tangent"
    fillet_edges: bool = False
    fillet_radius_mm: float = 0.6
    chamfer_edges: bool = False
    chamfer_size_mm: float = 0.3

    def __post_init__(self):
        # Normalize accepted integer lengths before arithmetic. Otherwise a
        # large integer sum can overflow during implicit float conversion.
        for field in fields(self):
            if field.name.endswith("_mm"):
                object.__setattr__(self, field.name, _length_value(
                    field.name, getattr(self, field.name),
                    allow_zero=field.name in {"start_margin_mm", "end_margin_mm", "rotation_clearance_mm"},
                ))
        self.validate()

    def validate(self):
        """Raise an actionable ValueError before a host operation starts."""
        for field in fields(self):
            if field.name in {"hinge_count", "knuckle_count", "include_pin", "split_seam",
                              "output_mode", "leaf_profile", "screw_holes", "chamfer_edges",
                              "knuckle_profile", "fillet_edges", "web_profile"}:
                continue
            _length_value(field.name, getattr(self, field.name),
                          allow_zero=field.name in {"start_margin_mm", "end_margin_mm", "rotation_clearance_mm"})
        if type(self.hinge_count) is not int or not 1 <= self.hinge_count <= 20:
            raise ValueError("Hinge count must be an integer from 1 to 20.")
        if type(self.knuckle_count) is not int or self.knuckle_count not in range(3, 16, 2):
            raise ValueError("Knuckle count must be an odd integer from 3 to 15.")
        if type(self.include_pin) is not bool:
            raise ValueError("Include pin must be true or false.")
        if type(self.split_seam) is not bool:
            raise ValueError("Split seam must be true or false.")
        if type(self.output_mode) is not str or self.output_mode not in ("attached", "separate"):
            raise ValueError("Output mode must be attached or separate.")
        if type(self.leaf_profile) is not str or self.leaf_profile not in ("rectangular", "rounded"):
            raise ValueError("Leaf profile must be rectangular or rounded.")
        if type(self.knuckle_profile) is not str or self.knuckle_profile not in ("round", "square"):
            raise ValueError("Knuckle profile must be round or square.")
        if type(self.web_profile) is not str or self.web_profile not in ("tangent", "flat"):
            raise ValueError("Attachment shape must be tangent or flat.")
        if type(self.screw_holes) is not bool:
            raise ValueError("Screw holes must be true or false.")
        if (self.output_mode == "attached" and self.split_seam
                and self.seam_clearance_mm / 2 >= self.leaf_reach_mm):
            raise ValueError("Seam clearance must be smaller than twice the leaf reach.")

        barrel_radius = self.barrel_diameter_mm / 2.0
        if self.rotation_clearance_mm and (not math.isfinite(barrel_radius + self.rotation_clearance_mm)
                or not barrel_radius + self.rotation_clearance_mm > barrel_radius
                or not math.isfinite(self.length_mm / 2 + self.rotation_clearance_mm)):
            raise ValueError("Movement clearance must produce a distinct finite housing envelope.")
        pin_radius = self.pin_diameter_mm / 2.0
        bore_radius = (self.pin_diameter_mm + self.diametral_clearance_mm) / 2.0
        if not 0 < pin_radius < bore_radius < barrel_radius:
            raise ValueError(
                "Pin diameter plus diametral clearance must be smaller than the barrel diameter, "
                "with a positive, representable clearance."
            )
        if self.knuckle_profile == "square" and not bore_radius < barrel_radius / math.sqrt(2):
            raise ValueError("The pin bore must fit inside the square housing. Increase the housing envelope or reduce pin/clearance.")
        if self.leaf_thickness_mm >= barrel_radius - bore_radius:
            raise ValueError(
                "Leaf thickness must be smaller than the barrel radius minus the bore radius "
                "so the attachment cannot fill the pin bore."
            )
        minimum_overlap_height = barrel_radius * (1.0 - (1 / math.sqrt(2)
            if self.knuckle_profile == "square" else math.sqrt(3.0) / 2.0))
        if self.leaf_thickness_mm <= minimum_overlap_height:
            raise ValueError(
                "Leaf thickness must exceed the barrel contact height "
                f"({minimum_overlap_height:.6g} mm) so the web intersects the barrel."
            )
        if self.leaf_reach_mm <= barrel_radius:
            raise ValueError("Leaf reach must be greater than the barrel radius.")
        if self.output_mode == "separate":
            inner_x = barrel_radius + self.leaf_barrel_clearance_mm
            width = self.leaf_reach_mm - inner_x
            web_end = inner_x + min(width / 2.0, self.leaf_thickness_mm)
            if (not math.isfinite(inner_x) or not math.isfinite(width) or width <= 0
                    or not inner_x < web_end <= self.leaf_reach_mm):
                raise ValueError(
                    "Separate leaf reach must exceed the barrel radius plus leaf barrel clearance "
                    "and leave a distinct plate and attachment width."
                )
            if self.leaf_profile == "rounded":
                corner_radius = min(width / 4.0, self.length_mm / 8.0,
                                    self.leaf_thickness_mm / 2.0)
                if not math.isfinite(corner_radius) or corner_radius <= 0:
                    raise ValueError("Rounded leaf corners must have a positive, representable radius.")
            if self.screw_holes:
                hole_radius = self.screw_diameter_mm / 2.0
                hole_x = inner_x + width / 2.0
                hole_y = self.length_mm / 2.0 - self.screw_end_margin_mm
                if (hole_radius <= 0 or not math.isfinite(hole_x)
                        or not inner_x < hole_x - hole_radius < hole_x + hole_radius < self.leaf_reach_mm):
                    raise ValueError(
                        "Screw holes must leave positive material at both sides of each leaf. "
                        "Reduce screw diameter or increase leaf reach."
                    )
                if (not self.screw_end_margin_mm > hole_radius
                        or not hole_y > hole_radius
                        or not -self.length_mm / 2.0 < -hole_y - hole_radius
                        or not hole_y + hole_radius < self.length_mm / 2.0):
                    raise ValueError(
                        "Screw end margin must exceed the hole radius and leave positive material "
                        "between the two holes. Increase hinge length or adjust margin/diameter."
                    )
                # Hole centres lie on the plate's mid-width line. The rounded
                # free-corner radius is at most width/4, so its corner centres
                # remain outside this line. Positive side and end clearances
                # therefore also contain each full circle inside the rounded
                # profile; no screw clearance or material-strength claim follows.
        usable_length = self.length_mm - (self.knuckle_count - 1) * self.axial_gap_mm
        if not math.isfinite(usable_length) or usable_length <= 0:
            raise ValueError("Hinge length must exceed the total axial gaps between knuckles.")
        pin_end = self.length_mm / 2.0 + self.pin_overhang_mm
        if not math.isfinite(pin_end):
            raise ValueError("Hinge length and pin overhang must produce finite pin endpoints.")

        # Positive input values can still collapse to zero or erase a gap at
        # floating-point precision. Reject that before the CAD adapter sees it.
        span = usable_length / self.knuckle_count
        previous_end = None
        for index in range(self.knuckle_count):
            start = -self.length_mm / 2.0 + index * (span + self.axial_gap_mm)
            end = self.length_mm / 2.0 if index == self.knuckle_count - 1 else start + span
            if not end > start or (previous_end is not None and not start > previous_end):
                raise ValueError("Hinge length and axial gap must produce distinct knuckle intervals.")
            previous_end = end
        validate_edge_finish(self)

    def to_dict(self):
        """Return JSON-compatible recipe dimensions, without host objects."""
        return asdict(self)

    @classmethod
    def from_dict(cls, values):
        """Read a complete recipe and reject missing or unrecognized fields."""
        if not isinstance(values, Mapping):
            raise ValueError("Hinge settings must be an object.")
        expected = {field.name for field in fields(cls)}
        if set(values) != expected:
            raise ValueError("Hinge settings must contain exactly the supported dimension fields.")
        return cls(**values)
