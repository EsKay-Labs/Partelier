"""One-face tools, owned deltas and opaque cached previews."""
from dataclasses import dataclass,replace
import math,time
from . import planner
from ..details import fusion as d
from ..hinge import fusion as h
from ..patterns import fusion as a,prism,display_export

@dataclass(frozen=True)
class Prepared:
    design: object
    settings: object
    faces: tuple
    targets: tuple
    tools: tuple
    results: tuple
    source_signature: tuple
    tokens: dict
    timings: dict
    record: object=None
    meshes: tuple=()

def selection(design,faces,settings):
    core,native=h._api();h._require_main_thread()
    if design.activeComponent!=design.rootComponent or design.designType!=native.DesignTypes.ParametricDesignType:raise ValueError('Use the root component with history enabled.')
    if len(faces)!=1 or faces[0] is None or not faces[0].isValid or native.BRepFace.cast(faces[0]) is None:raise ValueError('Select one planar face.')
    face=faces[0]
    if face.assemblyContext is not None or core.Plane.cast(face.geometry) is None or face.body.parentComponent!=design.rootComponent:raise ValueError('Select a native planar face in the root component.')
    a._solid(face.body,'Choose a solid body.');return (face.body,)

def frame(face,s):
    core,native=h._api();normal=d._normal(face)
    edges=[e for e in h._items(face.edges) if core.Line3D.cast(e.geometry) is not None]
    if edges:
        edge=max(edges,key=lambda e:e.length);x=d._unit(a._sub(d._xyz(edge.endVertex.geometry),d._xyz(edge.startVertex.geometry)))
    else:
        seed=(1.,0.,0.) if abs(normal[0])<.9 else (0.,1.,0.)
        x=d._unit(tuple(seed[i]-a._dot(seed,normal)*normal[i] for i in range(3)))
    z=h._cross(x,normal);origin=d._xyz(face.boundingBox.minPoint);other=d._xyz(face.boundingBox.maxPoint)
    origin=tuple((o+q)/2 for o,q in zip(origin,other))
    plane_point=d._xyz(face.pointOnFace);distance=a._dot(a._sub(origin,plane_point),normal)
    origin=tuple(o-distance*n for o,n in zip(origin,normal));f=h.HingeFrame(origin,x,normal,z)
    theta=math.radians(s.rotation_deg);cx,sx=math.cos(theta),math.sin(theta)
    x2=tuple(cx*u+sx*v for u,v in zip(x,z));z2=tuple(-sx*u+cx*v for u,v in zip(x,z))
    origin=d.world(f,s.offset_x_mm,s.offset_y_mm,0)
    return h.HingeFrame(origin,x2,normal,z2)

def _text(design,f,s,lo,hi):
    core,native=h._api();root=design.rootComponent;manager=native.TemporaryBRepManager.get();sketch=None;extrude=None
    try:
        sketch=root.sketches.add(root.xYConstructionPlane)
        inputs=sketch.sketchTexts.createInput2(s.text,s.height_mm/10);inputs.fontName=s.font
        extent=max(s.length_mm,s.height_mm*len(s.text)*2)/10
        if not inputs.setAsMultiLine(core.Point3D.create(-extent,-s.height_mm/10,0),core.Point3D.create(extent,s.height_mm/10,0),core.HorizontalAlignments.CenterHorizontalAlignment,core.VerticalAlignments.MiddleVerticalAlignment,0):raise ValueError('Could not position text.')
        text=sketch.sketchTexts.add(inputs)
        ext=root.features.extrudeFeatures.createInput(text,native.FeatureOperations.NewBodyFeatureOperation)
        ext.setDistanceExtent(False,core.ValueInput.createByReal((hi-lo)/10))
        extrude=root.features.extrudeFeatures.add(ext)
        if extrude is None or extrude.bodies.count==0:raise ValueError('This font cannot form closed lettering. Try Arial.')
        matrix=core.Matrix3D.create();origin=d.world(f,0,0,lo)
        matrix.setWithCoordinateSystem(core.Point3D.create(*(v/10 for v in origin)),core.Vector3D.create(*f.x_axis),core.Vector3D.create(*(-v for v in f.z_axis)),core.Vector3D.create(*f.y_axis))
        bodies=[]
        for body in h._items(extrude.bodies):
            copy=manager.copy(body)
            if not manager.transform(copy,matrix):raise ValueError('Could not place text on the face.')
            bodies.append(copy)
        return d._union(manager,bodies)
    finally:
        if extrude is not None and extrude.isValid:extrude.deleteMe()
        if sketch is not None and sketch.isValid:sketch.deleteMe()

