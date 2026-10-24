"""Exact convex pattern prism; no model/history access and no fallback.

Uses only the installed official BRepBodyDefinition API. A prism is assembled
from shared vertices/line edges and outward planar loops, followed by one
temporary-body creation. Shared topology retains analytic volume and winding.
"""

from dataclasses import dataclass
import math
from numbers import Real
import time


MAX_POLYGON_VERTICES = 128


def _api():
    import adsk.core as core
    import adsk.fusion as native
    return core,native


def _dot(one,two):
    return sum(a*b for a,b in zip(one,two))


def _sub(one,two):
    return tuple(a-b for a,b in zip(one,two))


def _cross(one,two):
    return (one[1]*two[2]-one[2]*two[1],one[2]*two[0]-one[0]*two[2],one[0]*two[1]-one[1]*two[0])


def _finite(values):
    try:
        valid=all(not isinstance(value,bool) and isinstance(value,Real) and math.isfinite(value) for value in values)
    except (TypeError,OverflowError):
        valid=False
    if not valid:
        raise ValueError("Pattern prism coordinates must be finite numbers in millimetres.")


@dataclass(frozen=True)
class PrismPlan:
    points_mm: tuple
    face_loops: tuple
    area_mm2: float
    volume_mm3: float
    center_mm: tuple


def plan_prism(frame,polygon_xz_mm,y_min_mm,y_max_mm,*,shear_xz_per_y=(0.,0.)):
    """Validate an exact strictly convex CCW XZ footprint and closed topology."""
    try:
        origin=tuple(frame.origin_mm)
        axes=tuple(tuple(axis) for axis in (frame.x_axis,frame.y_axis,frame.z_axis))
    except (TypeError,AttributeError) as error:
        raise ValueError("Pattern prism needs a finite orthonormal frame.") from error
    if len(origin)!=3 or any(len(axis)!=3 for axis in axes):
        raise ValueError("Pattern prism needs three-dimensional frame axes.")
    _finite((*origin,*(component for axis in axes for component in axis),y_min_mm,y_max_mm))
    if (any(abs(_dot(axis,axis)-1)>1e-7 for axis in axes)
            or any(abs(_dot(axes[a],axes[b]))>1e-7 for a,b in ((0,1),(0,2),(1,2)))
            or _dot(_cross(axes[0],axes[1]),axes[2])<1-1e-7):
        raise ValueError("Pattern prism needs a right-handed orthonormal frame.")
    if y_max_mm<=y_min_mm:
        raise ValueError("Pattern prism depth must have a positive finite span.")
    try:
        polygon=tuple(tuple(point) for point in polygon_xz_mm)
    except TypeError as error:
        raise ValueError("Pattern prism needs a finite convex polygon.") from error
    if not 3<=len(polygon)<=MAX_POLYGON_VERTICES or any(len(point)!=2 for point in polygon):
        raise ValueError("Pattern prism needs 3 to 128 two-dimensional vertices.")
    _finite(component for point in polygon for component in point)
    translated=tuple((x-polygon[0][0],z-polygon[0][1]) for x,z in polygon)
    twice_area=sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(translated,translated[1:]+translated[:1]))
    span=max(max(p[axis] for p in polygon)-min(p[axis] for p in polygon) for axis in (0,1))
    tolerance=max(1e-14,span*span*1e-12)
    if not math.isfinite(twice_area) or twice_area<=tolerance:
        raise ValueError("Pattern prism footprint must have positive counterclockwise area.")
    # All remaining vertices must lie strictly left of every oriented edge.
    # This rejects concave, crossing, repeated and collinear input vertices.
    for index,(one,two) in enumerate(zip(polygon,polygon[1:]+polygon[:1])):
        dx,dz=two[0]-one[0],two[1]-one[1]
        if math.hypot(dx,dz)<=1e-5:
            raise ValueError("Pattern prism has a collapsed polygon edge.")
        for other,point in enumerate(polygon):
            if other in (index,(index+1)%len(polygon)):
                continue
            if dx*(point[1]-one[1])-dz*(point[0]-one[0])<=tolerance:
                raise ValueError("Pattern prism footprint must be strictly convex without crossing edges.")
    shear=tuple(shear_xz_per_y)
    if len(shear)!=2:raise ValueError("Prism shear needs two finite tangent slopes.")
    _finite(shear)
    if max(abs(value) for value in shear)>2:
        raise ValueError("Prism shear exceeds the supported tilt.")
    def world(x,y,z):
        x+=y*shear[0];z+=y*shear[1]
        return tuple(origin[i]+x*axes[0][i]+y*axes[1][i]+z*axes[2][i] for i in range(3))
    count=len(polygon)
    points=tuple(world(x,y,z) for y in (y_min_mm,y_max_mm) for x,z in polygon)
    _finite(component for point in points for component in point)
    # CCW XZ has normal -Y. Reverse only the upper cap; every side points out.
    faces=(tuple(range(count)),tuple(reversed(range(count,2*count))))+tuple(
        (i,count+i,count+(i+1)%count,(i+1)%count) for i in range(count))
    occurrences={}
    for face in faces:
        for one,two in zip(face,face[1:]+face[:1]):
            key=(min(one,two),max(one,two))
            occurrences.setdefault(key,[]).append(one>two)
    if len(occurrences)!=3*count or any(sorted(directions)!=[False,True] for directions in occurrences.values()):
        raise ValueError("The pattern prism topology does not close with opposed shared edges.")
    volume=twice_area*(y_max_mm-y_min_mm)/2
    # A translated origin keeps the signed-volume proof stable far from zero.
    reference=points[0]
    signed=sum(_dot(_sub(points[face[0]],reference),
                _cross(_sub(points[face[index]],reference),_sub(points[face[index+1]],reference)))/6
        for face in faces for index in range(1,len(face)-1))
    if not math.isfinite(volume) or not math.isfinite(signed) or abs(signed-volume)>max(1e-9,volume*1e-7):
        raise ValueError("The pattern prism has inconsistent outward winding or volume.")
    center=world(sum(x for x,z in polygon)/count,(y_min_mm+y_max_mm)/2,sum(z for x,z in polygon)/count)
    return PrismPlan(points,faces,twice_area/2,volume,center)


