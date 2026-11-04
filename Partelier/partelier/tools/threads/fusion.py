"""Cylindrical source threads and temporary calibration solids, in mm."""
from dataclasses import dataclass, replace
import math,time
from . import geometry,planner
from ..hinge import fusion as h
from ..patterns import fusion as a,display_export
from ..fans import fusion as f,display

@dataclass(frozen=True)
class Prepared:
    design:object
    settings:object
    faces:tuple
    targets:tuple
    tools:tuple
    results:tuple
    source_signature:tuple
    tokens:dict
    timings:dict
    names:tuple=()
    record:object=None
    meshes:tuple=()


def _xyz(p):return (p.x*10,p.y*10,p.z*10)
def _dot(a,b):return sum(x*y for x,y in zip(a,b))
def _sub(a,b):return tuple(x-y for x,y in zip(a,b))
def _unit(v):
    n=math.sqrt(_dot(v,v))
    if n<1e-9:raise ValueError('Cylinder axis is invalid.')
    return tuple(x/n for x in v)
def _point(origin,x,y,z,u,v,w):return tuple(origin[i]+u*x[i]+v*y[i]+w*z[i] for i in range(3))


def cylinder(face):
    core,native=h._api()
    if face is None or not face.isValid or native.BRepFace.cast(face) is None:raise ValueError('Select a cylindrical face.')
    surface=core.Cylinder.cast(face.geometry)
    if surface is None or face.assemblyContext is not None:raise ValueError('Choose a complete native cylindrical face.')
    axis=_unit((surface.axis.x,surface.axis.y,surface.axis.z))
    dominant=max(range(3),key=lambda i:abs(axis[i]))
    if axis[dominant]<0:axis=tuple(-v for v in axis)
    centre=_xyz(surface.origin);radius=surface.radius*10;ends=[]
    for edge in h._items(face.edges):
        circle=core.Circle3D.cast(edge.geometry)
        if circle is not None and abs(edge.length-2*math.pi*circle.radius)<1e-5:
            ends.append(_dot(_sub(_xyz(circle.center),centre),axis))
    if len(ends)!=2 or max(ends)-min(ends)<.1:raise ValueError('Choose a complete cylinder bounded by two circular edges; split or trimmed faces are unsupported.')
    point=_xyz(face.pointOnFace);radial=_sub(_sub(point,centre),tuple(_dot(_sub(point,centre),axis)*v for v in axis))
    ok,normal=face.evaluator.getNormalAtPoint(face.pointOnFace)
    if not ok:raise ValueError('Could not read the cylinder orientation.')
    internal=_dot(radial,(normal.x,normal.y,normal.z))<0
    seed=(1.,0.,0.) if abs(axis[0])<.8 else (0.,1.,0.)
    x=_unit(_sub(seed,tuple(_dot(seed,axis)*v for v in axis)));y=h._cross(axis,x)
    origin=tuple(centre[i]+min(ends)*axis[i] for i in range(3))
    return origin,x,y,axis,radius,max(ends)-min(ends),internal


def fit(settings,face):
    *_,radius,height,internal=cylinder(face)
    expected=settings.mode=='internal'
    if internal!=expected:raise ValueError('Select an internal cylindrical hole.' if expected else 'Select an external cylindrical shaft.')
    if settings.profile=='metric':return settings
    diameter=2*radius+(2*planner.depth(settings)-2*settings.clearance_mm if internal else 0)
    return replace(settings,diameter_mm=round(diameter,6))


def selection(design,faces,s):
    core,native=h._api();h._require_main_thread()
    if design.activeComponent!=design.rootComponent or design.designType!=native.DesignTypes.ParametricDesignType:raise ValueError('Use the root component with history enabled.')
    required=0 if s.mode=='coupon' else 2 if s.mode=='pair' else 1
    if len(faces)!=required:raise ValueError('Select the required cylindrical face'+('s.' if required==2 else '.'))
    targets=[]
    for i,face in enumerate(faces):
        frame=cylinder(face);internal=s.mode=='internal' or s.mode=='pair' and i==1
        if frame[-1]!=internal:raise ValueError('Choose the internal hole for the female thread.' if internal else 'Choose the external cylinder for the male thread.')
        if face.body.parentComponent!=design.rootComponent:raise ValueError('Choose a native body in the root component.')
        a._solid(face.body,'Choose a solid source body.')
        if face.body in targets:raise ValueError('The mating threads need two different bodies.')
        if s.offset_mm+s.length_mm>frame[-2]+.001:raise ValueError('Thread length plus offset exceeds the selected cylindrical face.')
        targets.append(face.body)
    return tuple(targets)


def _transform(manager,body,frame,offset=0):
    core,_=h._api();origin,x,y,z=frame[:4]
    origin=tuple(origin[i]+offset*z[i] for i in range(3));m=core.Matrix3D.create()
    m.setWithCoordinateSystem(core.Point3D.create(*(v/10 for v in origin)),core.Vector3D.create(*x),core.Vector3D.create(*y),core.Vector3D.create(*z))
    if not manager.transform(body,m):raise ValueError('Could not place the thread on the cylinder.')
    return body


def _boolean(manager,body,tool,kind):
    a._boolean(manager,body,tool,kind,'The thread disconnects or consumes the source. Reduce depth/length or increase wall thickness.')
    return body


