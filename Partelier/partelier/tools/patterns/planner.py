"""Deterministic chart-space layouts. Surface acceptance happens separately."""

from dataclasses import dataclass, replace
import math
from . import clipping


MAX_CANDIDATES = 4000
MAX_CELLS = 400
MAX_FACE_CELLS = 200
BALANCED_FACE_CELLS = 48


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
    if settings.layout_mode == 'fill':
        size_hint = max(.001, hint-settings.web_mm)
        message = (f"Fill face is too dense. {reason}. "
                   f"Current Cell size: {settings.pitch_mm-settings.web_mm:g} mm; "
                   f"Minimum gap: {settings.web_mm:g} mm. "
                   f"Try Cell size about {size_hint:g} mm or higher (estimate), or choose Balanced. "
                   f"Limits: {MAX_FACE_CELLS} cells per face, {MAX_CELLS} total. Your size was not changed.")
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


def _build_legacy(settings, bounds, period_u_mm=None):
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

@dataclass(frozen=True)
class Layout:
    """Cells with resolved center spacing; opening size may be independent."""
    cells: tuple
    effective_pitch_mm: float
    requested_pitch_mm: float
    layout_mode: str

    @property
    def cell_count(self):
        return len(self.cells)

    @property
    def pitch_mm(self):
        return self.effective_pitch_mm


FIT_SHORTLIST = 3
FIT_ACCEPT_LIMIT = MAX_FACE_CELLS * FIT_SHORTLIST
_FIT_EPSILON = 1e-8


def _fit_bounds(bounds, border, periodic):
    if (not isinstance(bounds, (tuple, list)) or len(bounds) != 4
            or not all(isinstance(value, (int, float)) and not isinstance(value, bool)
                       and math.isfinite(value) for value in bounds)):
        raise ValueError("The selected face has no finite pattern region.")
    low_u, high_u, low_v, high_v = map(float, bounds)
    if low_u >= high_u or low_v >= high_v:
        raise ValueError("The selected face has no usable pattern region.")
    if not periodic:
        low_u, high_u = low_u + border, high_u - border
    low_v, high_v = low_v + border, high_v - border
    if low_u >= high_u or low_v >= high_v:
        return None
    return low_u, high_u, low_v, high_v


def _extents(polygon):
    return (max(point[0] for point in polygon)-min(point[0] for point in polygon),
            max(point[1] for point in polygon)-min(point[1] for point in polygon))


def _center_envelope(cells):
    return (min(cell.center_mm[0]+point[0] for cell in cells for point in cell.polygon_mm),
            max(cell.center_mm[0]+point[0] for cell in cells for point in cell.polygon_mm),
            min(cell.center_mm[1]+point[1] for cell in cells for point in cell.polygon_mm),
            max(cell.center_mm[1]+point[1] for cell in cells for point in cell.polygon_mm))


def _projected_size(bounds, angle):
    width, height = bounds[1]-bounds[0], bounds[3]-bounds[2]
    return (abs(math.cos(angle))*width+abs(math.sin(angle))*height,
            abs(math.sin(angle))*width+abs(math.cos(angle))*height)


def _complete(center, polygon, bounds, periodic):
    low_u, high_u, low_v, high_v = bounds
    reserve = max(math.hypot(u,v) for u,v in polygon)*1.05
    if (center[1]-reserve < low_v-_FIT_EPSILON or center[1]+reserve > high_v+_FIT_EPSILON
            or (not periodic and (center[0]-reserve < low_u-_FIT_EPSILON
                                  or center[0]+reserve > high_u+_FIT_EPSILON))):
        return False
    for du, dv in polygon:
        if not low_v-_FIT_EPSILON <= center[1]+dv <= high_v+_FIT_EPSILON:
            return False
        if not periodic and not low_u-_FIT_EPSILON <= center[0]+du <= high_u+_FIT_EPSILON:
            return False
    return True


