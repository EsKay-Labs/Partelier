"""True temporary CAD grooves: analytic primitives and helical ruled surfaces."""
import math
from . import planner
from ..threads.geometry import _helix, _cylinder, _api, _need
from ..fans.volute import prism_plan
from ..patterns.perforated_prism import create_plan


def _check(body):
    if body is None or not body.isValid or not body.isSolid or body.lumps.count != 1:
        raise ValueError('The knurling must remain one connected solid. Reduce Depth.')
    return body


def _boolean(manager, body, tool, kind):
    if not manager.booleanOperation(body,tool,kind):
        raise ValueError('Fusion could not combine the CAD grip grooves. Reduce Depth or increase Spacing.')
    return _check(body)


def _rotate(manager, body, angle):
    core,_ = _api()
    transform = core.Matrix3D.create()
    transform.setToRotation(angle,core.Vector3D.create(0,0,1),core.Point3D.create())
    if not manager.transform(body,transform):raise ValueError('Could not orient a grip groove.')
    return body


def _straight(p, depth, height):
    outside = .1
    width = p.half_width_mm*(depth+outside)/depth
    polygon = ((p.root_radius_mm,0.),(p.outer_radius_mm+outside,-width),(p.outer_radius_mm+outside,width))
    return create_plan(prism_plan(polygon,-1.,height+1.))


def _helical(p, depth, height, angle, direction):
    if angle == 0:return _straight(p,depth,height)
    lead = 2*math.pi*p.outer_radius_mm/math.tan(math.radians(angle))
    half = p.half_width_mm/math.tan(math.radians(angle))
    outside = .1
    full_half = half*(depth+outside)/depth
    margin = full_half+1.
    centre = -margin if direction>0 else height+margin
    profile = ((p.root_radius_mm,centre),(p.outer_radius_mm+outside,centre-full_half),(p.outer_radius_mm+outside,centre+full_half))
    body = _helix(profile,direction*lead,(height+2*margin)/lead)
    _,native = _api()
    return _rotate(native.TemporaryBRepManager.get(),body,direction*2*math.pi*centre/lead)


def _ring(manager, p, depth, centre):
    core,native = _api()
    half = p.half_width_mm
    outside = .1
    extent = half*(depth+outside)/depth
    shell = _cylinder(p.outer_radius_mm+outside,centre-extent,centre+extent)
    def cone(low,high,r1,r2):
        return _need(manager.createCylinderOrCone(core.Point3D.create(0,0,low/10),r1/10,core.Point3D.create(0,0,high/10),r2/10))
    lower=cone(centre-extent,centre,p.outer_radius_mm+outside,p.root_radius_mm)
    upper=cone(centre,centre+extent,p.root_radius_mm,p.outer_radius_mm+outside)
    _boolean(manager,lower,upper,native.BooleanTypes.UnionBooleanType)
    return _boolean(manager,shell,lower,native.BooleanTypes.DifferenceBooleanType)


def build(settings, radius_mm, height_mm, seed=None):
    """Full-height retained grip, local Z0..height; caller applies end finishes.

    Borders are handled by the adapter so the same true-CAD motif can cover a
    complete cylinder without mandatory blank bands or hidden fade triangles.
    """
    p=planner.plan(settings,radius_mm,height_mm)
    core,native=_api();manager=native.TemporaryBRepManager.get()
    cut=native.BooleanTypes.DifferenceBooleanType
    result=manager.copy(seed) if seed is not None else _cylinder(p.outer_radius_mm,0,height_mm)
    _check(result)
    phase=math.radians(settings.phase_deg)
    def repeat(tool):
        for i in range(p.repeats):
            copy=_rotate(manager,manager.copy(tool),phase+2*math.pi*i/p.repeats)
            _boolean(manager,result,copy,cut)
    style=settings.style
    if style in ('straight','pyramids'):
        repeat(_straight(p,settings.depth_mm,height_mm))
    elif style in ('diamond','helical'):
        repeat(_helical(p,settings.depth_mm,height_mm,settings.angle_deg,1))
        if style=='diamond' and settings.angle_deg:
            repeat(_helical(p,settings.depth_mm,height_mm,settings.angle_deg,-1))
    elif style=='chevron':
        if not settings.angle_deg:repeat(_straight(p,settings.depth_mm,height_mm))
        else:
            for direction in (1,-1):
                tool=_helical(p,settings.depth_mm,height_mm,settings.angle_deg,direction)
                clip=_cylinder(p.outer_radius_mm+2,0,height_mm/2) if direction==1 else _cylinder(p.outer_radius_mm+2,height_mm/2,height_mm)
                _boolean(manager,tool,clip,native.BooleanTypes.IntersectionBooleanType)
                if direction==-1:
                    shift=height_mm*math.tan(math.radians(settings.angle_deg))/p.outer_radius_mm
                    _rotate(manager,tool,shift)
                repeat(tool)
    elif style in ('flutes','scallops'):
        half=p.effective_pitch_mm*(.22 if style=='flutes' else .39)
        q=(half*half+settings.depth_mm**2)/(2*settings.depth_mm)
        centre=p.outer_radius_mm+q-settings.depth_mm
        tool=_need(manager.createCylinderOrCone(core.Point3D.create(centre/10,0,-.1),q/10,core.Point3D.create(centre/10,0,(height_mm+1)/10),q/10))
        repeat(tool)
    elif style=='dimples':
        q=(p.half_width_mm**2+settings.depth_mm**2)/(2*settings.depth_mm)
        centre=p.outer_radius_mm+q-settings.depth_mm
        for z in p.row_centres_mm:
            tool=_need(manager.createSphere(core.Point3D.create(centre/10,0,z/10),q/10))
            repeat(tool)
    elif style=='waves':
        from .sweep import wave_groove
        repeat(wave_groove(p,settings.depth_mm,height_mm,settings.angle_deg))
    if style in ('rings','pyramids'):
        for z in p.row_centres_mm:
            _boolean(manager,result,_ring(manager,p,settings.depth_mm,z),cut)
    return _check(result)
