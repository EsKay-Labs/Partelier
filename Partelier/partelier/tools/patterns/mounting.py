"""Four optional supported mounting lands and analytic through/countersunk holes.

Preset head envelopes are from the Böllhoff ISO 10642 catalogue, not a claim
that every M-size head is identical. Custom measured head diameter is supported.
All native mutations target owned temporary solids; no model feature per hole.
"""

from dataclasses import dataclass,replace
import math
import time


SCREWS={'M3':(3.,6.72),'M4':(4.,8.96),'M5':(5.,11.20),'M6':(6.,13.44)}
RIM_MM=1.2
EDGE_MM=.5
MIN_BARREL_MM=.2


def border_for_screw(settings):
    """Resolve the solid perimeter before generating any repeat or native tool.

    A whole head and its material rim must fit between the outer edge and the
    first opening. Retain the user's larger minimum; Off adds no restriction.
    """
    settings.validate()
    if settings.mount_mode=='off':return settings.border_mm
    nominal,head=SCREWS[settings.mount_screw]
    hole=nominal+settings.mount_clearance_mm
    head=(settings.mount_head_mm or head)*(1+settings.mount_head_extra_percent/100)
    if head<=hole+.1:
        raise ValueError('Head diameter must be larger than the through hole. Check Head Ø and Hole allowance.')
    radius=head/2+RIM_MM
    inset=settings.mount_inset_mm or radius+EDGE_MM
    if inset<radius+EDGE_MM-1e-8:
        raise ValueError(f'Mounting centres need at least {radius+EDGE_MM:.2f} mm from the outside edges. Use 0 for Auto.')
    return max(settings.border_mm,inset+radius)


@dataclass(frozen=True)
class MountPlan:
    centers_mm: tuple
    hole_diameter_mm: float
    head_diameter_mm: float
    countersink_depth_mm: float
    land_radius_mm: float
    inset_mm: float
    land_bounds_mm: tuple


def plan(settings,bounds,thickness_mm):
    """Pure dimensions, fit and corner connectivity before native pattern work."""
    settings.validate()
    if settings.mount_mode=='off':raise ValueError('Enable mounting holes first.')
    if (len(bounds)!=4 or not all(math.isfinite(v) for v in (*bounds,thickness_mm))
            or thickness_mm<=0 or bounds[1]<=bounds[0] or bounds[3]<=bounds[2]):
        raise ValueError('Mounting needs finite rectangular plate bounds and thickness.')
    nominal,head=SCREWS[settings.mount_screw]
    hole=nominal+settings.mount_clearance_mm
    head=(settings.mount_head_mm or head)*(1+settings.mount_head_extra_percent/100)
    if head<=hole+.1:
        raise ValueError('Head diameter must be larger than the through hole. Check Head Ø and Hole allowance.')
    depth=(head-hole)/2 if settings.mount_mode=='countersink' else 0.
    if depth+MIN_BARREL_MM>thickness_mm+1e-8:
        raise ValueError(f'The 90° countersink needs plate thickness at least {depth+MIN_BARREL_MM:.2f} mm '
                         f'(current {thickness_mm:.2f} mm). Use Plain, a thicker plate or your measured Head Ø.')
    radius=head/2+RIM_MM
    inset=settings.mount_inset_mm or radius+EDGE_MM
    if inset<radius+EDGE_MM-1e-8:
        raise ValueError(f'Mounting centres need at least {radius+EDGE_MM:.2f} mm from the outside edges. Use 0 for Auto.')
    if settings.border_mm<1:
        raise ValueError('Mounting needs Border at least 1 mm to connect the corner lands.')
    lo,hi,bottom,top=bounds
    if min(hi-lo,top-bottom)-2*inset<2*radius+EDGE_MM:
        required=2*inset+2*radius+EDGE_MM
        raise ValueError(f'Four mounting holes need both plate dimensions at least {required:.2f} mm. Use a smaller screw or a larger plate.')
    centers=tuple((x,z) for x in (lo+inset,hi-inset) for z in (bottom+inset,top-inset))
    span=inset+radius
    lands=tuple((x[0],x[1],z[0],z[1]) for x in ((lo,lo+span),(hi-span,hi))
                for z in ((bottom,bottom+span),(top-span,top)))
    return MountPlan(centers,hole,head,depth,radius,inset,lands)


