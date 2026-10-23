"""Complete immutable surface-pattern settings, in millimetres and degrees."""

from dataclasses import asdict, dataclass, fields
import math


@dataclass(frozen=True)
class PatternSettings:
    pattern: str = "hexagon"
    mode: str = "through"
    pitch_mm: float = 8.0
    web_mm: float = 1.2
    depth_mm: float = 1.0
    border_mm: float = 2.0
    rotation_deg: float = 0.0
    offset_u_mm: float = 0.0
    offset_v_mm: float = 0.0
    selection_scope: str = "faces"
    layout_mode: str = "fit"

    def __post_init__(self):
        for key in ("pitch_mm", "web_mm", "depth_mm", "border_mm", "rotation_deg", "offset_u_mm", "offset_v_mm"):
            value = getattr(self, key)
            try:
                finite = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite:
                raise ValueError("Pattern dimensions must be finite numbers.")
            object.__setattr__(self, key, float(value))
        self.validate()

    def validate(self):
        if self.pattern not in ("hexagon", "circle", "diamond", "square", "slot"):
            raise ValueError("Choose hexagon, circle, diamond, square or slot.")
        if self.mode not in ("through", "engrave", "emboss"):
            raise ValueError("Choose through, engrave or emboss.")
        if self.selection_scope not in ("faces", "body"):
            raise ValueError("Choose selected faces or the whole body.")
        if self.layout_mode not in ("fit", "fixed"):
            raise ValueError("Choose Automatic spacing or Exact pitch.")
        if min(self.pitch_mm, self.web_mm, self.depth_mm) <= 0 or self.border_mm < 0:
            raise ValueError("Pitch, web and depth must be positive; border may be zero.")
        if self.web_mm >= self.pitch_mm:
            raise ValueError("Web thickness must be smaller than pitch.")
        if self.pitch_mm > 10000 or self.depth_mm > 1000 or abs(self.rotation_deg)>36000:
            raise ValueError("Pattern dimensions exceed the supported working range.")
        if max(abs(self.offset_u_mm), abs(self.offset_v_mm), self.border_mm)>100000:
            raise ValueError("Pattern offsets or border exceed the supported working range.")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, values):
        if not isinstance(values, dict) or set(values) != {field.name for field in fields(cls)}:
            raise ValueError("Pattern settings must contain exactly the supported fields.")
        return cls(**values)
