"""Optional read-only placement and planform references."""

import math,hashlib,json
from .fusion import IDENTITY


def _unit(v):
    length=math.hypot(*v)
    if length<1e-9:raise ValueError('Reference axis has zero length.')
    return tuple(x/length for x in v)


def _cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def circle(entity):
    import adsk.core as core
    import adsk.fusion as native
    edge=native.BRepEdge.cast(entity)
    curve=core.Circle3D.cast(edge.geometry) if edge is not None and edge.isValid else None
    if curve is None or edge.assemblyContext is not None or edge.body.parentComponent!=core.Application.get().activeProduct.rootComponent or abs(edge.length-2*math.pi*curve.radius)>1e-5:
        raise ValueError('Pick one complete circular edge in the root component.')
    z=_unit((curve.normal.x,curve.normal.y,curve.normal.z))
    x=_unit(_cross((0,1,0) if abs(z[1])<.9 else (1,0,0),z));y=_cross(z,x)
    return ((tuple(v*10 for v in (curve.center.x,curve.center.y,curve.center.z)),x,y,z),curve.radius*20)


def outline(entity):
    import adsk.core as core
    import adsk.fusion as native
    profile=native.Profile.cast(entity)
    if profile is None or not profile.isValid or profile.profileLoops.count!=1 or profile.parentSketch.parentComponent!=core.Application.get().activeProduct.rootComponent:
        raise ValueError('Pick one closed root-component sketch profile without inner loops.')
    points=[]
    for curve in profile.profileLoops.item(0).profileCurves:
        geometry=curve.geometry;evaluator=geometry.evaluator
        ok,lo,hi=evaluator.getParameterExtents()
        if not ok:raise ValueError('Could not read the sketch outline.')
        ok,stroke=evaluator.getStrokes(lo,hi,.005)
        if not ok:raise ValueError('Could not sample the sketch outline.')
        values=[(p.x*10,p.y*10) for p in stroke]
        if points and math.dist(points[-1],values[-1])<math.dist(points[-1],values[0]):values.reverse()
        points.extend(values if not points else values[1:])
    if len(points)>1 and math.dist(points[0],points[-1])<.001:points.pop()
    if not 4<=len(points)<=256:raise ValueError('Outline needs4–256 sampled points. Simplify its sketch curves.')
    left=min(x for x,y in points);middle=(min(y for x,y in points)+max(y for x,y in points))/2
    return tuple((x-left,y-middle) for x,y in points)


def resolve(design,refs,settings):
    if not isinstance(refs,dict) or not set(refs)<={'circle','outline'}:raise ValueError('Fan references are damaged.')
    placement=IDENTITY;points=();payload={}
    for role,token in refs.items():
        if not isinstance(token,str) or not 0<len(token)<=16384:raise ValueError('Fan reference token is invalid.')
        values=design.findEntityByToken(token)
        if len(values)!=1 or not values[0].isValid:raise ValueError('A fan reference was removed or split. Pick it again.')
        if role=='circle':
            placement,diameter=circle(values[0]);payload['circle']=(placement,diameter)
            if abs(settings.diameter_mm+2*settings.tip_gap_mm-diameter)>.001:
                raise ValueError('Opening diameter or Tip gap changed. Pick the circular opening again to refit the rotor.')
        else:points=outline(values[0]);payload['outline']=points
    if settings.outline_mode=='sketch' and not points:raise ValueError('Pick the custom sketch outline first.')
    signature=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    return placement,points,signature
