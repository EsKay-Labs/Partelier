"""Transient helical thread envelopes; no native features or scratch documents."""
import math
from . import planner

def _api():
    import adsk.core as core
    import adsk.fusion as native
    return core,native

def _need(value,message='Fusion could not construct the thread.'):
    if value is None:raise ValueError(message)
    return value

def _helix(profile,pitch,turns):
    """Sweep a CCW radial/axial polygon through shared exact helical edges."""
    core,native=_api();manager=native.TemporaryBRepManager.get()
    definition=_need(native.BRepBodyDefinition.create());definition.doFullHealing=True
    shell=_need(_need(definition.lumpDefinitions.add()).shellDefinitions.add())
    wires=[];curves=[];start=[];end=[]
    angle=2*math.pi*turns
    for r,z in profile:
        wire=_need(manager.createHelixWire(core.Point3D.create(0,0,0),core.Vector3D.create(0,0,1),
            core.Point3D.create(r/10,0,z/10),pitch/10,turns,0))
        if wire.edges.count!=1:raise ValueError('Thread helix has unexpected topology.')
        wires.append(wire);curves.append(wire.edges.item(0).geometry)
        start.append(core.Point3D.create(r/10,0,z/10))
        end.append(core.Point3D.create(r*math.cos(angle)/10,r*math.sin(angle)/10,(z+pitch*turns)/10))
    sv=[_need(definition.createVertexDefinition(p)) for p in start]
    ev=[_need(definition.createVertexDefinition(p)) for p in end]
    he=[_need(definition.createEdgeDefinitionByCurve(a,b,c)) for a,b,c in zip(sv,ev,curves)]
    se=[];ee=[];n=len(profile)
    for i in range(n):
        j=(i+1)%n
        se.append(_need(definition.createEdgeDefinitionByCurve(sv[i],sv[j],core.Line3D.create(start[i],start[j]))))
        ee.append(_need(definition.createEdgeDefinitionByCurve(ev[i],ev[j],core.Line3D.create(end[i],end[j]))))
    def loop(surface,reverse,edges):
        face=_need(shell.faceDefinitions.add(surface,reverse));boundary=_need(face.loopDefinitions.add())
        for edge,rev in edges:_need(boundary.bRepCoEdgeDefinitions.add(edge,rev))
    loop(core.Plane.create(start[0],core.Vector3D.create(0,-1,0)),False,[(e,False) for e in se])
    loop(core.Plane.create(end[0],core.Vector3D.create(-math.sin(angle),math.cos(angle),0)),False,[(e,True) for e in reversed(ee)])
    for i in range(n):
        j=(i+1)%n
        surface_body=_need(manager.createRuledSurface(wires[i].wires.item(0),wires[j].wires.item(0)))
        if surface_body.faces.count!=1:raise ValueError('Thread side has unexpected topology.')
        surface=surface_body.faces.item(0).geometry
        a,b=profile[i],profile[j];r=(a[0]+b[0])/2;z=(a[1]+b[1])/2+pitch*turns/2
        theta=angle/2;dr=b[0]-a[0];dz=b[1]-a[1];h=pitch/(2*math.pi)
        expected=(r*math.cos(theta)*dz-h*dr*math.sin(theta),r*math.sin(theta)*dz+h*dr*math.cos(theta),-r*dr)
        ok,normal=surface.evaluator.getNormalAtPoint(core.Point3D.create(r*math.cos(theta)/10,r*math.sin(theta)/10,z/10))
        if not ok:raise ValueError('Could not orient the helical thread surface.')
        reverse=sum(a*b for a,b in zip(expected,(normal.x,normal.y,normal.z)))<0
        loop(surface,reverse,[(he[i],False),(ee[i],False),(he[j],True),(se[i],True)])
    body=definition.createBody()
    if body is None or not body.isValid or not body.isTemporary or not body.isSolid or body.lumps.count!=1:
        raise ValueError('Could not close the helical thread profile: '+str(tuple(definition.outcomeInfo)))
    return body

