"""Bounded layouts for polygon mosaics; all proposals remain plain numbers."""

import math

from . import clipping
from .tiles import motif, dimensions, profiles, rotate
from .planner import Cell, Layout, MAX_CANDIDATES, density_error, _fit_bounds, _projected_size
from .auto_fit import DENSITIES, _quality


def _grid(settings,bounds,period,size,spread,phase,prepared):
    unit_u,unit_v,shapes=prepared
    angle=math.radians(settings.rotation_deg)
    if period:
        columns=max(1,math.floor(period/(unit_u*spread)+1e-10))
        spread=period/(columns*unit_u)
    step_u,step_v=unit_u*spread,unit_v*spread
    width,height=_projected_size(bounds,angle)
    if period:width,height=period,bounds[3]-bounds[2]
    columns=columns if period else math.ceil(width/step_u)+4
    rows=math.ceil(height/step_v)+4
    if columns*rows*len(shapes)>MAX_CANDIDATES:return None,None,None
    c,s=math.cos(angle),math.sin(angle)
    center=((bounds[0]+bounds[1])/2,(bounds[2]+bounds[3])/2)
    offset_u=math.remainder(settings.offset_u_mm,step_u)+phase[0]*step_u
    offset_v=math.remainder(settings.offset_v_mm,step_v)+phase[1]*step_v
    templates=[]
    for (x,y),polygon in shapes:
        polygon=rotate(polygon,angle)
        templates.append((x*spread,y*spread,polygon,
            (min(u for u,v in polygon),max(u for u,v in polygon),min(v for u,v in polygon),max(v for u,v in polygon))))
    cells=[]
    for row in range(rows):
        v=(row-(rows-1)/2)*step_v+offset_v
        for column in range(columns):
            u=(column if period else column-(columns-1)/2)*step_u+offset_u
            for tx,ty,polygon,extent in templates:
                x=(u+tx)*c-(v+ty)*s;y=(u+tx)*s+(v+ty)*c
                x=bounds[0]+x%period if period else center[0]+x;y+=center[1]
                lo_u,hi_u,lo_v,hi_v=x+extent[0],x+extent[1],y+extent[2],y+extent[3]
                if hi_v<=bounds[2] or lo_v>=bounds[3] or not period and (hi_u<=bounds[0] or lo_u>=bounds[1]):continue
                inside=lo_v>=bounds[2] and hi_v<=bounds[3] and (period or lo_u>=bounds[0] and hi_u<=bounds[1])
                if settings.edge_mode=='whole':
                    radius=max(math.hypot(a,b) for a,b in polygon)*1.05
                    if y-radius<bounds[2] or y+radius>bounds[3] or not period and (x-radius<bounds[0] or x+radius>bounds[1]):continue
                if inside:
                    cells.append(Cell((x,y),polygon));continue
                if settings.edge_mode=='whole':continue
                clipped=clipping.rectangle(tuple((x+a,y+b) for a,b in polygon),bounds,bool(period))
                if not clipped:continue
                origin=(sum(a for a,b in clipped)/len(clipped),sum(b for a,b in clipped)/len(clipped))
                cells.append(Cell(origin,tuple((a-origin[0],b-origin[1]) for a,b in clipped)))
    return tuple(cells),step_u,size


