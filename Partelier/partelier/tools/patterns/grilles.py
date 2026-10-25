"""Planar grille openings: numeric bands and sheared first-wall cutters."""

from dataclasses import dataclass, replace
import math


GRILLES=('grille_parallel','grille_cross','grille_louver')


def build_layout(settings,bounds,period_u_mm,max_cells,accept):
    from .planner import Cell,Layout,build_layout as common,density_error
    from .clipping import rectangle,area
    if period_u_mm is not None:
        raise ValueError('Grilles currently require planar faces. Use surface Patterns for curved faces.')
    if type(max_cells) is not int or not 1<=max_cells<=200:
        raise ValueError('The grille face budget must be between 1 and 200 openings.')
    if settings.pattern=='grille_cross':
        # Mounting is applied once to the finished grille, not to its internal
        # square-layout settings (which intentionally are not a grille type).
        return common(replace(settings,pattern='square',mount_mode='off'),bounds,None,max_cells=max_cells,accept=accept)
    if (len(bounds)!=4 or not all(math.isfinite(value) for value in bounds)
            or bounds[1]<=bounds[0] or bounds[3]<=bounds[2]):
        raise ValueError('Select a finite planar grille region.')
    low_u,high_u,low_v,high_v=bounds
    b=settings.border_mm
    inner=(low_u+b,high_u-b,low_v+b,high_v-b)
    if inner[1]<=inner[0] or inner[3]<=inner[2]:return Layout((),settings.pitch_mm,settings.pitch_mm,'fill')
    angle=math.radians(settings.rotation_deg)
    c,s=math.cos(angle),math.sin(angle)
    center=((low_u+high_u)/2,(low_v+high_v)/2)
    corners=tuple((u-center[0],v-center[1]) for u in inner[:2] for v in inner[2:])
    low=min(-u*s+v*c for u,v in corners);high=max(-u*s+v*c for u,v in corners)
    pitch=settings.pitch_mm;opening=pitch-settings.web_mm
    # A bounded band count is proven before allocation or trim callbacks.
    count=math.ceil((high-low+opening)/pitch)+2
    if count>max_cells+4:
        raise density_error(settings,[(high_u-low_u)*(high_v-low_v)],face_cells=count)
    radius=math.hypot(high_u-low_u,high_v-low_v)+abs(settings.offset_u_mm)+pitch
    offset=((settings.offset_v_mm+pitch/2)%pitch)-pitch/2
    first=math.floor(low/pitch)-1;last=math.ceil(high/pitch)+1
    cells=[];checks=0
    for row in range(first,last+1):
        v=row*pitch+offset
        polygon=tuple((center[0]+x*c-z*s,center[1]+x*s+z*c)
                      for x,z in ((-radius,v-opening/2),(radius,v-opening/2),
                                  (radius,v+opening/2),(-radius,v+opening/2)))
        polygon=rectangle(polygon,inner)
        if not polygon or area(polygon)<1e-7:continue
        midpoint=tuple(sum(point[i] for point in polygon)/len(polygon) for i in (0,1))
        cell=Cell(midpoint,tuple((u-midpoint[0],w-midpoint[1]) for u,w in polygon))
        checks+=1
        if accept is None or accept(cell):cells.append(cell)
        if len(cells)>max_cells:raise density_error(settings,[(high_u-low_u)*(high_v-low_v)],face_cells=len(cells))
    return Layout(tuple(cells),pitch,pitch,'fill',opening,1,checks)


@dataclass(frozen=True)
class LouverFace:
    inner_points_mm: tuple
    across: tuple


def prepare_louver_face(face,settings):
    """Validate and map one rectangular face once per preparation.

    Tilt is from the inward normal; no protruding fins or unproven curved lofts.
    Cell wall witnesses are checked once in the adapter's existing depth pass.
    """
    from . import fusion as adapter
    from .surfaces import SurfaceMap
    core,native=adapter._api()
    if core.Plane.cast(face.geometry) is None or face.loops.count!=1 or face.edges.count!=4:
        raise ValueError('Louvers currently require one rectangular planar face without holes.')
    chart=SurfaceMap(face)
    lo,hi,bottom,top=chart.bounds
    b=settings.border_mm
    # A rectangular chart is necessary to keep its border at every depth.
    for edge in adapter.hinge._items(face.edges):
        if core.Line3D.cast(edge.geometry) is None:
            raise ValueError('Louvers currently require straight rectangular face boundaries.')
    rectangle=tuple(chart.sample(u,v).point_mm for u,v in ((lo,bottom),(hi,bottom),(hi,top),(lo,top)))
    actual=tuple(vertex.geometry for vertex in adapter.hinge._items(face.vertices))
    if len(actual)!=4 or any(min(math.dist(point,(v.x*10,v.y*10,v.z*10)) for v in actual)>1e-4 for point in rectangle):
        raise ValueError('Align a rectangular planar face with its surface axes before adding louvers.')
    # Tangent across bars in chart UV; project into the right-handed prism frame.
    angle=math.radians(settings.rotation_deg)
    chart_center=chart.sample((lo+hi)/2,(bottom+top)/2)
    across=tuple(-math.sin(angle)*a+math.cos(angle)*v for a,v in zip(chart_center.tangent_u,chart_center.tangent_v))
    inner=tuple(chart.sample(u,v).point_mm for u,v in ((lo+b,bottom+b),(hi-b,bottom+b),(hi-b,top-b),(lo+b,top-b)))
    return LouverFace(inner,across)


def louver_cutter(cell,settings,through_depth,context):
    """Construct one inclined first-wall cutter using a preparation-local face map."""
    from . import fusion as adapter
    from .prism import prism
    _,native=adapter._api()
    depth=through_depth
    frame=adapter.hinge.HingeFrame(cell.center.point_mm,cell.center.tangent_u,
        cell.center.normal,adapter.hinge._cross(cell.center.tangent_u,cell.center.normal))
    slope=math.tan(math.radians(settings.louver_angle_deg))
    shear=(-slope*adapter._dot(context.across,frame.x_axis),-slope*adapter._dot(context.across,frame.z_axis))
    cutter=prism(frame,cell.polygon,-depth,.02,shear_xz_per_y=shear)
    footprint=tuple((adapter._dot(adapter._sub(p,frame.origin_mm),frame.x_axis),
                     adapter._dot(adapter._sub(p,frame.origin_mm),frame.z_axis)) for p in context.inner_points_mm)
    if sum(a[0]*z[1]-z[0]*a[1] for a,z in zip(footprint,footprint[1:]+footprint[:1]))<0:footprint=tuple(reversed(footprint))
    mask=prism(frame,footprint,-depth,.02)
    manager=native.TemporaryBRepManager.get()
    adapter._boolean(manager,cutter,mask,native.BooleanTypes.IntersectionBooleanType,'The louver could not preserve its perimeter border.')
    return cutter
