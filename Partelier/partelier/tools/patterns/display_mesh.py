"""Bounded binary STL display buffers; no Fusion handles or model operations."""

from dataclasses import dataclass
import math
import struct


MAX_TRIANGLES = 200_000
_FACET = struct.Struct('<12fH')


@dataclass(frozen=True)
class DisplayMesh:
    coordinates: tuple
    normals: tuple

    @property
    def triangle_count(self):
        return len(self.coordinates)//9


def read_binary_stl(data):
    """Read centimetre coordinates; smooth shallow joins and retain hard edges."""
    if not isinstance(data, bytes) or len(data)<84:
        raise ValueError('The display export is not a complete binary STL.')
    count=struct.unpack_from('<I',data,80)[0]
    if not 0<count<=MAX_TRIANGLES or len(data)!=84+count*_FACET.size:
        raise ValueError('The display export is incomplete or exceeds its triangle budget.')
    facets=[];corners={}
    for record in _FACET.iter_unpack(memoryview(data)[84:]):
        values=record[3:12]
        if not all(math.isfinite(value) for value in values):
            raise ValueError('The display export contains invalid coordinates.')
        points=tuple(tuple(values[index:index+3]) for index in (0,3,6))
        u=tuple(b-a for a,b in zip(points[0],points[1]));v=tuple(b-a for a,b in zip(points[0],points[2]))
        cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        area=math.sqrt(sum(value*value for value in cross))
        if area<=1e-20:continue
        normal=tuple(value/area for value in cross)
        keys=tuple(tuple(round(value,6) for value in point) for point in points)
        facets.append((points,keys,normal))
        for index,key in enumerate(keys):
            a=tuple(x-y for x,y in zip(points[(index+1)%3],points[index]))
            b=tuple(x-y for x,y in zip(points[(index+2)%3],points[index]))
            angle=math.atan2(area,sum(x*y for x,y in zip(a,b)))
            corners.setdefault(key,[]).append((normal,angle))
    if not facets:raise ValueError('The display export contains no drawable triangles.')
    coordinates=[];normals=[]
    limit=math.cos(math.radians(30))
    for points,keys,normal in facets:
        for point,key in zip(points,keys):
            coordinates.extend(point)
            nearby=[(n,weight) for n,weight in corners[key] if sum(a*b for a,b in zip(n,normal))>=limit]
            averaged=tuple(sum(n[index]*weight for n,weight in nearby) for index in range(3))
            length=math.sqrt(sum(value*value for value in averaged))
            normals.extend(value/length for value in averaged)
    return DisplayMesh(tuple(coordinates),tuple(normals))