def _required(value,message):
    if value is None:
        raise ValueError(message)
    return value


def prism(frame,polygon_xz_mm,y_min_mm,y_max_mm,*,diagnostics=None,shear_xz_per_y=(0.,0.)):
    """Create one temporary prism with full healing; never invoke booleans."""
    started=time.perf_counter()
    plan=plan_prism(frame,polygon_xz_mm,y_min_mm,y_max_mm,shear_xz_per_y=shear_xz_per_y)
    planned=time.perf_counter()
    core,native=_api()
    definition=_required(native.BRepBodyDefinition.create(),"Fusion could not define the direct pattern prism.")
    # Retain Autodesk's full healing for the closed shared-edge definition.
    definition.doFullHealing=True
    points=tuple(_required(core.Point3D.create(*(value/10 for value in point)),
                          "Fusion could not define a prism point.") for point in plan.points_mm)
    vertices=tuple(_required(definition.createVertexDefinition(point),
                             "Fusion could not define a shared prism vertex.") for point in points)
    lump=_required(definition.lumpDefinitions.add(),"Fusion could not define a prism lump.")
    shell=_required(lump.shellDefinitions.add(),"Fusion could not define a prism shell.")
    edges={}
    for indices in plan.face_loops:
        one,two,three=(plan.points_mm[index] for index in indices[:3])
        normal=_cross(_sub(two,one),_sub(three,one))
        length=math.sqrt(_dot(normal,normal))
        plane=_required(core.Plane.create(points[indices[0]],core.Vector3D.create(*(value/length for value in normal))),
                        "Fusion could not define a planar prism face.")
        face=_required(shell.faceDefinitions.add(plane,False),"Fusion could not define a prism face.")
        loop=_required(face.loopDefinitions.add(),"Fusion could not define a prism loop.")
        for first,last in zip(indices,indices[1:]+indices[:1]):
            key=(min(first,last),max(first,last))
            if key not in edges:
                curve=_required(core.Line3D.create(points[key[0]],points[key[1]]),
                                "Fusion could not define a prism edge line.")
                edges[key]=_required(definition.createEdgeDefinitionByCurve(vertices[key[0]],vertices[key[1]],curve),
                                     "Fusion could not define a shared prism edge.")
            _required(loop.bRepCoEdgeDefinitions.add(edges[key],first>last),
                      "Fusion could not define a prism co-edge.")
    defined=time.perf_counter()
    body=definition.createBody()
    created=time.perf_counter()
    outcome=tuple(definition.outcomeInfo)
    if diagnostics is not None:
        diagnostics.update({"backend":"BRepBodyDefinition","full_healing":True,"create_calls":1,
            "vertices":len(vertices),"edges":len(edges),"faces":len(plan.face_loops),"outcome":outcome,
            "plan_ms":(planned-started)*1000,"definition_ms":(defined-planned)*1000,
            "create_ms":(created-defined)*1000})
    if body is None or not body.isValid or not body.isTemporary or not body.isSolid or body.lumps.count!=1:
        raise ValueError("Fusion could not create one closed direct pattern prism. "+str(outcome))
    lump=body.lumps.item(0)
    if lump.shells.count!=1 or lump.shells.item(0).isVoid:
        raise ValueError("The direct pattern prism has an unexpected inner or reversed shell.")
    actual=float(body.volume)
    expected=plan.volume_mm3/1000
    if not math.isfinite(actual) or actual<=0 or abs(actual-expected)>max(1e-10,expected*1e-6):
        raise ValueError("The direct pattern prism volume differs from its analytic polygon volume.")
    if diagnostics is not None:
        diagnostics.update({"expected_volume_mm3":plan.volume_mm3,"volume_mm3":actual*1000,
            "total_ms":(time.perf_counter()-started)*1000})
    return body
