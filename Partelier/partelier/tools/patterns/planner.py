"""Deterministic chart-space layouts. Surface acceptance happens separately."""

from dataclasses import dataclass
import math


MAX_CANDIDATES = 4000
MAX_CELLS = 400
MAX_FACE_CELLS = 200


class PatternDensityError(ValueError):
    """A bounded refusal with an explicitly approximate, non-applied hint."""

    def __init__(self, message, suggested_pitch_mm):
        super().__init__(message)
        self.suggested_pitch_mm = suggested_pitch_mm


def density_error(settings, areas_mm2, *, face_index=0, face_cells=0,
                  total_cells=0, candidates=None):
    """Estimate a useful pitch without building additional cells or solids.

    Surface area/lattice area ignores borders, trims and chart distortion, so
    this is guidance rather than a guaranteed fit or an automatic size change.
    """
    factor = math.sqrt(3)/2 if settings.pattern in ('hexagon', 'circle') else 1
    estimates = [area/(factor*settings.pitch_mm**2) for area in areas_mm2
                 if isinstance(area, (int, float)) and math.isfinite(area) and area>0]
    ratio = max([1.0, sum(estimates)/MAX_CELLS,
                 face_cells/MAX_FACE_CELLS, total_cells/MAX_CELLS]
                + [count/MAX_FACE_CELLS for count in estimates])
    hint = math.ceil(max(settings.pitch_mm*1.25,
                         settings.pitch_mm*math.sqrt(ratio)*1.1)*10)/10
    faces = len(areas_mm2)
    selected = f"{faces} face{'s' if faces!=1 else ''} selected"
    if candidates is not None:
        reason = f"The layout exceeds {MAX_CANDIDATES:,} candidate positions"
    elif face_cells>MAX_FACE_CELLS:
        reason = f"Face {face_index+1} exceeds {MAX_FACE_CELLS} pattern cells"
    else:
        reason = f"The selection exceeds {MAX_CELLS} pattern cells in total"
    suggestion = (f"Try Pitch about {hint:g} mm or higher (estimate)."
                  if hint<=10000 else "Use a smaller face region; the estimated pitch exceeds the supported range.")
    message = (f"Pattern is too dense. {reason} ({selected}). A cell is one pattern repetition. "
               f"Current Pitch: {settings.pitch_mm:g} mm. {suggestion} "
               f"Limits: {MAX_FACE_CELLS} cells per face, {MAX_CELLS} total.")
    return PatternDensityError(message, hint if hint<=10000 else None)


@dataclass(frozen=True)
class Cell:
    center_mm: tuple
    polygon_mm: tuple

    @property
    def radius_mm(self):
        return max(math.hypot(x, y) for x, y in self.polygon_mm)


def _polygon(settings):
    width = settings.pitch_mm-settings.web_mm
    if settings.pattern == "hexagon":
        radius, count, phase = width/math.sqrt(3), 6, math.pi/6
        points = [(radius*math.cos(phase+2*math.pi*i/count),radius*math.sin(phase+2*math.pi*i/count)) for i in range(count)]
    elif settings.pattern == "circle":
        points = [(width/2*math.cos(2*math.pi*i/32),width/2*math.sin(2*math.pi*i/32)) for i in range(32)]
    elif settings.pattern == "diamond":
        points = [(width/2,0),(0,width/2),(-width/2,0),(0,-width/2)]
    elif settings.pattern == "square":
        points = [(-width/2,-width/2),(width/2,-width/2),(width/2,width/2),(-width/2,width/2)]
    else:
        # Capsule length = opening width; rounded ends remain separated by web.
        radius=width*.2; half=width/2-radius
        points=[(half+radius*math.cos(-math.pi/2+math.pi*i/12),radius*math.sin(-math.pi/2+math.pi*i/12)) for i in range(13)]
        points += [(-half+radius*math.cos(math.pi/2+math.pi*i/12),radius*math.sin(math.pi/2+math.pi*i/12)) for i in range(13)]
    angle=math.radians(settings.rotation_deg)
    return tuple((x*math.cos(angle)-y*math.sin(angle),x*math.sin(angle)+y*math.cos(angle)) for x,y in points)


def build_cells(settings, bounds, period_u_mm=None):
    settings.validate()
    if len(bounds)!=4 or not all(math.isfinite(v) for v in bounds):
        raise ValueError("The selected face has no finite pattern region.")
    low_u, high_u, low_v, high_v = bounds
    if low_u>=high_u or low_v>=high_v:
        raise ValueError("The selected face has no usable pattern region.")
    pitch=settings.pitch_mm
    periodic=period_u_mm is not None
    angle=math.radians(settings.rotation_deg)
    center=((low_u+high_u)/2,(low_v+high_v)/2)
    original=bounds
    if periodic:
        symmetry={"hexagon":60,"square":90,"diamond":90,"slot":180}.get(settings.pattern)
        if symmetry and abs(settings.rotation_deg/symmetry-round(settings.rotation_deg/symmetry))>1e-8:
            raise ValueError("A full wrap currently needs rotation in multiples of "+str(symmetry)+" degrees for this shape.")
    else:
        corners=[((u-center[0])*math.cos(angle)+(v-center[1])*math.sin(angle)+center[0],
                  -(u-center[0])*math.sin(angle)+(v-center[1])*math.cos(angle)+center[1])
                 for u in (low_u,high_u) for v in (low_v,high_v)]
        low_u,high_u=min(p[0] for p in corners),max(p[0] for p in corners)
        low_v,high_v=min(p[1] for p in corners),max(p[1] for p in corners)
    if periodic:
        if not math.isfinite(period_u_mm) or period_u_mm <= 0:
            raise ValueError("The wrap period must be finite and positive.")
        columns=math.floor(period_u_mm/pitch)
        if columns<3:
            raise ValueError("Reduce pitch to fit at least three cells around the curved face.")
        # Round down the count, so closing the seam never reduces the requested web.
        step_u=period_u_mm/columns
    else:
        step_u=pitch
        columns=math.ceil((high_u-low_u)/step_u)+2
    step_v=pitch*math.sqrt(3)/2 if settings.pattern in ("hexagon", "circle") else pitch
    rows=math.ceil((high_v-low_v)/step_v)+2
    if rows*columns>MAX_CANDIDATES:
        raise density_error(settings, [(original[1]-original[0])*(original[3]-original[2])],
                            candidates=rows*columns)
    polygon=_polygon(settings)
    result=[]
    # Center the grid, while keeping offsets periodic rather than moving it away.
    offset_u=settings.offset_u_mm%step_u
    offset_v=settings.offset_v_mm%step_v
    for row in range(-1,rows-1):
        base_v=low_v+row*step_v+offset_v
        stagger=step_u/2 if settings.pattern in ("hexagon","circle") and row%2 else 0
        for column in range(columns):
            v=base_v
            u=low_u+column*step_u+stagger+offset_u
            if periodic:
                u=low_u+(u-low_u)%period_u_mm
            else:
                u-=step_u
                du,dv=u-center[0],v-center[1]
                u=center[0]+du*math.cos(angle)-dv*math.sin(angle)
                v=center[1]+du*math.sin(angle)+dv*math.cos(angle)
            if original[0]-1e-8<=u<original[1]-1e-8 and original[2]-1e-8<=v<=original[3]+1e-8:
                result.append(Cell((u,v),polygon))
    return tuple(result)