def _fit_grid(settings, bounds, pitch, period, phase, *, preserve_size=False, spread=False):
    if settings.edge_mode=='clip':
        return _clipped_grid(settings,bounds,pitch,period,phase,preserve_size=preserve_size,spread=spread)
    periodic = period is not None
    if periodic:
        columns = int(math.floor(period/pitch)) if preserve_size else max(3, int(round(period/pitch)))
        if columns < 3:
            raise ValueError("Reduce cell size to fit at least three cells around the curved face.")
        pitch = period/columns
    effective = settings if preserve_size else replace(settings, pitch_mm=pitch)
    polygon = _polygon(effective)
    unrotated = _polygon(replace(effective, rotation_deg=0.0))
    # Match SurfaceMap's existing conservative 1.05 circumradius margin.
    # Count proposals by eligible CENTER space, so native acceptance cannot
    # remove an entire outer row/column solely because of this same guard.
    reserve = max(math.hypot(u,v) for u,v in unrotated)*1.05
    opening_u = opening_v = 2*reserve
    triangular = settings.pattern in ("hexagon", "circle")
    factor = math.sqrt(3)/2 if triangular else 1.0
    step_v = factor*(settings.pitch_mm if preserve_size and not spread else pitch)
    angle = math.radians(settings.rotation_deg)
    width, height = _projected_size(bounds, angle) if not periodic else (period, bounds[3]-bounds[2])
    if not periodic:
        columns = math.floor((width-opening_u+_FIT_EPSILON)/pitch)+1
    rows = math.floor((height-opening_v+_FIT_EPSILON)/step_v)+1
    if min(columns, rows) < 1:
        return (), pitch
    if rows*columns > MAX_CANDIDATES:
        return None, pitch
    center = ((bounds[0]+bounds[1])/2, (bounds[2]+bounds[3])/2)
    offset_u = math.remainder(settings.offset_u_mm, pitch)
    offset_v = math.remainder(settings.offset_v_mm, step_v)
    result = []
    for row in range(rows):
        short = triangular and (row+phase)%2
        count = columns if periodic or not short else columns-1
        for column in range(count):
            local_v = (row-(rows-1)/2)*step_v+offset_v
            if periodic:
                local_u = column*pitch+(pitch/2 if short else 0)+offset_u
                position = (bounds[0]+local_u%period, center[1]+local_v)
            else:
                local_u = (column-(count-1)/2)*pitch+offset_u
                position = (center[0]+local_u*math.cos(angle)-local_v*math.sin(angle),
                            center[1]+local_u*math.sin(angle)+local_v*math.cos(angle))
            if _complete(position, polygon, bounds, periodic):
                result.append(Cell(position, polygon))
    if (result and not periodic and offset_u == 0 and offset_v == 0):
        # Rotation/whole-cell pruning can leave a noncentral finite envelope.
        # A common translation preserves every lattice spacing and is safe:
        # the complete envelope is no larger than the available rectangle.
        envelope = _center_envelope(result)
        shift = (center[0]-(envelope[0]+envelope[1])/2,
                 center[1]-(envelope[2]+envelope[3])/2)
        result = [Cell((cell.center_mm[0]+shift[0], cell.center_mm[1]+shift[1]), polygon)
                  for cell in result]
    return tuple(result), pitch


