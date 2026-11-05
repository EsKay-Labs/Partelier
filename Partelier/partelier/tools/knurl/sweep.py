"""Smooth longitudinal NURBS grooves, with shared curves and ruled CAD faces."""
from ..threads.geometry import _api, _need
from . import wave_profile


def _path_curve(point, low, high, pitch, lean, radius):
    """C1 cubic Hermite B-spline of a sinusoidally rotating transverse point.

    The curve is smooth CAD geometry, not a triangulated boundary. Eight cubic
    spans per period bound the wave interpolation while retaining one side face.
    """
    core,_ = _api()
    sections,levels=wave_profile.spans(point,low,high,pitch,lean,radius)
    controls=[sections[0][0]]+[p for section in sections for p in section[1:]]
    knots=[low]*4+[z for z in levels[1:-1] for _ in range(3)]+[high]*4
    return _need(core.NurbsCurve3D.createNonRational([core.Point3D.create(*(v/10 for v in p)) for p in controls],3,knots,False))


def wave_groove(plan, depth, height, angle):
    core,native=_api();manager=native.TemporaryBRepManager.get()
    profile=wave_profile.profile(plan.outer_radius_mm,plan.root_radius_mm,plan.half_width_mm,depth)
    low,high=-.1,height+.1
    curves=[_path_curve(point,low,high,plan.effective_pitch_mm,angle,plan.outer_radius_mm) for point in profile]
    wires=[_need(manager.createWireFromCurves([curve],False)[0]) for curve in curves]
    definition=_need(native.BRepBodyDefinition.create());definition.doFullHealing=True
    shell=_need(_need(definition.lumpDefinitions.add()).shellDefinitions.add())
    starts=[];ends=[]
    for curve in curves:
        ok,a=curve.evaluator.getPointAtParameter(low)
        okay,b=curve.evaluator.getPointAtParameter(high)
        if not ok or not okay:raise ValueError('Could not evaluate the wave endpoints.')
        starts.append(a);ends.append(b)
    sv=[_need(definition.createVertexDefinition(p)) for p in starts]
    ev=[_need(definition.createVertexDefinition(p)) for p in ends]
    paths=[_need(definition.createEdgeDefinitionByCurve(a,b,curve)) for a,b,curve in zip(sv,ev,curves)]
    se=[];ee=[]
    for i in range(3):
        j=(i+1)%3
        se.append(_need(definition.createEdgeDefinitionByCurve(sv[i],sv[j],core.Line3D.create(starts[i],starts[j]))))
        ee.append(_need(definition.createEdgeDefinitionByCurve(ev[i],ev[j],core.Line3D.create(ends[i],ends[j]))))
    def face(surface,reverse,edges):
        boundary=_need(_need(shell.faceDefinitions.add(surface,reverse)).loopDefinitions.add())
        for edge,rev in edges:_need(boundary.bRepCoEdgeDefinitions.add(edge,rev))
    face(core.Plane.create(starts[0],core.Vector3D.create(0,0,-1)),False,[(e,True) for e in reversed(se)])
    face(core.Plane.create(ends[0],core.Vector3D.create(0,0,1)),False,[(e,False) for e in ee])
    parameter=(low+high)/2
    for i in range(3):
        j=(i+1)%3
        body=_need(manager.createRuledSurface(wires[i].wires.item(0),wires[j].wires.item(0)))
        if body.faces.count!=1:raise ValueError('The wave groove has unexpected side topology.')
        surface=body.faces.item(0).geometry
        ok,a=curves[i].evaluator.getPointAtParameter(parameter)
        okay,b=curves[j].evaluator.getPointAtParameter(parameter)
        derivative_ok,tangent=curves[i].evaluator.getFirstDerivative(parameter)
        if not (ok and okay and derivative_ok):raise ValueError('Could not orient the wave groove.')
        point=core.Point3D.create((a.x+b.x)/2,(a.y+b.y)/2,(a.z+b.z)/2)
        edge=(b.x-a.x,b.y-a.y,b.z-a.z);path=(tangent.x,tangent.y,tangent.z)
        expected=(edge[1]*path[2]-edge[2]*path[1],edge[2]*path[0]-edge[0]*path[2],edge[0]*path[1]-edge[1]*path[0])
        normal_ok,normal=surface.evaluator.getNormalAtPoint(point)
        if not normal_ok:raise ValueError('Could not evaluate the wave surface normal.')
        reverse=sum(x*y for x,y in zip(expected,(normal.x,normal.y,normal.z)))<0
        face(surface,reverse,[(se[i],False),(paths[j],False),(ee[i],True),(paths[i],True)])
    result=definition.createBody()
    if result is None or not result.isValid or not result.isSolid or result.lumps.count!=1:
        raise ValueError('Could not close the smooth wave groove: '+str(tuple(definition.outcomeInfo)))
    return result