def prepare(design,faces,s):
    s.validate();started=time.perf_counter();targets=selection(design,faces,s)
    core,native=h._api();manager=native.TemporaryBRepManager.get();cut=native.BooleanTypes.DifferenceBooleanType;union=native.BooleanTypes.UnionBooleanType
    result=[];tools=[];names=[]
    if s.mode=='coupon':
        male=geometry.build(s,internal=False)
        # Flat grip bases start on Z=0; male thread starts above its grip.
        m=core.Matrix3D.create();m.translation=core.Vector3D.create(0,0,s.wall_mm/10)
        if not manager.transform(male,m):raise ValueError('Could not place the coupon thread.')
        base=f._cylinder(manager,core,s.diameter_mm/2+s.wall_mm,0,s.wall_mm+.05)
        _boolean(manager,base,male,union);result.append(base);names.append('Thread coupon · male')
        spacing=s.diameter_mm+2*(s.wall_mm+s.clearance_mm+s.coupon_clearance_step_mm)+5
        for i,c in enumerate((s.clearance_mm-s.coupon_clearance_step_mm,s.clearance_mm,s.clearance_mm+s.coupon_clearance_step_mm),1):
            setting=replace(s,mode="internal",clearance_mm=c)
            tool=geometry.build(setting,internal=True)
            nut=f._cylinder(manager,core,s.diameter_mm/2+c+s.wall_mm,0,s.length_mm)
            _boolean(manager,nut,tool,cut)
            # One/two/three full-height exterior marks identify the clearance
            # after slicing/printing, without cutting into the thread wall.
            radius=s.diameter_mm/2+c+s.wall_mm
            for mark in range(i):
                angle=(mark-(i-1)/2)*1.5/radius
                centre=((radius+.15)*math.cos(angle),(radius+.15)*math.sin(angle))
                tab=f._cylinder(manager,core,.35,0,s.length_mm,centre)
                _boolean(manager,nut,tab,union)
            m=core.Matrix3D.create();m.translation=core.Vector3D.create((i%2)*spacing/10,(i//2)*spacing/10,0)
            if not manager.transform(nut,m):raise ValueError('Could not arrange the coupon.')
            result.append(nut);names.append(f'Thread coupon · radial clearance {c:g} mm')
    else:
        p=planner.plan(s)
        for i,(face,target) in enumerate(zip(faces,targets)):
            frame=cylinder(face);internal=s.mode=='internal' or s.mode=='pair' and i==1
            radius=frame[-3]
            if internal:
                if radius>p.female_minor_radius_mm+.01:raise ValueError('This hole is too large to retain the thread roots. Use a smaller bore or larger nominal diameter.')
                # A complete annular material witness also protects the widened
                # lead-in. A volume comparison detects holes between sample rays.
                radius_outer=p.female_major_radius_mm+s.lead_in_mm+.8
                shell=f._cylinder(manager,core,radius_outer,.01,s.length_mm-.01)
                _boolean(manager,shell,f._cylinder(manager,core,radius_outer-.8,-.1,s.length_mm+.1),cut)
                _transform(manager,shell,frame,s.offset_mm)
                expected=shell.volume;intersection=manager.copy(shell)
                ok=manager.booleanOperation(intersection,manager.copy(target),native.BooleanTypes.IntersectionBooleanType)
                if not ok or not intersection.isValid or not intersection.isSolid or abs(intersection.volume-expected)>max(1e-8,expected*1e-6):
                    raise ValueError('The internal thread and lead-in need at least 0.8 mm of surrounding material. Reduce diameter/lead-in or add wall thickness.')
                tool=geometry.build(s,internal=True)
            else:
                if abs(radius-p.major_radius_mm)>.01:raise ValueError('The nominal diameter must match the selected external cylinder.')
                tool=f._cylinder(manager,core,p.major_radius_mm+.5,0,s.length_mm)
                _boolean(manager,tool,geometry.build(s,internal=False),cut)
            _transform(manager,tool,frame,s.offset_mm)
            body=manager.copy(target);_boolean(manager,body,manager.copy(tool),cut)
            if abs(body.volume-target.volume)<1e-9:raise ValueError('The thread does not intersect the selected cylinder.')
            result.append(body);tools.append(tool)
    return Prepared(design,s,tuple(faces),targets,tuple(tools),tuple(result),tuple(h._body_signature(b) for b in targets),
        {'faces':[f.entityToken for f in faces],'bodies':[b.entityToken for b in targets]},
        {'prepare_ms':(time.perf_counter()-started)*1000},tuple(names))


def validate(p):
    if p.design!=h._api()[0].Application.get().activeProduct:raise ValueError('Return to the thread design.')
    targets=selection(p.design,p.faces,p.settings)
    if targets!=p.targets or tuple(h._body_signature(b) for b in targets)!=p.source_signature:raise ValueError('The source changed. Refresh the thread preview.')


def cache(p):return replace(p,meshes=tuple(display_export.capture(p.design,b,coarse=True) for b in p.results))


def draw(p):
    core,native=h._api();group=None
    try:
        if len(p.meshes)!=len(p.results):raise ValueError('Thread preview mesh is missing.')
        material=p.design.rootComponent.material;default=material.appearance if material is not None else None
        for i,(body,mesh) in enumerate(zip(p.results,p.meshes)):
            appearance=p.targets[i].appearance if i<len(p.targets) else default
            group=display_export.draw(p.design,body,appearance,mesh,group=group,effect=display.material(appearance,core,native))
        return group
    except Exception:
        if group is not None and group.isValid:group.deleteMe()
        raise