def _clipped_grid(settings,bounds,pitch,period,phase,*,preserve_size=False,spread=False):
    periodic=period is not None
    columns=None
    if periodic:
        columns=math.floor(period/pitch) if preserve_size else max(3,round(period/pitch))
        if columns<3:raise ValueError('Reduce cell size to fit three cells around the curved face.')
        pitch=period/columns
    effective=settings if preserve_size else replace(settings,pitch_mm=pitch)
    polygon=_polygon(effective)
    triangular=settings.pattern in ('hexagon','circle')
    step_v=(settings.pitch_mm if preserve_size and not spread else pitch)*(math.sqrt(3)/2 if triangular else 1)
    angle=math.radians(settings.rotation_deg)
    width,height=_projected_size(bounds,angle) if not periodic else (period,bounds[3]-bounds[2])
    columns=columns if periodic else math.ceil(width/pitch)+3
    rows=math.ceil(height/step_v)+3
    if rows*columns>MAX_CANDIDATES:return None,pitch
    center=((bounds[0]+bounds[1])/2,(bounds[2]+bounds[3])/2)
    offset_u,offset_v=math.remainder(settings.offset_u_mm,pitch),math.remainder(settings.offset_v_mm,step_v)
    result=[]
    for row in range(rows):
        v=(row-(rows-1)/2)*step_v+offset_v
        stagger=pitch/2 if triangular and (row+phase)%2 else 0
        for column in range(columns):
            u=(column-(columns-1)/2)*pitch+stagger+offset_u
            position=((bounds[0]+(column*pitch+stagger+offset_u)%period,center[1]+v) if periodic else
                      (center[0]+u*math.cos(angle)-v*math.sin(angle),center[1]+u*math.sin(angle)+v*math.cos(angle)))
            world=tuple((position[0]+x,position[1]+y) for x,y in polygon)
            clipped=clipping.rectangle(world,bounds,periodic)
            if not clipped:continue
            origin=tuple(sum(p[axis] for p in clipped)/len(clipped) for axis in (0,1))
            result.append(Cell(origin,tuple((x-origin[0],y-origin[1]) for x,y in clipped)))
    return tuple(result),pitch


def _pitch_candidates(settings, bounds, period, max_cells):
    triangular = settings.pattern in ("hexagon", "circle")
    factor = math.sqrt(3)/2 if triangular else 1.0
    width, height = bounds[1]-bounds[0], bounds[3]-bounds[2]
    area = width*height
    # Start near the requested size; a dense selection raises this baseline
    # before constructing any cells, so auto-fit cannot allocate huge grids.
    base = max(settings.pitch_mm, math.sqrt(area/(factor*max_cells))*.85)
    unit = _polygon(replace(settings, pitch_mm=settings.web_mm+1, rotation_deg=0.0))
    unit_u = unit_v = 2*max(math.hypot(u,v) for u,v in unit)*1.05
    projected_u, projected_v = _projected_size(bounds, math.radians(settings.rotation_deg))
    if period is not None:
        projected_u, projected_v = period, height
    values = {settings.pitch_mm, base}
    for ratio in (.85, .9, .95, 1.05, 1.1, 1.15, 1.25, 1.4, 1.6, 2, 4, 8):
        values.add(base*ratio)
    for target in (settings.pitch_mm, base):
        if period is not None:
            approximate = max(3, round(period/target))
            for columns in range(max(3, approximate-3), approximate+4):
                values.add(period/columns)
            values.add(period/3)
        else:
            approximate = max(1, round(projected_u/target))
            for columns in range(max(1, approximate-3), approximate+4):
                values.add((projected_u+settings.web_mm*unit_u)/(columns-1+unit_u))
        approximate = max(1, round(projected_v/(factor*target)))
        for rows in range(max(1, approximate-3), approximate+4):
            values.add((projected_v+settings.web_mm*unit_v)/((rows-1)*factor+unit_v))
    # A narrow but otherwise usable face can require a smaller cell than the
    # normal +/-15% neighborhood. This is still one uniform reported pitch.
    values.add(min((projected_u+settings.web_mm*unit_u)/unit_u,
                   (projected_v+settings.web_mm*unit_v)/unit_v))
    minimum = settings.web_mm+max(1e-6, settings.web_mm*1e-6)
    values = {value for value in values if minimum < value <= 10000 and math.isfinite(value)}
    if period is not None:
        values = {period/max(3, round(period/value)) for value in values}
        values = {value for value in values if minimum < value <= 10000}
    return tuple(sorted(values))


