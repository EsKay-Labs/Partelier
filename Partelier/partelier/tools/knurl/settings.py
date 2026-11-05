"""Strict dimensions for bounded, upright-print cylindrical grip relief."""
from dataclasses import asdict, dataclass, fields
import math

STYLES = ('diamond', 'straight', 'helical', 'chevron', 'waves', 'flutes',
          'scallops', 'dimples', 'pyramids', 'rings')
ANGLED_STYLES = ('diamond', 'helical', 'chevron', 'waves')
BOUNDS = {'pitch_mm': (2., 30.), 'depth_mm': (.1, 3.), 'border_mm': (0., 20.),
          'angle_deg': (0., 45.), 'phase_deg': (-360., 360.)}


@dataclass(frozen=True)
class KnurlSettings:
    style: str = 'diamond'
    pitch_mm: float = 6.
    depth_mm: float = .6
    border_mm: float = 1.
    angle_deg: float = 30.
    phase_deg: float = 0.

    def __post_init__(self):
        if self.style not in STYLES:
            raise ValueError('Choose a supported grip texture.')
        for name, (low, high) in BOUNDS.items():
            value = getattr(self, name)
            try:
                valid = type(value) in (int, float) and math.isfinite(value) and low <= value <= high
            except OverflowError:
                valid = False
            if not valid:
                unit = 'degrees' if name.endswith('_deg') else 'mm'
                raise ValueError(f'{name.replace("_", " ")} must be {low:g}–{high:g} {unit}.')

    def validate(self):
        self.__post_init__()
        return self

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {f.name for f in fields(cls)}:
            raise ValueError('Grip settings must contain exactly the current dimensions.')
        return cls(**value)
