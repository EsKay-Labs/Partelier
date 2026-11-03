"""Explicit support placement and positive-volume attachment to two real bodies."""
from dataclasses import replace
import math
from ..patterns import fusion as a
from ..hinge import fusion as h
from ..solid_pair import _resolve,_body


def _unit(v):
    size=math.sqrt(sum(x*x for x in v))
    if size<1e-9:raise ValueError('The attachment direction is degenerate.')
    return tuple(x/size for x in v)


def _cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def selection(design,references):
    core,native=h._api()
    if design.designType!=native.DesignTypes.ParametricDesignType or design.activeComponent!=design.rootComponent:
        raise ValueError('Activate the root of a history-based Design.')
    if not {'face_a','face_b'}<=set(references):raise ValueError('Select mounting Face A and Face B on two existing bodies.')
    faces=tuple(_resolve(design,references[key]) for key in ('face_a','face_b'))
    for face in faces:
        if native.BRepFace.cast(face) is None or face.assemblyContext is not None or core.Plane.cast(face.geometry) is None:
            raise ValueError('Use native planar mounting faces in the root component.')
        _body(face.body,design.rootComponent)
    if faces[0].body==faces[1].body:raise ValueError('Choose two different source bodies.')
    return faces


def placement(design,references,settings):
    core,_=h._api();faces=selection(design,references);face=faces[0]
    ok,normal=face.evaluator.getNormalAtPoint(face.pointOnFace)
    if not ok:raise ValueError('Could not read the mounting face normal.')
    n=_unit(tuple(normal.asArray()))
    edges=[edge for edge in face.edges if core.Line3D.cast(edge.geometry)]
    if 'axis_edge' in references:
        edge=_resolve(design,references['axis_edge'])
        if edge not in edges:raise ValueError('Choose a straight boundary edge on Face A for orientation.')
    elif edges:edge=max(edges,key=lambda e:e.length)
    else:edge=None
    if edge:
        p,q=edge.startVertex.geometry,edge.endVertex.geometry
        u=_unit((q.x-p.x,q.y-p.y,q.z-p.z))
    else:
        guide=(1.,0.,0.) if abs(n[0])<.8 else (0.,1.,0.)
        u=_unit(_cross(guide,n))
    v=_unit(_cross(n,u));theta=math.radians(settings.placement_angle_deg)
    u2=tuple(math.cos(theta)*a+math.sin(theta)*b for a,b in zip(u,v));v2=_cross(n,u2)
    # Bounding-box midpoint projected to the support plane, stable for annular faces.
    lo,hi=face.boundingBox.minPoint,face.boundingBox.maxPoint
    center=tuple((a+b)*5 for a,b in zip(lo.asArray(),hi.asArray()))
    plane=face.pointOnFace;delta=sum((c-p*10)*a for c,p,a in zip(center,plane.asArray(),n))
    center=tuple(c-delta*a for c,a in zip(center,n))
    s=settings
    if s.family in ('clevis','barrel','concealed','pip_hinge'):
        axes=(n,u2,v2)
        mount=(-s.length_mm/2,0,s.height_mm/2) if s.family=='clevis' else (-s.height_mm-s.width_mm,0,s.length_mm/2)
    else:
        axes=(u2,v2,n);mount=(0,s.length_mm/2,0) if s.family in ('slider','dovetail') else (0,0,0)
    origin=tuple(center[i]-sum(mount[j]*axes[j][i] for j in range(3))-s.attachment_overlap_mm*n[i]
                 +s.x_mm*u2[i]+s.y_mm*v2[i]+s.z_mm*n[i] for i in range(3))
    transform=core.Matrix3D.create()
    transform.setWithCoordinateSystem(core.Point3D.create(*(x/10 for x in origin)),*(core.Vector3D.create(*axis) for axis in axes))
    return faces,transform


def prepare(design,settings,record,references):
    from . import fusion, attached_store
    if record is not None:return attached_store.prepare_edit(design,record,settings)
    faces,transform=placement(design,references,settings);core,native=h._api();manager=native.TemporaryBRepManager.get()
    raw=fusion.prepare(design,replace(settings,output_mode='separate',x_mm=0,y_mm=0,z_mm=0,placement_angle_deg=0))
    tools=tuple(a._copy(manager,b) for b in raw.bodies)
    for body in tools:
        if not manager.transform(body,transform):raise ValueError('Could not place the mechanism on Face A.')
    targets=tuple(face.body for face in faces);results=[]
    for index,(target,tool) in enumerate(zip(targets,tools)):
        overlap=manager.copy(tool)
        if not manager.booleanOperation(overlap,manager.copy(target),native.BooleanTypes.IntersectionBooleanType) or not overlap.isValid or not overlap.isSolid or overlap.volume<=1e-9:
            raise ValueError(f'Part {"AB"[index]} does not penetrate its support. Adjust the face, placement, dimensions or Attachment overlap.')
        result=a._copy(manager,target)
        a._boolean(manager,result,a._copy(manager,tool),native.BooleanTypes.UnionBooleanType,'Attachment must remain one solid on its selected body.')
        if float(result.volume)<=float(target.volume)+1e-9:raise ValueError('The mechanism is buried inside the source. Move it outward.')
        results.append(result)
    results.extend(tools[2:])
    for i,body in enumerate(results):
        for other in results[i+1:]:
            witness=a._copy(manager,body);before=float(witness.volume)
            a._boolean(manager,witness,a._copy(manager,other),native.BooleanTypes.DifferenceBooleanType,'Attached parts overlap. Review source bodies and placement.')
            if abs(float(witness.volume)-before)>max(1e-9,before*1e-8):raise ValueError('Attached parts overlap. Leave room for the mechanism between the source bodies.')
    return replace(raw,settings=settings,bodies=tuple(results),references=dict(references),targets=targets,tools=tools,
                   source_signature=tuple(h._body_signature(b) for b in targets),record=None)


def validate(prepared):
    targets=tuple(face.body for face in selection(prepared.design,prepared.references))
    if targets!=prepared.targets or tuple(h._body_signature(b) for b in targets)!=prepared.source_signature:
        raise ValueError('The mounting bodies changed. Refresh the preview.')
