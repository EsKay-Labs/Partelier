"""Bounded dense crossed grids: numerical openings and one perforated prism.

This path is restricted to rectangular planar, constant first-wall regions.
Whole-region volume proofs replace per-opening wall casts; source inputs are
never Boolean targets. Generic surface-pattern budgets are unchanged.
"""

import math
import time
from dataclasses import dataclass

from . import clipping
from .planner import Cell,Layout

MAX_OPENINGS=4096
MAX_TOTAL_OPENINGS=8192
MAX_NATIVE_OPENINGS=4096
MAX_NATIVE_TOTAL=8192
MAX_CANDIDATES=10000
MAX_BANDS=256


@dataclass(frozen=True)
class Grid:
    layout: object
    bands: tuple
    bounds: tuple
    opening_area_mm2: float


def plan(settings,bounds,*,trim_margin_mm=0.0):
    """Match the clipped square lattice's phase without any CAD calls."""
    if settings.pattern!='grille_cross' or settings.edge_mode!='clip':
        raise ValueError('Dense Crossed grid requires clipped openings on rectangular planar faces.')
    if len(bounds)!=4 or not all(math.isfinite(x) for x in bounds):raise ValueError('Select a finite grid face.')
    b=settings.border_mm
    if b<.1:raise ValueError('Dense Crossed grid needs a Border of at least 0.1 mm to keep its frame connected.')
    lo,hi,bottom,top=inner=(bounds[0]+b,bounds[1]-b,bounds[2]+b,bounds[3]-b)
    pitch=settings.pitch_mm;opening=pitch-settings.web_mm
    if hi<=lo or top<=bottom:
        return Grid(Layout((),pitch,pitch,'fill',opening),(),inner,0.0)
    angle=math.radians(settings.rotation_deg);c,s=math.cos(angle),math.sin(angle)
    width=(hi-lo)*abs(c)+(top-bottom)*abs(s)
    height=(hi-lo)*abs(s)+(top-bottom)*abs(c)
    columns,rows=math.ceil(width/pitch)+3,math.ceil(height/pitch)+3
    if rows*columns>MAX_CANDIDATES or rows+columns+2>MAX_BANDS:
        raise ValueError('Crossed grid exceeds its bounded row/column budget. Increase Opening width or Rib width.')
    center=((lo+hi)/2,(bottom+top)/2)
    # Preserve the requested-border phase before applying the native trim guard.
    inner=(lo+trim_margin_mm,hi-trim_margin_mm,bottom+trim_margin_mm,top-trim_margin_mm)
    if inner[1]<=inner[0] or inner[3]<=inner[2]:
        return Grid(Layout((),pitch,pitch,'fill',opening),(),inner,0.0)
    offset=(math.remainder(settings.offset_u_mm,pitch),math.remainder(settings.offset_v_mm,pitch))
    xs=tuple((i-(columns-1)/2)*pitch+offset[0] for i in range(columns))
    ys=tuple((i-(rows-1)/2)*pitch+offset[1] for i in range(rows))
    def polygon(points):
        return clipping.rectangle(tuple((center[0]+x*c-y*s,center[1]+x*s+y*c) for x,y in points),inner)
    cells=[]
    for y in ys:
        for x in xs:
            points=polygon(((x-opening/2,y-opening/2),(x+opening/2,y-opening/2),
                            (x+opening/2,y+opening/2),(x-opening/2,y+opening/2)))
            if not points or clipping.area(points)<1e-7:continue
            origin=tuple(sum(p[i] for p in points)/len(points) for i in (0,1))
            cells.append(Cell(origin,tuple((u-origin[0],v-origin[1]) for u,v in points)))
            if len(cells)>MAX_OPENINGS:
                raise ValueError(f'Crossed grid exceeds {MAX_OPENINGS} openings per face. Increase Opening width or Rib width. Dimensions were not changed.')
    if not cells:raise ValueError('No grid openings fit inside this border.')
    radius=math.hypot(hi-lo,top-bottom)+pitch*2
    bands=[]
    for axis,values in enumerate((xs,ys)):
        for value in values:
            low=value+opening/2;high=low+settings.web_mm
            points=((low,-radius),(high,-radius),(high,radius),(low,radius)) if axis==0 else ((-radius,low),(radius,low),(radius,high),(-radius,high))
            points=polygon(points)
            if points and clipping.area(points)>1e-7:bands.append(points)
    if settings.pattern_fillet_mm:
        from .fillet import profile
        # Validate the real clipped apertures, including border fragments,
        # before copying/querying any source body. Never shrink the radius.
        opened=math.fsum(profile(cell.polygon_mm,settings.pattern_fillet_mm).area_mm2 for cell in cells)
    else:opened=math.fsum(clipping.area(cell.polygon_mm) for cell in cells)
    return Grid(Layout(tuple(cells),pitch,pitch,'fill',opening,1,0),tuple(bands),inner,opened)