def _layout_score(cells, pitch, requested, bounds, periodic):
    envelope = _center_envelope(cells)
    width, height = bounds[1]-bounds[0], bounds[3]-bounds[2]
    fill_u = 1.0 if periodic else min(1.0, (envelope[1]-envelope[0])/width)
    fill_v = min(1.0, (envelope[3]-envelope[2])/height)
    envelope_fill = fill_u*fill_v
    polygon = cells[0].polygon_mm
    area = abs(sum(a[0]*b[1]-b[0]*a[1]
                   for a,b in zip(polygon, polygon[1:]+polygon[:1])))/2
    opening_fill = min(1.0, sum(clipping.area(cell.polygon_mm) for cell in cells)/(width*height))
    # Coverage and a close requested size both matter; a single huge opening
    # cannot win just because it happens to touch the rectangle's four sides.
    return .8*envelope_fill+.2*opening_fill-.35*abs(math.log(pitch/requested))


def build_layout(settings, bounds, period_u_mm=None, *, max_cells=MAX_FACE_CELLS, accept=None):
    """Resolve a centered bounded lattice without any CAD/host dependency.

    ``accept(cell)`` is optional final trim/curvature acceptance. Pure envelope
    scoring selects at most three proposals BEFORE invoking it; callbacks are
    capped at 3*max_cells, independent of the number of pure pitch candidates.
    The caller still verifies physical web thickness after surface mapping.
    """
    settings.validate()
    mode = getattr(settings, "layout_mode", "fixed")
    if mode == "fixed" and settings.edge_mode=='whole':
        cells = _build_legacy(settings, bounds, period_u_mm)
        if accept is not None:
            if not callable(accept):
                raise ValueError("Pattern trim acceptance must be callable.")
            cells = tuple(cell for cell in cells if accept(cell))
        return Layout(cells, settings.pitch_mm, settings.pitch_mm, "fixed")
    if mode not in ("balanced", "fill", "fit", "fixed"):
        raise ValueError("Choose balanced, fill, fit or fixed pattern layout.")
    if type(max_cells) is not int or not 1 <= max_cells <= MAX_FACE_CELLS:
        raise ValueError("The face budget must be between 1 and 200 cells.")
    if mode == "balanced":
        max_cells = min(max_cells, BALANCED_FACE_CELLS)
    if accept is not None and not callable(accept):
        raise ValueError("Pattern trim acceptance must be callable.")
    periodic = period_u_mm is not None
    if periodic:
        if (not isinstance(period_u_mm, (int,float)) or isinstance(period_u_mm, bool)
                or not math.isfinite(period_u_mm) or period_u_mm <= 0):
            raise ValueError("The wrap period must be finite and positive.")
        symmetry = {"hexagon":60, "square":90, "diamond":90, "slot":180}.get(settings.pattern)
        if symmetry and abs(settings.rotation_deg/symmetry-round(settings.rotation_deg/symmetry)) > 1e-8:
            raise ValueError("A full wrap currently needs rotation in multiples of "+str(symmetry)+" degrees for this shape.")
    available = _fit_bounds(bounds, settings.border_mm, periodic)
    if available is None:
        return Layout((), settings.pitch_mm, settings.pitch_mm, mode)
    if periodic and abs(available[1]-available[0]-period_u_mm) > max(1e-7, period_u_mm*1e-7):
        raise ValueError("The full-wrap chart width must match its period.")
    proposals = []
    dense_count = 0
    candidate_overflow = False
    triangular = settings.pattern in ("hexagon", "circle")
    pitches = (settings.pitch_mm,) if mode in ('fill','fixed') else _pitch_candidates(settings, available, period_u_mm, max_cells)
    if mode=='balanced':
        # Cell size is a user dimension, not a target overridden by the soft
        # budget. Spread centers farther apart instead of enlarging openings.
        pitches=tuple(pitch for pitch in pitches if pitch>=settings.pitch_mm-1e-9)
    for pitch in pitches:
        for phase in ((0,1) if triangular else (0,)):
            cells, actual = _fit_grid(settings, available, pitch, period_u_mm, phase,
                preserve_size=mode in ('balanced','fill','fixed'),spread=mode=='balanced')
            if mode in ('fill','fixed') and (cells is None or len(cells) > max_cells):
                candidate_overflow |= cells is None
                dense_count = max(dense_count, len(cells) if cells is not None else 0)
                continue
            if not cells or len(cells) > max_cells:
                continue
            score = len(cells) if mode == "fill" else _layout_score(cells, actual, settings.pitch_mm, available, periodic)
            proposals.append((score, -abs(math.log(actual/settings.pitch_mm)), len(cells), -phase, actual, cells))
    if not proposals:
        if mode in ('fill','fixed') and (dense_count or candidate_overflow):
            # Refuse, never silently enlarge a fixed-size cell or truncate the grid.
            raise density_error(settings, [(bounds[1]-bounds[0])*(bounds[3]-bounds[2])],
                                face_cells=dense_count,
                                total_cells=MAX_CELLS+1 if dense_count>max_cells and max_cells<MAX_FACE_CELLS else 0,
                                candidates=MAX_CANDIDATES+1 if candidate_overflow else None)
        return Layout((), settings.pitch_mm, settings.pitch_mm, mode)
    proposals.sort(key=lambda proposal: proposal[:4], reverse=True)
    if accept is None:
        best = proposals[0]
        return Layout(best[5], best[4], settings.pitch_mm, mode)
    accepted = []
    cache = {}
    checks = 0
    for proposal in proposals[:FIT_SHORTLIST]:
        cells = []
        for cell in proposal[5]:
            key = (round(proposal[4], 9), *(round(value, 9) for value in cell.center_mm))
            if settings.edge_mode=='clip':key=(proposal[4],cell)
            if key not in cache:
                if checks >= min(FIT_ACCEPT_LIMIT, max_cells*FIT_SHORTLIST):
                    break
                cache[key] = bool(accept(cell))
                checks += 1
            if cache[key]:
                cells.append(cell)
        if cells:
            score = len(cells) if mode == "fill" else _layout_score(tuple(cells), proposal[4], settings.pitch_mm, available, periodic)
            # Prefer a phase that fits the real face instead of two distant
            # isolated clusters with an apparently large envelope.
            score -= .2*(1-len(cells)/len(proposal[5]))
            accepted.append((score, proposal[1], len(cells), proposal[3], proposal[4], tuple(cells)))
    if not accepted:
        return Layout((), settings.pitch_mm, settings.pitch_mm, mode)
    best = max(accepted, key=lambda proposal: proposal[:4])
    return Layout(best[5], best[4], settings.pitch_mm, mode)