def apply(prepared,plate,mount):
    from . import fusion as a
    from .prism import prism
    started=time.perf_counter()
    core,native=a._api();manager=native.TemporaryBRepManager.get()
    result=a._copy(manager,prepared.result_body)
    operations=native.BooleanTypes
    def tool(center,low,high,first,last=None):
        one=core.Point3D.create(*(v/10 for v in plate.world(*center,low)))
        two=core.Point3D.create(*(v/10 for v in plate.world(*center,high)))
        shape=manager.createCylinderOrCone(one,first/10,two,(first if last is None else last)/10)
        return a._solid(shape,'Fusion could not create a mounting cylinder or countersink.')
    def boolean(target,other,operation):
        return a._boolean(manager,target,other,operation,'A mounting land or hole disconnected the grille. Increase Border or reduce screw size.')
    def block(bounds,low,high):
        lo,hi,bottom,top=bounds
        return prism(plate.frame,((lo,bottom),(hi,bottom),(hi,top),(lo,top)),low,high)
    # Full corner blocks avoid the thin crescents left when circular clearances
    # meet inclined or chamfered fin ends. All material stays inside the plate.
    restores=0
    if prepared.settings.border_mm+1e-8<mount.inset_mm+mount.land_radius_mm:
        for bounds in mount.land_bounds_mm:
            land=block(bounds,-plate.thickness_mm-.02,.02)
            boolean(land,plate.body,operations.IntersectionBooleanType)
            expected=(bounds[1]-bounds[0])*(bounds[3]-bounds[2])*plate.thickness_mm/1000
            if abs(float(land.volume)-expected)>max(1e-8,expected*1e-7):
                raise ValueError('The mounting land is not fully supported by the original plate.')
            boolean(result,land,operations.UnionBooleanType)
            restores+=1
    if prepared.settings.grille_profile!='flat':
        # Seats stay on the original front plane. Clear fins/frame above the
        # reserved lands so the head can reach that plane from the outside.
        for bounds in mount.land_bounds_mm:
            clear=block(bounds,0,prepared.settings.grille_height_mm+.02)
            boolean(result,clear,operations.DifferenceBooleanType)
    radius=mount.hole_diameter_mm/2
    for center in mount.centers_mm:
        before=float(result.volume)
        boolean(result,tool(center,-plate.thickness_mm-.02,.02,radius),operations.DifferenceBooleanType)
        expected=math.pi*radius**2*plate.thickness_mm/1000
        if mount.countersink_depth_mm:
            depth=mount.countersink_depth_mm;head=mount.head_diameter_mm/2
            boolean(result,tool(center,-depth,.02,radius,head+.02),operations.DifferenceBooleanType)
            expected+=math.pi*depth*(head*head+head*radius-2*radius*radius)/3000
        if abs(before-float(result.volume)-expected)>max(1e-8,expected*1e-6):
            raise ValueError('A mounting hole did not retain its complete bore and head seat.')
    elapsed=(time.perf_counter()-started)*1000
    def reserved(point):
        x,z=plate.local(point)
        return any(lo-.01<=x<=hi+.01 and bottom-.01<=z<=top+.01 for lo,hi,bottom,top in mount.land_bounds_mm)
    samples=tuple(sample for sample in prepared.accepted_samples if not reserved(sample['point_mm']))
    prepared=replace(prepared,result_body=result,accepted_samples=samples,timings={**prepared.timings,
        'mounting_ms':elapsed,'total_ms':prepared.timings.get('total_ms',0)+elapsed,
        'mount_holes':4,'mount_border_restores':restores,'mount_hole_diameter_mm':mount.hole_diameter_mm,
        'mount_head_diameter_mm':mount.head_diameter_mm,'mount_countersink_depth_mm':mount.countersink_depth_mm,
        'mount_inset_mm':mount.inset_mm})
    return prepared
