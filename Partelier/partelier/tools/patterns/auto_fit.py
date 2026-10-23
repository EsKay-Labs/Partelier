"""Bounded visual layout proposals, using only chart-space numbers.

At most 16 grids are constructed, and only two reach surface acceptance.
No Fusion calls, new dependencies, random search or CAD candidate bodies.
"""

from dataclasses import replace
import math

from . import clipping
from .planner import Layout, _fit_grid, _polygon, _projected_size


MAX_AUTO_PROPOSALS = 16
AUTO_SHORTLIST = 2
DENSITIES = {'sparse': (3, 24), 'balanced': (5, 64), 'dense': (7, 128)}


def _pitches(settings, bounds, period, budget):
    short_count, _ = DENSITIES[settings.density]
    width, height = _projected_size(bounds, math.radians(settings.rotation_deg))
    if period is not None:
        width, height = period, bounds[3]-bounds[2]
    factor = math.sqrt(3)/2 if settings.pattern in ('hexagon','circle') else 1
    target = min(budget, max(1, short_count**2*max(width,height)/min(width,height)/factor))
    # A suggested opening smaller than its solid gap reads as pinholes. Keep
    # that visual floor only for automatic size; explicit dimensions stay exact.
    base = max(settings.web_mm*2, math.sqrt(width*height/(factor*target)))
    if settings.size_locked:
        base = max(base, settings.pitch_mm)
    upper = 10000
    base = min(base, upper)
    unit = _polygon(replace(settings,pitch_mm=settings.web_mm+1))
    extent = (max(x for x,y in unit)-min(x for x,y in unit),
              max(y for x,y in unit)-min(y for x,y in unit))
    edges = set()
    for span, step, shape in ((width,1,extent[0]),(height,factor,extent[1])):
        count = max(1, round(span/(base*step)))
        for n in range(max(1,count-1),count+2):
            edges.add((span+shape*settings.web_mm)/((n-1)*step+shape))
    # Reserve room for a larger grid step if edge clipping adds another row.
    ordered = [base, min(upper,base*1.35)]
    ordered += sorted(edges,key=lambda value:(abs(math.log(value/base)),value))
    candidates = []
    for value in ordered:
        if period is not None:
            columns = math.floor(period/value) if settings.size_locked else max(3,round(period/value))
            if columns<3:continue
            value = period/columns
        minimum = settings.pitch_mm if settings.size_locked else settings.web_mm*2
        if value<minimum-1e-9 or value>upper+1e-9:continue
        # Reject enormous allocations analytically before making any polygons.
        if width*height/(factor*value**2)>budget*1.8:continue
        if all(abs(value-other)>1e-7 for other in candidates):candidates.append(value)
        if len(candidates)==4:break
    return tuple(candidates), target, factor


def _quality(cells, full_area, bounds, period, target):
    """Favor balanced coverage and useful fragments over cut-off slivers."""
    width, height = bounds[1]-bounds[0], bounds[3]-bounds[2]
    areas = [clipping.area(cell.polygon_mm) for cell in cells]
    total = sum(areas)
    if total<=1e-12:return -math.inf
    points = [(cell.center_mm[0]+x,cell.center_mm[1]+y)
              for cell in cells for x,y in cell.polygon_mm]
    low_u, high_u = min(x for x,y in points), max(x for x,y in points)
    low_v, high_v = min(y for x,y in points), max(y for x,y in points)
    fill = (1 if period else min(1,(high_u-low_u)/width))*min(1,(high_v-low_v)/height)
    imbalance = abs((low_v-bounds[2])-(bounds[3]-high_v))/height
    if period is None:
        imbalance += abs((low_u-bounds[0])-(bounds[1]-high_u))/width
    tiny = sum(max(0,.25-area/full_area) for area in areas)/len(cells)
    # A symmetric envelope alone can hide a heavily biased cluster near a hole.
    mass_v = sum(cell.center_mm[1]*area for cell,area in zip(cells,areas))/total
    imbalance += abs(mass_v-(bounds[2]+bounds[3])/2)/height
    if period is None:
        mass_u = sum(cell.center_mm[0]*area for cell,area in zip(cells,areas))/total
        imbalance += abs(mass_u-(bounds[0]+bounds[1])/2)/width
    return .7*fill-1.2*imbalance-1.5*tiny-abs(math.log(len(cells)/target))


def build_auto_layout(settings, bounds, period, max_cells, accept):
    budget = min(max_cells,DENSITIES[settings.density][1])
    pitches, target, factor = _pitches(settings,bounds,period,budget)
    proposals = []
    evaluated = 0
    for pitch in pitches:
        for du,dv in ((0,0),(.5,0),(0,.5),(.5,.5)):
            # A sparse tall cylinder needs wider spacing, rather than a cell
            # spanning too much curvature. Keep its opening below a bounded
            # angular footprint while the lattice can still spread both ways.
            opening = (settings.pitch_mm-settings.web_mm if settings.size_locked else
                       min(pitch-settings.web_mm,period*.105) if period else pitch-settings.web_mm)
            row_pitch = pitch
            if period:
                rows = max(2,budget//round(period/pitch))
                polygon = _polygon(replace(settings,pitch_mm=opening+settings.web_mm))
                extent_v = max(y for x,y in polygon)-min(y for x,y in polygon)
                row_pitch = max(pitch,(bounds[3]-bounds[2]+extent_v)/((rows-1)*factor))
            candidate = replace(settings,pitch_mm=opening+settings.web_mm,offset_u_mm=settings.offset_u_mm+du*pitch,
                                offset_v_mm=settings.offset_v_mm+dv*row_pitch*factor)
            cells, actual = _fit_grid(candidate,bounds,pitch,period,0,
                preserve_size=True,spread=True,row_pitch_mm=row_pitch,fast_clip=True)
            evaluated += 1
            if not cells or len(cells)>budget:continue
            size = opening
            full_area = clipping.area(_polygon(replace(settings,pitch_mm=size+settings.web_mm)))
            score = _quality(cells,full_area,bounds,period,target)
            proposals.append((score,-len(proposals),actual,size,full_area,cells))
    proposals.sort(key=lambda item:item[:2],reverse=True)
    if not proposals:
        return Layout((),settings.pitch_mm,settings.pitch_mm,'auto',None,evaluated)
    if accept is None:
        best = proposals[0]
        return Layout(best[5],best[2],settings.pitch_mm,'auto',best[3],evaluated)
    cache, accepted = {}, []
    for proposal in proposals[:AUTO_SHORTLIST]:
        cells, retained = [], 0.0
        for cell in proposal[5]:
            if cell not in cache:
                result = accept(cell)
                cache[cell] = min(1.0,max(0.0,float(result)))
            if cache[cell]>0:
                cells.append(cell);retained += cache[cell]
        if not cells:continue
        cells = tuple(cells)
        score = _quality(cells,proposal[4],bounds,period,target)
        score -= .5*(1-retained/len(proposal[5]))
        accepted.append((score,proposal[1],proposal[2],proposal[3],cells))
    if not accepted:
        return Layout((),settings.pitch_mm,settings.pitch_mm,'auto',None,evaluated,len(cache))
    best = max(accepted,key=lambda item:item[:2])
    return Layout(best[4],best[2],settings.pitch_mm,'auto',best[3],evaluated,len(cache))
