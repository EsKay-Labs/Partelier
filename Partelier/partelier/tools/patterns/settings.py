"""Complete immutable surface-pattern settings, in millimetres and degrees."""

from dataclasses import asdict, dataclass, fields
import math
from .tiles import TILED_PATTERNS
from ..truss.planner import STYLES
from .grille_styles import GRILLES


@dataclass(frozen=True)
class PatternSettings:
    pattern: str = "hexagon"
    mode: str = "through"
    pitch_mm: float = 19.5
    web_mm: float = 7.0
    depth_mm: float = 1.0
    border_mm: float = 7.0
    rotation_deg: float = 0.0
    offset_u_mm: float = 0.0
    offset_v_mm: float = 0.0
    selection_scope: str = "faces"
    layout_mode: str = "auto"
    edge_mode: str = "clip"
    density: str = "balanced"
    size_locked: bool = False
    louver_angle_deg: float = 45.0
    grille_profile: str = "flat"
    grille_height_mm: float = 3.0
    grille_chamfer_mm: float = 0.0
    mount_mode: str = "off"
    mount_screw: str = "M4"
    mount_clearance_mm: float = .3
    mount_head_extra_percent: float = 10.0
    mount_head_mm: float = 0.0
    mount_inset_mm: float = 0.0
    truss_bays: int = 6
    truss_axis: str = 'long'
    truss_fillet_mm: float = 0.0
    pattern_fillet_mm: float = 0.0

    def __post_init__(self):
        for key in ("pitch_mm", "web_mm", "depth_mm", "border_mm", "rotation_deg", "offset_u_mm", "offset_v_mm", "louver_angle_deg", "grille_height_mm",
                    "mount_clearance_mm","mount_head_extra_percent","mount_head_mm","mount_inset_mm","truss_fillet_mm","pattern_fillet_mm","grille_chamfer_mm"):
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
        if self.pattern not in ("hexagon", "circle", "diamond", "square", "slot")+GRILLES+TILED_PATTERNS+STYLES:
            raise ValueError("Choose a supported pattern shape or polygon mosaic.")
        if self.mode not in ("through", "engrave", "emboss", "inlay"):
            raise ValueError("Choose through, engrave, emboss or flat colour.")
        if type(self.truss_bays) is not int or not 2<=self.truss_bays<=64 or self.truss_axis not in ('long','short'):
            raise ValueError('Use 2–64 whole Bays and Long side or Short side for the truss span.')
        if not 0<=self.truss_fillet_mm<=1000:
            raise ValueError('Truss fillet radius must be between 0 and 1000 mm; 0 keeps sharp junctions.')
        if not 0<=self.pattern_fillet_mm<=1000:
            raise ValueError('Pattern fillet radius must be between 0 and 1000 mm; 0 keeps the original cell perimeter.')
        if self.pattern in STYLES:
            if (self.mode!='through' or self.layout_mode!='fill' or self.selection_scope!='faces'
                    or self.grille_profile!='flat' or self.rotation_deg or self.offset_u_mm or self.offset_v_mm):
                raise ValueError('Planar trusses use one plate face, through openings, and Long/Short side direction.')
            if self.pattern!='truss_warren' and self.truss_bays%2:
                raise ValueError('Pratt and Howe need an even number of Bays for a symmetric centre.')
            if not .4<=self.web_mm<=100 or not .5<=self.border_mm<=1000:
                raise ValueError('Use Member width 0.4–100 mm and Frame width 0.5–1000 mm.')
        if not 0 <= self.louver_angle_deg <= 45:
            raise ValueError("Louver tilt must be between 0 and 45 degrees from the surface normal.")
        if self.pattern.startswith('grille_') and (self.mode != 'through' or self.layout_mode != 'fill'):
            raise ValueError("Grilles use through openings with fixed opening width and rib thickness.")
        if self.pattern=='grille_diffuser' and (self.rotation_deg or self.offset_u_mm or self.offset_v_mm):
            raise ValueError('Four-way diffusers are centred and aligned to the plate. Set Direction and offsets to 0.')
        if self.grille_profile not in ('flat','raised','chamfer'):
            raise ValueError('Choose Flat, Raised or Chamfered grille profile.')
        if not .2 <= self.grille_height_mm <= 20:
            raise ValueError('Grille height must be between 0.2 and 20 mm above the selected face.')
        if not 0 <= self.grille_chamfer_mm <= 20:
            raise ValueError('Chamfer size must be 0–20 mm; 0 uses the automatic size.')
        if self.mount_mode not in ('off','plain','countersink') or self.mount_screw not in ('M3','M4','M5','M6'):
            raise ValueError('Choose mounting holes Off, Plain or Countersunk and screw M3–M6.')
        if self.mount_mode!='off' and not self.pattern.startswith('grille_'):
            raise ValueError('Mounting holes are available in Grilles.')
        if (not 0<=self.mount_clearance_mm<=2 or not 0<=self.mount_head_extra_percent<=30
                or not 0<=self.mount_head_mm<=40 or not 0<=self.mount_inset_mm<=1000):
            raise ValueError('Mounting allowance or placement is outside the supported range.')
        if self.selection_scope not in ("faces", "body"):
            raise ValueError("Choose selected faces or the whole body.")
        if self.layout_mode not in ("auto", "balanced", "fill", "fit", "fixed"):
            raise ValueError("Choose Auto fit, Balanced, Fill face, Automatic size or Exact pitch.")
        if self.density not in ('sparse','balanced','dense') or type(self.size_locked) is not bool:
            raise ValueError('Choose a supported density and automatic or locked size.')
        if self.edge_mode not in ('clip','whole'):
            raise ValueError('Choose clipped or whole edge cells.')
        if min(self.pitch_mm, self.web_mm, self.depth_mm) <= 0 or self.border_mm < 0:
            raise ValueError("Pitch, web and depth must be positive; border may be zero.")
        if self.web_mm >= self.pitch_mm and self.pattern not in STYLES:
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
