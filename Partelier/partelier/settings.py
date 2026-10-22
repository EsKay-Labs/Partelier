"""Host-independent honeycomb settings, expressed in millimetres.

Cell size is the distance between opposite hexagon wall centre lines. These are
input checks only; they do not establish that geometry exists or is printable.
"""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class HoneycombSettings:
    """Illustrative defaults for the first honeycomb workflow."""

    cell_size_mm: float = 10.0
    wall_thickness_mm: float = 1.2

    def __post_init__(self):
        for label, value in (
            ("Cell size", self.cell_size_mm),
            ("Wall thickness", self.wall_thickness_mm),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{label} must be a finite number greater than zero.")
        if self.wall_thickness_mm >= self.cell_size_mm:
            raise ValueError("Wall thickness must be smaller than cell size.")

    @classmethod
    def from_centimetres(cls, cell_size_cm, wall_thickness_cm):
        """Convert the two Fusion length values at the host boundary."""
        return cls(
            cell_size_mm=cell_size_cm * 10.0,
            wall_thickness_mm=wall_thickness_cm * 10.0,
        )
