"""Raised grilles built on a flat-backed plate, with supported 45-degree sides."""

from dataclasses import replace
import math
import time
from . import clipping
from . import profile_loft
from .planner import Cell,PatternDensityError,build_layout
from .grille_styles import ANGLED,flow_uv


def chamfer_size(settings):
    if settings.grille_profile!='chamfer':return 0.
    size=settings.grille_chamfer_mm or min(.6,settings.grille_height_mm/2,settings.web_mm/4,settings.border_mm/4)
    if size>=settings.grille_height_mm or 2*size>=settings.web_mm-1e-8:
        raise ValueError('Chamfer size must be smaller than Height and half the Rib width. Reduce Chamfer size or increase Rib width.')
    return size


def prepare(design,faces,settings,body,signature,tokens,started,*,historical=False,plate=None):
    from . import fusion as a
    from .flat_plate import inspect
    if len(faces)!=1 or settings.selection_scope!='faces' or settings.border_mm<.5:
        raise ValueError('Raised grilles need one rectangular plate face and Border at least 0.5 mm. Its back prints on the bed.')
    cap=chamfer_size(settings)
    flat=replace(settings,grille_profile='flat',pattern='grille_parallel' if settings.pattern=='grille_louver' else settings.pattern)
    plate=plate or inspect(design,faces,flat,body)
    chart=plate.chart
    lo,hi,bottom,top=chart.bounds
    origin=chart.sample((lo+hi)/2,(bottom+top)/2)
    frame=plate.frame
    local=plate.local
    def ccw(polygon):
        polygon=tuple(polygon)
        return polygon if sum(p[0]*q[1]-q[0]*p[1] for p,q in zip(polygon,polygon[1:]+polygon[:1]))>0 else tuple(reversed(polygon))
    outer=plate.outer
    _,native=a._api();manager=native.TemporaryBRepManager.get()
    thickness=plate.thickness_mm
    inner=(lo+settings.border_mm,hi-settings.border_mm,bottom+settings.border_mm,top-settings.border_mm)
    if inner[1]<=inner[0] or inner[3]<=inner[2]:
        raise ValueError('Border leaves no grille region. Reduce Border.')
    def clipped(cell):
        return clipping.rectangle(tuple((cell.center_mm[0]+u,cell.center_mm[1]+v) for u,v in cell.polygon_mm),inner)
    # This rectangular plate has an exact numeric inset. Use one closed loop
    # per aperture rather than the general boundary-capsule decomposition,
    # whose touching fragments cannot be separate loops in one cap.
    try:
        layout=build_layout(flat,chart.bounds,period_u_mm=None,max_cells=200,accept=lambda cell:bool(clipped(cell)))
    except PatternDensityError as error:
        raise ValueError('Raised profiles support at most 200 openings. Increase Opening width or Rib width, or use Flat for dense Crossed grid.') from error
    loops=tuple(clipped(cell) for cell in layout.cells)
    if not loops:raise ValueError('No grille openings fit. Reduce Border or Opening width.')
    u0,v0=(lo+hi)/2,(bottom+top)/2
    du=chart.sample(u0+min(1,(hi-lo)/4),v0)
    dv=chart.sample(u0,v0+min(1,(top-bottom)/4))
    tangent_u=tuple(x/min(1,(hi-lo)/4) for x in a._sub(du.point_mm,origin.point_mm))
    tangent_v=tuple(x/min(1,(top-bottom)/4) for x in a._sub(dv.point_mm,origin.point_mm))
    def world(uv):
        return tuple(p+(uv[0]-u0)*u+(uv[1]-v0)*v for p,u,v in zip(origin.point_mm,tangent_u,tangent_v))
    holes=tuple(ccw(local(world(point)) for point in loop) for loop in loops)
    profiles=()
    if settings.pattern_fillet_mm:
        from .fillet import profile,stroke
        # One bounded stroked contour is shared by the base and every loft
        # section. Sheared/capped profiles cannot use cylindrical side faces.
        profiles=tuple(profile(hole,settings.pattern_fillet_mm) for hole in holes)
        holes=tuple(stroke(item,tolerance_mm=.01,max_points=128) for item in profiles)
    cells=[];diagnostics=[]
    for index,loop in enumerate(loops):
        center=tuple(sum(point[i] for point in loop)/len(loop) for i in (0,1))
        cells.append(Cell(center,tuple((u-center[0],v-center[1]) for u,v in loop)))
        if len(diagnostics)<3:
            point_mm=plate.world(*profiles[index].interior_point) if profiles else world(center)
            diagnostics.append({'face_index':0,'point_mm':point_mm,'normal':origin.normal,
                                'first_exit_mm':thickness,'next_entry_mm':None})
    layout=replace(layout,cells=tuple(cells))
    height=settings.grille_height_mm
    shear=math.tan(math.radians(settings.louver_angle_deg)) if settings.pattern in ANGLED else 0.
    slopes=[]
    for loop in loops:
        uv=tuple(sum(p[i] for p in loop)/len(loop) for i in (0,1))
        direction=flow_uv(settings,uv,chart.bounds)
        across=tuple(direction[0]*u+direction[1]*v for u,v in zip(tangent_u,tangent_v))
        slopes.append(tuple(shear*a._dot(across,axis) for axis in (frame.x_axis,frame.z_axis)))
    # Retain a flat reveal around the raised frame. Angled fins need extra
    # room in the frame for their sideways rise; never enlarge the footprint.
    reveal=max(0,min(settings.border_mm/2,settings.border_mm-height*shear-2*cap-.5)) if settings.pattern in ANGLED else max(0,settings.border_mm-min(settings.web_mm,settings.border_mm/2))
    raised_outer=clipping.offset_convex(outer,reveal) if reveal else outer
    def section(z,inset=0):
        boundary=clipping.offset_convex(raised_outer,inset) if inset else raised_outer
        # Freeze the slat shear at the start of the bevel. Its horizontal
        # offset then equals its rise, making EVERY bevel plane 45° to the bed.
        # Continuing the shear here would change the bevel to 0°/63.4° at a
        # 45° slat tilt. Since |shear|<=1 this only removes original material.
        rise=min(z,height-cap) if cap else z
        openings=tuple(tuple((u+rise*slope[0],v+rise*slope[1]) for u,v in (clipping.offset_convex(hole,-inset) if inset else hole)) for hole,slope in zip(holes,slopes))
        return boundary,openings
    # Validate every numeric segment before any expensive preparation or SDK
    # creation. Tilt is measured from the plate normal (0 through 45 degrees).
    # Frames remain inside the original footprint.
    levels=(0.,height-cap,height) if cap else (0.,height)
    plans=[]
    for low,high in zip(levels,levels[1:]):
        lower=section(low);upper=section(high,cap if high==height else 0)
        try:
            plans.append(profile_loft.plan(frame,*lower,*upper,low,high))
        except ValueError as error:
            raise ValueError('Raised profile does not fit. Increase Border/Rib width or reduce Height/Chamfer size. '+str(error)) from error
    from .perforated_prism import create,create_plan
    planned=time.perf_counter()
    result=create(frame,outer,holes,-thickness,0)
    before=float(result.volume)
    for plan in plans:
        addition=create_plan(plan)
        a._boolean(manager,result,addition,native.BooleanTypes.UnionBooleanType,'The raised grille did not join the existing plate.')
    added=math.fsum(plan.volume_mm3 for plan in plans)/1000
    if abs(float(result.volume)-before-added)>max(1e-8,added*1e-7):
        raise ValueError('The raised grille overlaps existing material or did not attach completely.')
    completed=time.perf_counter()
    prepared=a.PreparedPattern(design,faces,body,settings,result,signature,
        {'source_and_plan_ms':(planned-started)*1000,'temporary_geometry_ms':(completed-planned)*1000,
         'total_ms':(completed-started)*1000,'raised_profile':settings.grille_profile,
         'raised_body_creations':1+len(plans),'raised_height_mm':height,'underside_limit_deg':45,
         'chamfer_size_mm':cap,'chamfer_angle_deg':45 if cap else 0,
         'louver_angle_deg':settings.louver_angle_deg if settings.pattern in ANGLED else 0},
        len(holes),tokens,accepted_samples=tuple(diagnostics),layouts=(layout,))
    a.validate_sources(prepared,_historical=historical)
    return prepared