def build_tiled_layout(settings,bounds,period,max_cells,accept):
    if type(max_cells) is not int or not 1<=max_cells<=200:raise ValueError('The face budget must be between 1 and 200 cells.')
    if accept is not None and not callable(accept):raise ValueError('Pattern trim acceptance must be callable.')
    if period is not None:
        if isinstance(period,bool) or not isinstance(period,(int,float)) or not math.isfinite(period) or period<=0:
            raise ValueError('The wrap period must be finite and positive.')
        if abs((bounds[1]-bounds[0])-period)>max(1e-7,period*1e-7):raise ValueError('The chart width must match the wrap period.')
        if abs(settings.rotation_deg/180-round(settings.rotation_deg/180))>1e-8:
            raise ValueError('Full-wrap polygon mosaics currently need rotation in multiples of 180 degrees.')
    available=_fit_bounds(bounds,settings.border_mm,bool(period))
    if available is None:return Layout((),settings.pitch_mm,settings.pitch_mm,settings.layout_mode)
    auto=settings.layout_mode=='auto';resizing=settings.layout_mode=='fit' or auto and not settings.size_locked
    budget=min(max_cells,DENSITIES[settings.density][1] if auto else 48 if settings.layout_mode=='balanced' else 200)
    width,height=available[1]-available[0],available[3]-available[2]
    area=width*height;value=motif(settings.pattern);ref_width,shrink=dimensions(settings.pattern)
    short=DENSITIES[settings.density][0] if auto else 7
    target=min(budget,max(1,short*short*max(width,height)/min(width,height)))
    desired_scale=math.sqrt(area*len(value.polygons)/(value.width*value.height*target))
    desired_size=max(settings.web_mm,desired_scale*ref_width-settings.web_mm*shrink)
    requested=settings.pitch_mm-settings.web_mm
    if settings.layout_mode=='fit':desired_size=max(requested,desired_size)
    choices=[];seen=set()
    for factor in (1,1.15,1.35,1.65):
        size=desired_size*factor if resizing else requested
        if period and resizing:
            # Circumscribed raw tiles bound normal rotation before sampling.
            raw_radius=max(max(math.hypot(x-sum(a for a,b in p)/len(p),y-sum(b for a,b in p)/len(p)) for x,y in p)
                           for p in value.polygons)
            size=min(size,period*.065*ref_width/raw_radius-settings.web_mm*shrink)
        if size<=0 or size+settings.web_mm>10000:continue
        prepared=profiles(settings.pattern,size,settings.web_mm)
        if not prepared:continue
        unit_u,unit_v,shapes=prepared
        spread=(max(1,math.sqrt(area*len(shapes)/(unit_u*unit_v*target)))*factor
                if not resizing and (auto or settings.layout_mode=='balanced') else 1)
        choice=(size,spread)
        if choice not in seen:choices.append((size,spread,prepared));seen.add(choice)
    proposals=[];evaluated=0;overflow=False;candidate_overflow=False;max_count=0
    for size,spread,prepared in choices:
        reference_area=clipping.area(prepared[2][value.reference][1])
        for phase in ((0,0),(.5,0),(0,.5),(.5,.5)):
            cells,repeat_u,resolved=_grid(settings,available,period,size,spread,phase,prepared);evaluated+=1
            if cells is None or len(cells)>budget:
                overflow=True;candidate_overflow|=cells is None
                max_count=max(max_count,len(cells) if cells is not None else 0)
                continue
            if not cells:continue
            score=len(cells) if settings.layout_mode in ('fill','fixed') else _quality(cells,reference_area,available,period,target)
            proposals.append((score,-len(proposals),resolved,repeat_u,reference_area,cells))
    if not proposals:
        if overflow and settings.layout_mode in ('fill','fixed'):
            raise density_error(settings,[area],face_cells=max_count,candidates=MAX_CANDIDATES+1 if candidate_overflow else None)
        return Layout((),settings.pitch_mm,settings.pitch_mm,settings.layout_mode,None,evaluated)
    proposals.sort(key=lambda p:p[:2],reverse=True)
    checks=0;accepted=[];cache={}
    for p in proposals[:2] if accept is not None else proposals[:1]:
        cells=[];retained=0
        for cell in p[5]:
            if accept is None:weight=1
            else:
                if cell not in cache:cache[cell]=min(1,max(0,float(accept(cell))));checks+=1
                weight=cache[cell]
            if weight:cells.append(cell);retained+=weight
        if not cells:continue
        cells=tuple(cells)
        score=len(cells) if settings.layout_mode in ('fill','fixed') else _quality(cells,p[4],available,period,target)
        score-=.5*(1-retained/len(p[5]))
        accepted.append((score,p[1],p[2],p[3],cells))
    if not accepted:return Layout((),settings.pitch_mm,settings.pitch_mm,settings.layout_mode,None,evaluated,checks)
    best=max(accepted,key=lambda p:p[:2])
    return Layout(best[4],best[2]+settings.web_mm,settings.pitch_mm,settings.layout_mode,best[2],evaluated,checks,best[3])