def build_cells(settings, bounds, period_u_mm=None):
    """Compatibility tuple API; new adapters should report build_layout pitch."""
    if getattr(settings, "layout_mode", "fixed") == "fixed" and settings.edge_mode=='whole':
        return _build_legacy(settings, bounds, period_u_mm)
    return build_layout(settings, bounds, period_u_mm).cells


def allocate_face_budgets(areas_mm2, *, max_total=MAX_CELLS, max_face=MAX_FACE_CELLS):
    """Deterministic area-weighted integer budgets, capped per face and total."""
    areas = tuple(areas_mm2)
    if (type(max_total) is not int or max_total < 1 or not areas or len(areas) > max_total
            or type(max_face) is not int or not 1 <= max_face <= MAX_FACE_CELLS
            or not all(isinstance(value,(int,float)) and not isinstance(value,bool)
                       and math.isfinite(value) and value > 0 for value in areas)):
        raise ValueError("Provide positive finite face areas within the total pattern budget.")
    allocations = [1]*len(areas)
    remaining = min(max_total, max_face*len(areas))-len(areas)
    while remaining:
        active = [index for index,value in enumerate(allocations) if value < max_face]
        total_area = sum(areas[index] for index in active)
        shares = {index:remaining*areas[index]/total_area for index in active}
        added = 0
        for index in active:
            count = min(max_face-allocations[index], math.floor(shares[index]))
            allocations[index] += count
            added += count
        remaining -= added
        if remaining:
            ranked = sorted((index for index in active if allocations[index] < max_face),
                            key=lambda index: (-(shares[index]-math.floor(shares[index])), index))
            for index in ranked:
                if not remaining:
                    break
                allocations[index] += 1
                remaining -= 1
    return tuple(allocations)