def _volume_agrees(actual,expected):
    return math.isfinite(actual) and abs(actual-expected)<=max(1e-8,abs(expected)*1e-8)


def prepare(design,faces,settings,body,signature,tokens,started,*,historical=False):
    from . import fusion as a
    from .grilles import prepare_louver_face
    from .prism import prism
    from .perforated_prism import create as perforated
    core,native=a._api();manager=native.TemporaryBRepManager.get()
    plans=[];total_openings=0
    for face in faces:
        try:
            context=prepare_louver_face(face,settings)
            chart=a.SurfaceMap(face)
            # Use the real circumscribed capsule's side extent, including the
            # SurfaceMap .002 mm allowance, rather than guessing its inset.
            margin=max(y for x,y in clipping.capsule((0,0),(1,0),max(.005,settings.border_mm+.002)))-settings.border_mm
            grid=plan(settings,chart.bounds,trim_margin_mm=margin)
        except ValueError as error:
            raise ValueError('Dense Crossed grid needs rectangular planar faces and a constant-thickness wall. '+str(error)) from error
        if grid.layout.cell_count>MAX_NATIVE_OPENINGS:
            raise ValueError(f'Crossed grid exceeds {MAX_NATIVE_OPENINGS} openings per face. Increase Opening width or Rib width. Dimensions were not changed.')
        total_openings+=grid.layout.cell_count
        if total_openings>min(MAX_TOTAL_OPENINGS,MAX_NATIVE_TOTAL):
            raise ValueError(f'Crossed grid exceeds {min(MAX_TOTAL_OPENINGS,MAX_NATIVE_TOTAL)} openings in total. Select fewer faces or increase Opening width.')
        plans.append((face,context,chart,grid))
    planned=time.perf_counter();result=a._copy(manager,body);layouts=[];masks=[];diagnostics=[]
    a._trace_geometry('grid.begin',faces=len(faces),openings=sum(grid.layout.cell_count for _,_,_,grid in plans))
    expected=float(body.volume);wall_queries=0;rib_count=0
    def boolean(target,tool,operation):
        if manager.booleanOperation(target,tool,operation) is False or not target.isValid or not target.isSolid or target.volume<=0:
            raise ValueError('Fusion could not build the dense grid. Increase Opening width or Rib width.')
        return target
    for index,(face,context,chart,grid) in enumerate(plans):
        if not grid.layout.cells:
            layouts.append(grid.layout)
            continue
        a._trace_geometry('grid.face.begin',face_index=index,openings=grid.layout.cell_count,rib_tools=len(grid.bands))
        lo,hi,bottom,top=grid.bounds
        # All opening loops must be strictly inside the cap's outer loop.
        # This thin surrounding frame replaces identical original material.
        lo-=.01;hi+=.01;bottom-=.01;top+=.01
        origin=chart.sample((lo+hi)/2,(bottom+top)/2)
        frame=a.hinge.HingeFrame(origin.point_mm,origin.tangent_u,origin.normal,a.hinge._cross(origin.tangent_u,origin.normal))
        u0,v0=(lo+hi)/2,(bottom+top)/2
        step_u,step_v=min(1,(hi-lo)/4),min(1,(top-bottom)/4)
        du=tuple(x/step_u for x in a._sub(chart.sample(u0+step_u,v0).point_mm,origin.point_mm))
        dv=tuple(x/step_v for x in a._sub(chart.sample(u0,v0+step_v).point_mm,origin.point_mm))
        if abs(a._dot(du,du)-1)>1e-7 or abs(a._dot(dv,dv)-1)>1e-7 or abs(a._dot(du,dv))>1e-7:
            raise ValueError('Dense Crossed grid requires orthogonal planar surface axes.')
        def local(uv):
            delta=tuple((uv[0]-u0)*x+(uv[1]-v0)*y for x,y in zip(du,dv))
            return (a._dot(delta,frame.x_axis),a._dot(delta,frame.z_axis))
        def footprint(points):
            polygon=tuple(local(p) for p in points)
            if sum(p[0]*q[1]-q[0]*p[1] for p,q in zip(polygon,polygon[1:]+polygon[:1]))<0:polygon=tuple(reversed(polygon))
            return polygon
        def solid(points,inward,outward=0):
            return prism(frame,footprint(points),-inward,outward)
        # Nine rays locate a candidate wall. Exact full-region intersections
        # below must then prove solid material and empty air, including between rays.
        witnesses=[chart.sample(u,v) for u in (lo,(lo+hi)/2,hi) for v in (bottom,(bottom+top)/2,top)]
        depths=[a._wall(design,body,sample.point_mm,origin.normal) for sample in witnesses];wall_queries+=len(depths)
        thickness=depths[0][0]
        if max(d[0] for d in depths)-min(d[0] for d in depths)>.00001:
            raise ValueError('Dense Crossed grid requires a constant-thickness first wall.')
        region=((lo,bottom),(hi,bottom),(hi,top),(lo,top))
        mask=solid(region,thickness)
        material=a._copy(manager,mask)
        boolean(material,body,native.BooleanTypes.IntersectionBooleanType)
        if not _volume_agrees(float(material.volume),float(mask.volume)):
            raise ValueError('The grid region contains an internal void or variable wall. Select a constant-thickness plate.')
        # A thin region strictly beyond the back plane must contain no source.
        air=solid(region,thickness+.02,-thickness-.002)
        air_volume=float(air.volume)
        boolean(air,body,native.BooleanTypes.DifferenceBooleanType)
        if not _volume_agrees(float(air.volume),air_volume):
            raise ValueError('The grid wall has material immediately behind it. Select a constant-thickness plate.')
        for previous in masks:
            overlap=a._copy(manager,mask)
            overlap_volume=float(overlap.volume)
            boolean(overlap,previous,native.BooleanTypes.DifferenceBooleanType)
            if not _volume_agrees(float(overlap.volume),overlap_volume):
                raise ValueError('Selected grid walls overlap at a corner. Increase Border or select fewer faces.')
        masks.append(mask)
        a._trace_geometry('grid.wall_proven',face_index=index,thickness_mm=thickness)
        holes=tuple(footprint(tuple((cell.center_mm[0]+u,cell.center_mm[1]+v) for u,v in cell.polygon_mm)) for cell in grid.layout.cells)
        profiles=()
        if settings.pattern_fillet_mm:
            from .fillet import profile
            from .rounded_prism import create
            profiles=tuple(profile(hole,settings.pattern_fillet_mm) for hole in holes)
            grid_body=create(frame,footprint(region),profiles,-thickness,0)
        else:grid_body=perforated(frame,footprint(region),holes,-thickness,0)
        a._trace_geometry('grid.body_ready',face_index=index)
        boolean(result,mask,native.BooleanTypes.DifferenceBooleanType)
        boolean(result,grid_body,native.BooleanTypes.UnionBooleanType)
        expected-=grid.opening_area_mm2*thickness/1000
        if not _volume_agrees(float(result.volume),expected) or result.lumps.count!=1:
            raise ValueError('The dense grid did not retain the expected connected material. Increase Border or Rib width.')
        layouts.append(grid.layout)
        a._trace_geometry('grid.face.end',face_index=index)
        for cell_index in range(0,grid.layout.cell_count,max(1,grid.layout.cell_count//9)):
            if profiles:
                x,z=profiles[cell_index].interior_point
                point_mm=tuple(p+x*u+z*v for p,u,v in zip(frame.origin_mm,frame.x_axis,frame.z_axis))
                normal=frame.y_axis
            else:
                point=chart.sample(*grid.layout.cells[cell_index].center_mm);point_mm,normal=point.point_mm,point.normal
            diagnostics.append({'face_index':index,'point_mm':point_mm,'normal':normal,
                                'first_exit_mm':thickness,'next_entry_mm':None})
    completed=time.perf_counter()
    prepared=a.PreparedPattern(design,faces,body,settings,result,signature,
        {'source_and_plan_ms':(planned-started)*1000,'temporary_geometry_ms':(completed-planned)*1000,
         'total_ms':(completed-started)*1000,'dense_grid':True,'grid_rib_tools':rib_count,
         'grid_body_creations':len(masks),'grid_wall_queries':wall_queries},
        sum(layout.cell_count for layout in layouts),tokens,accepted_samples=tuple(diagnostics),layouts=tuple(layouts))
    a.validate_sources(prepared,_historical=historical)
    a._trace_geometry('grid.end',openings=prepared.cell_count,rib_tools=rib_count,wall_queries=wall_queries,total_ms=prepared.timings['total_ms'])
    return prepared
