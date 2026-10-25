"""One fully healed planar prism with shared edges and multiple cap loops.

Convex holes are disjoint and strictly inside the convex outer boundary.
No native Boolean per hole and no model/history entities are created.
"""

from dataclasses import dataclass
import math
from . import prism as simple
from . import clipping


@dataclass(frozen=True)
class Plan:
    points_mm: tuple
    faces: tuple
    volume_mm3: float


def plan(frame,outer,holes,low,high):
    outer=tuple(outer);holes=tuple(tuple(hole) for hole in holes)
    if not 1<=len(holes)<=4096:raise ValueError('Provide 1 to 4096 separated grid openings.')
    base=simple.plan_prism(frame,outer,low,high)
    boxes=[];parts=[]
    for hole in holes:
        part=simple.plan_prism(frame,hole,low,high)
        for point in hole:
            for one,two in zip(outer,outer[1:]+outer[:1]):
                distance=((two[0]-one[0])*(point[1]-one[1])-(two[1]-one[1])*(point[0]-one[0]))/math.dist(one,two)
                if distance<.0001:raise ValueError('Grid openings must lie strictly inside the frame.')
        parts.append(part);boxes.append(clipping.bounds(hole))
    # Bounded sweep rejects overlapping/touching loops before entering the SDK.
    active=[];checks=0
    for index in sorted(range(len(holes)),key=lambda i:boxes[i][0][0]):
        box=boxes[index];active=[i for i in active if boxes[i][0][1]>=box[0][0]-1e-6]
        for previous in active:
            other=boxes[previous]
            if other[1][1]<box[1][0]-1e-6 or box[1][1]<other[1][0]-1e-6:continue
            checks+=1
            if checks>250000:raise ValueError('Too many neighboring grid loops. Increase Rib width.')
            # Convex separating-axis theorem, with a strict gap at each loop.
            separated=False
            for polygon in (holes[index],holes[previous]):
                for a,b in zip(polygon,polygon[1:]+polygon[:1]):
                    normal=(-(b[1]-a[1]),b[0]-a[0]);length=math.dist(a,b)
                    spans=[(min(x*normal[0]+y*normal[1] for x,y in value),max(x*normal[0]+y*normal[1] for x,y in value)) for value in (holes[index],holes[previous])]
                    if min(spans[0][1],spans[1][1])-max(spans[0][0],spans[1][0]) < -1e-6*length:
                        separated=True;break
                if separated:break
            if not separated:raise ValueError('Grid opening loops overlap or touch. Increase Rib width.')
        active.append(index)
    points=list(base.points_mm)
    faces=[[base.face_loops[0]],[base.face_loops[1]]]+[[loop] for loop in base.face_loops[2:]]
    for part in parts:
        offset=len(points);points.extend(part.points_mm)
        loops=[tuple(offset+i for i in reversed(loop)) for loop in part.face_loops]
        faces[0].append(loops[0]);faces[1].append(loops[1])
        faces.extend([loop] for loop in loops[2:])
    volume=base.volume_mm3-math.fsum(part.volume_mm3 for part in parts)
    if volume<=0:raise ValueError('Grid openings leave no frame material.')
    edges={}
    for face in faces:
        for loop in face:
            for one,two in zip(loop,loop[1:]+loop[:1]):edges.setdefault(tuple(sorted((one,two))),[]).append(one>two)
    if any(sorted(directions)!=[False,True] for directions in edges.values()):
        raise ValueError('The perforated prism does not close with opposed shared edges.')
    return Plan(tuple(points),tuple(tuple(face) for face in faces),volume)


def create(frame,outer,holes,low,high):
    geometry=plan(frame,outer,holes,low,high)
    return create_plan(geometry)


def create_plan(geometry):
    """Create a previously validated closed multi-loop planar solid."""
    core,native=simple._api();require=simple._required
    definition=require(native.BRepBodyDefinition.create(),'Fusion could not define the grid body.')
    definition.doFullHealing=True
    points=tuple(core.Point3D.create(*(v/10 for v in p)) for p in geometry.points_mm)
    vertices=tuple(require(definition.createVertexDefinition(p),'Fusion could not define a grid vertex.') for p in points)
    shell=require(require(definition.lumpDefinitions.add(),'Fusion could not define a grid lump.').shellDefinitions.add(),'Fusion could not define a grid shell.')
    edges={}
    for loops in geometry.faces:
        indices=loops[0];a,b,c=(geometry.points_mm[i] for i in indices[:3])
        normal=simple._cross(simple._sub(b,a),simple._sub(c,a));length=math.sqrt(simple._dot(normal,normal))
        plane=core.Plane.create(points[indices[0]],core.Vector3D.create(*(v/length for v in normal)))
        face=require(shell.faceDefinitions.add(plane,False),'Fusion could not define a grid face.')
        for indices in loops:
            loop=require(face.loopDefinitions.add(),'Fusion could not define a grid face loop.')
            for one,two in zip(indices,indices[1:]+indices[:1]):
                key=tuple(sorted((one,two)))
                if key not in edges:
                    edges[key]=require(definition.createEdgeDefinitionByCurve(vertices[key[0]],vertices[key[1]],core.Line3D.create(points[key[0]],points[key[1]])),'Fusion could not define a grid edge.')
                require(loop.bRepCoEdgeDefinitions.add(edges[key],one>two),'Fusion could not define a grid co-edge.')
    body=definition.createBody()
    expected=geometry.volume_mm3/1000
    if body is None or not body.isValid or not body.isTemporary or not body.isSolid or body.lumps.count!=1:
        raise ValueError('Fusion could not create the closed grid body. '+str(tuple(definition.outcomeInfo)))
    if body.lumps.item(0).shells.count!=1 or body.lumps.item(0).shells.item(0).isVoid:
        raise ValueError('The grid body has an unexpected inner or reversed shell.')
    if abs(float(body.volume)-expected)>max(1e-9,expected*1e-7):raise ValueError('The grid body volume differs from its planned openings.')
    return body