def _cylinder(radius,low,high):
    core,native=_api();return _need(native.TemporaryBRepManager.get().createCylinderOrCone(
        core.Point3D.create(0,0,low/10),radius/10,core.Point3D.create(0,0,high/10),radius/10))

def build(s,internal=False):
    """Return full male envelope or radially enlarged female cutter, local Z0..L."""
    core,native=_api();manager=native.TemporaryBRepManager.get();p=planner.plan(s)
    allowance=planner.allowance(s,internal)
    # Start one full turn before and end one beyond the final span, then clip.
    turns=p.turns+2;lead=p.lead_mm
    # Join while caps are beyond the finished span. Joining already trimmed
    # ridges makes their end caps coincide with the core cylinder and can trigger
    # ASM edge-coincidence failures at fractional lengths during Rebuild.
    result=_cylinder(p.minor_radius_mm+allowance,-lead-s.pitch_mm,s.length_mm+lead+s.pitch_mm)
    shifted=[(r+allowance,z-lead) for r,z in p.profile]
    # Overlap below the root without moving any visible flank/profile vertex.
    # Merely shifting the first/last vertices would steepen printable45° flanks.
    inner=p.minor_radius_mm+allowance-.05
    shifted=[(inner,shifted[0][1])]+shifted+[(inner,shifted[-1][1])]
    if s.handedness=='left':shifted=[(r,z+s.length_mm+2*lead) for r,z in shifted];lead=-lead
    thread=_helix(tuple(shifted),lead,turns)
    for index in range(s.starts):
        ridge=manager.copy(thread)
        if index:
            transform=core.Matrix3D.create();transform.setToRotation(2*math.pi*index/s.starts,core.Vector3D.create(0,0,1),core.Point3D.create(0,0,0))
            if not manager.transform(ridge,transform):raise ValueError('Could not place the thread start.')
        if not manager.booleanOperation(result,ridge,native.BooleanTypes.UnionBooleanType):raise ValueError('Could not join the thread ridge.')
    clip=_cylinder(p.major_radius_mm+allowance+1,0,s.length_mm)
    if not manager.booleanOperation(result,clip,native.BooleanTypes.IntersectionBooleanType):raise ValueError('Could not trim the thread ends.')
    # A conical lead-in at both ends eases mating. For the internal cutter, widen
    # the entry instead of shrinking the cavity; never consume the requested gap.
    if s.lead_in_mm:
        chamfer=s.lead_in_mm;R=p.major_radius_mm+allowance
        for bottom in (True,False):
            low,high=(0,chamfer) if bottom else (s.length_mm-chamfer,s.length_mm)
            radii=(R+chamfer,R) if bottom else (R,R+chamfer)
            cone=_need(manager.createCylinderOrCone(core.Point3D.create(0,0,low/10),radii[0]/10,core.Point3D.create(0,0,high/10),radii[1]/10))
            if internal:
                if not manager.booleanOperation(result,cone,native.BooleanTypes.UnionBooleanType):raise ValueError('Could not create thread entry relief.')
            else:
                # Retained external tip radius falls by chamfer at the end.
                retained=(R-chamfer,R) if bottom else (R,R-chamfer)
                cone=_need(manager.createCylinderOrCone(core.Point3D.create(0,0,low/10),retained[0]/10,core.Point3D.create(0,0,high/10),retained[1]/10))
                shell=_cylinder(R+1,low,high)
                if not manager.booleanOperation(shell,cone,native.BooleanTypes.DifferenceBooleanType) or not manager.booleanOperation(result,shell,native.BooleanTypes.DifferenceBooleanType):raise ValueError('Could not create thread lead-in.')
    if not result.isSolid or result.lumps.count!=1:raise ValueError('The thread envelope is not one connected solid.')
    return result
