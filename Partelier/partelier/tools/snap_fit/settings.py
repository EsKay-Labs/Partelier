"""Immutable input contract for hook, detent, torsion and annular snap-fits.

Positive dimensions describe geometry only. They do not establish a suitable
strain, material, print orientation, fatigue life, or printer-specific fit.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
import math


def _length(name, value, *, allow_zero=False):
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
class SnapFitSettings:
    """All lengths are millimetres; hook depth measures engagement into B."""

    width_mm: float = 8.0
    thickness_mm: float = 1.5
    reach_mm: float = 16.0
    clearance_mm: float = 0.3
    hook_depth_mm: float = 1.0
    lead_in_mm: float = 3.0
    snap_count: int = 1
    start_margin_mm: float = 5.0
    end_margin_mm: float = 5.0
    root_length_mm: float = 4.0
    attachment_overlap_mm: float = 0.5
    snap_style: str = "standard"
    chamfer_edges: bool = True
    chamfer_size_mm: float = 0.3
    print_support: bool = True
    snap_family: str = "hook"
    ball_radius_mm: float = 2.0
    torsion_radius_mm: float = 0.8
    annular_bead_width_mm: float = 2.0
    annular_bead_height_mm: float = 0.5
    annular_offset_mm: float = 3.0

    def __post_init__(self):
        for field in fields(self):
            if field.name.endswith("_mm"):
                object.__setattr__(self, field.name, _length(
                    field.name, getattr(self, field.name),
                    allow_zero=field.name in {"start_margin_mm", "end_margin_mm"},
                ))
        self.validate()

    def validate(self):
        """Reject degenerate requests before selecting or editing native bodies."""
        for field in fields(self):
            if field.name.endswith("_mm"):
                _length(field.name, getattr(self, field.name),
                        allow_zero=field.name in {"start_margin_mm", "end_margin_mm"})
        if type(self.snap_count) is not int or not 1 <= self.snap_count <= 20:
            raise ValueError("Snap count must be an integer from 1 to 20.")
        if type(self.snap_style) is not str or self.snap_style not in ("standard", "tapered", "twin"):
            raise ValueError("Snap style must be standard, tapered or twin.")
        if type(self.chamfer_edges) is not bool:
            raise ValueError("Chamfer edges must be true or false.")
        if type(self.print_support) is not bool:
            raise ValueError("Print support must be true or false.")
        if type(self.snap_family) is not str or self.snap_family not in ("hook", "ball_detent", "torsion", "annular"):
            raise ValueError("Choose hook, ball_detent, torsion or annular.")
        if self.snap_family != "hook" and self.snap_style != "standard":
            raise ValueError("Hook variants apply only to the hook latch family.")
        if self.snap_family == "annular":
            if self.snap_count != 1 or self.chamfer_edges:
                raise ValueError("An annular ring needs count 1 and exposed chamfers off; its bead already has sloping sides.")
            if self.annular_offset_mm <= self.annular_bead_width_mm / 2 + self.clearance_mm:
                raise ValueError("Move the annular bead farther below the rim to retain material above its groove.")
            return
        if self.snap_family == "ball_detent":
            if not self.ball_radius_mm > self.hook_depth_mm / 2:
                raise ValueError("Ball diameter must exceed nose engagement.")
            if not self.ball_radius_mm * 2 < self.reach_mm:
                raise ValueError("Ball diameter must be smaller than beam reach.")
            if not self.ball_radius_mm - self.hook_depth_mm + self.ball_radius_mm > self.clearance_mm:
                raise ValueError("The ball must extend into the beam to join it.")
        gap = max(self.thickness_mm, 4.0 * self.clearance_mm + .2) if self.snap_style == "twin" else 0.0
        arm_width = ((self.width_mm - gap) / 2.0 if self.snap_style == "twin" else self.width_mm)
        if not math.isfinite(gap) or not math.isfinite(arm_width) or arm_width <= 0:
            raise ValueError("Twin arms need width greater than their middle gap (max thickness, 4 clearances + 0.2 mm).")
        tip_thickness = self.thickness_mm * (.65 if self.snap_style == "tapered" else 1.0)
        if self.chamfer_edges:
            size = self.chamfer_size_mm
            if not size < min(tip_thickness, arm_width, self.root_length_mm,
                              self.lead_in_mm, self.hook_depth_mm) / 2.0:
                raise ValueError("Chamfer size must be below half the tip thickness, arm width, root length, lead in and hook depth.")
        if not self.lead_in_mm < self.reach_mm:
            raise ValueError("Lead in must be smaller than the beam reach.")
        shoulder = self.reach_mm - self.lead_in_mm
        if not 0 < shoulder - self.clearance_mm < shoulder < self.reach_mm:
            raise ValueError("Reach must exceed the lead in plus clearance and leave a distinct receiving pocket.")
        if self.chamfer_edges and not shoulder > 4 * self.chamfer_size_mm:
            raise ValueError("Chamfer size needs beam reach beyond the lead in to preserve the root joint and retaining shoulder.")
        outer = self.clearance_mm + self.thickness_mm
        pocket_outer = outer + self.clearance_mm
        pocket_depth = self.hook_depth_mm + self.clearance_mm
        pocket_top = self.reach_mm + self.clearance_mm
        half_width = self.width_mm / 2.0
        pocket_half_width = half_width + self.clearance_mm
        derived = (outer, pocket_outer, pocket_depth, pocket_top,
                   pocket_half_width, outer + self.attachment_overlap_mm,
                   outer + self.hook_depth_mm, pocket_depth + pocket_outer,
                   2.0 * pocket_half_width, self.root_length_mm + self.reach_mm,
                   self.lead_in_mm + 2.0 * self.clearance_mm,
                   self.reach_mm + self.hook_depth_mm + 3 * self.clearance_mm,
                   self.root_length_mm + outer + self.attachment_overlap_mm)
        if (not all(math.isfinite(value) for value in derived)
                or not self.clearance_mm < outer < pocket_outer
                or not pocket_depth > self.hook_depth_mm
                or not pocket_top > self.reach_mm
                or not 0 < half_width < pocket_half_width):
            raise ValueError("Dimensions and clearance must produce distinct finite snap-fit surfaces.")

    def to_dict(self):
        """Return the complete JSON-compatible settings snapshot."""
        return asdict(self)

    @classmethod
    def from_dict(cls, values):
        """Reject partial, extra, or malformed settings instead of mixing states."""
        if not isinstance(values, Mapping):
            raise ValueError("Snap-fit settings must be an object.")
        expected = {field.name for field in fields(cls)}
        if set(values) != expected:
            raise ValueError("Snap-fit settings must contain exactly the supported dimension fields.")
        return cls(**values)
