"""Finite surface charts with physical trim margins and local curvature guards.

Plane and cylinder charts have constant physical scale; cylinder U is arc
length. Other smooth faces use a local metric chart and exclude singular or
strongly distorted regions rather than silently overlapping cells.
"""

from dataclasses import dataclass
import math


def _xyz(value):
    return (value.x,value.y,value.z)


def _dot(one,two):
    return sum(a*b for a,b in zip(one,two))


def _unit(value):
    length=math.sqrt(_dot(value,value))
    if not math.isfinite(length) or length<1e-10:
        raise ValueError("The surface chart reaches a singularity. Select a smaller face region.")
    return tuple(component/length for component in value)


def _cross(one,two):
    return (one[1]*two[2]-one[2]*two[1],one[2]*two[0]-one[0]*two[2],one[0]*two[1]-one[1]*two[0])


@dataclass(frozen=True)
class SurfaceSample:
    point_mm: tuple
    normal: tuple
    tangent_u: tuple
    tangent_v: tuple


class SurfaceMap:
    def __init__(self, face):
        import adsk.core as core
        self.face=face
        self.evaluator=face.evaluator
        self._core=core
        anomalies=self.evaluator.getParamAnomaly()
        period_u=anomalies[1][0] if anomalies[0] and anomalies[1] else 0
        period_v=anomalies[2][0] if anomalies[0] and len(anomalies)>2 and anomalies[2] else 0
        self._swap=period_v>0 and not period_u>0
        ok, origin=self.evaluator.getParameterAtPoint(face.pointOnFace)
        if not ok:
            raise ValueError("Fusion could not locate the selected surface chart.")
        self._origin=(origin.y,origin.x) if self._swap else (origin.x,origin.y)
        ok, du,dv=self.evaluator.getFirstDerivative(origin)
        if not ok:
            raise ValueError("Fusion could not read the selected surface directions.")
        if self._swap:du,dv=dv,du
        self._scale=(math.sqrt(_dot(_xyz(du),_xyz(du)))*10,
                     math.sqrt(_dot(_xyz(dv),_xyz(dv)))*10)
        if min(self._scale)<1e-7 or not all(math.isfinite(x) for x in self._scale):
            raise ValueError("Select a regular surface region away from poles and singularities.")
        box=self.evaluator.parametricRange()
        self._range=(box.minPoint.x,box.maxPoint.x,box.minPoint.y,box.maxPoint.y)
        if self._swap:self._range=(self._range[2],self._range[3],self._range[0],self._range[1])
        self.bounds=tuple((value-self._origin[axis])*self._scale[axis]
                          for value,axis in zip(self._range,(0,0,1,1)))
        if not all(math.isfinite(value) and abs(value)<1e7 for value in self.bounds):
            raise ValueError("The face has no finite pattern region.")
        self.kind=('plane' if core.Plane.cast(face.geometry) is not None else
                   'cylinder' if core.Cylinder.cast(face.geometry) is not None else 'general')
        self.period_u_mm=None
        period=period_v if self._swap else period_u
        if period>0:
            if abs(self._range[1]-self._range[0]-period)<max(1e-7,period*1e-7):
                self.period_u_mm=period*self._scale[0]
        self._edges=[]
        for index in range(face.edges.count):
            edge=face.edges.item(index)
            if edge.isDegenerate:
                continue
            coedges=[edge.coEdges.item(i) for i in range(edge.coEdges.count)]
            if len(coedges)==2 and all(coedge.loop.face==face for coedge in coedges):
                continue  # A periodic seam is not a real trim boundary.
            self._edges.append(edge)

    def _parameter(self,u,v):
        raw_u=self._origin[0]+u/self._scale[0]
        if self.period_u_mm is not None:
            raw_u=self._range[0]+(raw_u-self._range[0])%(self._range[1]-self._range[0])
        raw_v=self._origin[1]+v/self._scale[1]
        return self._core.Point2D.create(raw_v,raw_u) if self._swap else self._core.Point2D.create(raw_u,raw_v)

    def sample(self,u,v):
        parameter=self._parameter(u,v)
        if not self.evaluator.isParameterOnFace(parameter):
            raise ValueError("Pattern position lies outside the trimmed surface.")
        ok,point=self.evaluator.getPointAtParameter(parameter)
        success,normal=self.evaluator.getNormalAtParameter(parameter)
        derivatives,du,dv=self.evaluator.getFirstDerivative(parameter)
        if not ok or not success or not derivatives:
            raise ValueError("Fusion could not evaluate a regular pattern surface point.")
        normal=_unit(_xyz(normal)); tangent=_unit(_xyz(dv if self._swap else du))
        if abs(_dot(normal,tangent))>1e-5:
            raise ValueError("The surface directions could not be oriented safely.")
        return SurfaceSample(tuple(value*10 for value in _xyz(point)),normal,tangent,_unit(_cross(normal,tangent)))

    def accepts(self,u,v,radius_mm,border_mm):
        try:
            center=self.sample(u,v)
            reserve=radius_mm*1.05
            # Check a surrounding ring, not only the cell's center. Trims,
            # holes, periodic seams and normal rotation all participate.
            for index in range(24):
                angle=2*math.pi*index/24
                parameter=self._parameter(u+reserve*math.cos(angle),v+reserve*math.sin(angle))
                point=self.sample(u+reserve*math.cos(angle),v+reserve*math.sin(angle))
                if _dot(center.normal,point.normal)<.75:
                    return False
                ok,du,dv=self.evaluator.getFirstDerivative(parameter)
                if not ok:return False
                if self._swap:du,dv=dv,du
                lengths=(math.sqrt(_dot(_xyz(du),_xyz(du)))*10,
                         math.sqrt(_dot(_xyz(dv),_xyz(dv)))*10)
                if not ok or any(not .8<length/scale<1.25 for length,scale in zip(lengths,self._scale)):
                    return False
            point=self._core.Point3D.create(*(value/10 for value in center.point_mm))
            measure=self._core.Application.get().measureManager
            for edge in self._edges:
                result=measure.measureMinimumDistance(point,edge)
                if result is None or result.value*10<reserve+border_mm-1e-6:
                    return False
            return True
        except ValueError:
            return False