def prepare(design,faces,s):
    s.validate();started=time.perf_counter();targets=selection(design,faces,s);body=targets[0]
    core,native=h._api();manager=native.TemporaryBRepManager.get();f=frame(faces[0],s)
    lo,hi=(-.15,s.height_mm if s.kind=='stop' else s.depth_mm) if s.additive else (-s.depth_mm,.02)
    if s.kind=='text':tool=_text(design,f,s,lo,hi)
    elif s.kind=='notch':
        # Centre on the actual rectangular outer edge, yielding a half-round opening.
        base,bounds=d._frame(faces[0]);cx,cy={'top':(0,bounds[3]),'bottom':(0,bounds[2]),'left':(bounds[0],0),'right':(bounds[1],0)}[s.edge_side]
        f=replace(base,origin_mm=d.world(base,cx+s.offset_x_mm,cy+s.offset_y_mm,0))
        tool=d._cylinder(f,(0,0),lo,hi,s.width_mm/2)
    elif s.kind=='keyhole':
        r=s.width_mm/2;q=s.shaft_mm/2;travel=s.length_mm-r-q
        tool=d._union(manager,(d._cylinder(f,(0,-travel/2),lo,hi,r),prism.prism(f,planner.rectangle(-q,q,-travel/2,travel/2),lo,hi),d._cylinder(f,(0,travel/2),lo,hi,q)))
    else:tool=d._union(manager,tuple(prism.prism(f,poly,lo,hi) for poly in planner.polygons(s)))
    if s.additive:
        # Exact planar material slice ensures every separate mark/stop is attached.
        mask=manager.copy(tool);box=body.boundingBox
        span=max(box.maxPoint.distanceTo(box.minPoint)*10+100,100)
        plane_slice=prism.prism(f,planner.rectangle(-span,span,-span,span),-.15,0)
        if not manager.booleanOperation(mask,plane_slice,native.BooleanTypes.IntersectionBooleanType):raise ValueError('Could not inspect detail roots.')
        expected=float(mask.volume);actual=manager.copy(mask)
        if (actual is None or manager.booleanOperation(actual,body,native.BooleanTypes.IntersectionBooleanType) is False
                or not actual.isValid or not actual.isSolid or abs(float(actual.volume)-expected)>max(1e-8,expected*1e-6)):
            raise ValueError('Every raised detail needs material beneath it. Move or reduce the detail.')
    result=a._copy(manager,body)
    a._boolean(manager,result,manager.copy(tool),native.BooleanTypes.UnionBooleanType if s.additive else native.BooleanTypes.DifferenceBooleanType,'The detail splits or disconnects the body. Adjust position or dimensions.')
    if abs(result.volume-body.volume)<1e-9:raise ValueError('The detail does not intersect this face. Adjust its position.')
    return Prepared(design,s,tuple(faces),targets,(tool,),(result,),(h._body_signature(body),),{'faces':[faces[0].entityToken],'bodies':[body.entityToken]},{'prepare_ms':(time.perf_counter()-started)*1000})

def validate(p):
    targets=selection(p.design,p.faces,p.settings)
    if targets!=p.targets or tuple(h._body_signature(b) for b in targets)!=p.source_signature:raise ValueError('The source changed. Refresh preview.')
def cache(p):return replace(p,meshes=tuple(display_export.capture(p.design,b,coarse=True) for b in p.results))
def draw(p):
    body=p.targets[0];appearance=body.appearance
    if appearance is None and body.material is not None:appearance=body.material.appearance
    return display_export.draw(p.design,p.results[0],appearance,p.meshes[0],colour=None if appearance else (175,178,182))
