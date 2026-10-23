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


TRIM_TOLERANCE_MM = .005
MAX_BOUNDARY_POINTS = 100000


def _segment_distance_squared(point, one, two):
    vector = tuple(b-a for a,b in zip(one,two))
    squared = _dot(vector,vector)
    if squared <= 1e-24:
        return sum((p-a)**2 for p,a in zip(point,one))
    fraction = max(0.0,min(1.0,sum((p-a)*v for p,a,v in zip(point,one,vector))/squared))
    return sum((p-a-fraction*v)**2 for p,a,v in zip(point,one,vector))


@dataclass(frozen=True)
class _TrimBoundary:
    points_mm: tuple
    tolerance_mm: float
    bounds_mm: tuple

    def distance_mm(self,point_mm):
        """Conservative distance to a finite curve, never its support line."""
        squared = min(_segment_distance_squared(point_mm,one,two)
                      for one,two in zip(self.points_mm,self.points_mm[1:]))
        return max(0.0,math.sqrt(squared)-self.tolerance_mm)

    def clears(self,point_mm,required_mm):
        # Strokes deviate from the bounded curve by at most tolerance_mm.
        # Inflate the refusal radius so approximation cannot reduce a border.
        limit = required_mm+self.tolerance_mm
        if limit <= 0:
            return True
        squared_limit = limit*limit
        bounds_squared = sum(max(low-value,0.0,value-high)**2
            for value,(low,high) in zip(point_mm,self.bounds_mm))
        if bounds_squared >= squared_limit:
            return True
        return all(_segment_distance_squared(point_mm,one,two) >= squared_limit
                   for one,two in zip(self.points_mm,self.points_mm[1:]))


def _boundary_from_edge(edge,core):
    """Cache finite trim endpoints/strokes once; all lengths leave in mm.

    Native point-to-BRepEdge measurement can project onto an unbounded support
    curve. Evaluator parameter extents instead identify the actual trimmed
    edge. Curved strokes carry the documented maximum-deviation allowance.
    """
    evaluator = edge.evaluator
    ok,start,end = evaluator.getParameterExtents()
    if not ok or not all(math.isfinite(value) for value in (start,end)) or end <= start:
        raise ValueError("A pattern trim edge has no finite boundary. Select a regular face region.")
    if core.Line3D.cast(edge.geometry) is not None:
        one,first = evaluator.getPointAtParameter(start)
        two,last = evaluator.getPointAtParameter(end)
        if not one or not two or first is None or last is None:
            raise ValueError("Fusion could not read the finite endpoints of a pattern boundary.")
        values = (first,last)
        tolerance = 0.0
    else:
        ok,values = evaluator.getStrokes(start,end,TRIM_TOLERANCE_MM/10)
        if not ok or values is None or len(values) < 2:
            raise ValueError("Fusion could not bound a curved pattern edge. Select a simpler face region.")
        tolerance = TRIM_TOLERANCE_MM
    if len(values) > MAX_BOUNDARY_POINTS:
        raise ValueError("The pattern trim is too complex. Select a smaller or simpler face region.")
    points = []
    for value in values:
        point = tuple(float(component)*10 for component in _xyz(value))
        if not all(math.isfinite(component) for component in point):
            raise ValueError("Fusion returned a non-finite pattern trim boundary.")
        if not points or sum((a-b)**2 for a,b in zip(point,points[-1])) > 1e-24:
            points.append(point)
    if len(points) < 2:
        raise ValueError("A pattern trim boundary collapsed. Select a regular face region.")
    bounds = tuple((min(point[axis] for point in points),max(point[axis] for point in points))
                   for axis in range(3))
    return _TrimBoundary(tuple(points),tolerance,bounds)


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
        self._boundaries=tuple(_boundary_from_edge(edge,core) for edge in self._edges)
        if sum(len(boundary.points_mm) for boundary in self._boundaries)>MAX_BOUNDARY_POINTS:
            raise ValueError("The selected face has too much trim detail. Select a smaller or simpler face region.")

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
            if any(not boundary.clears(center.point_mm,reserve+border_mm-1e-6)
                   for boundary in self._boundaries):
                return False
            # A plane has constant normal and metric. Its trim-valid center and
            # finite-boundary clearance prove that the entire enclosing disk
            # fits; evaluating the same planar geometry at 24 ring points adds
            # no information. Curved charts retain the complete ring checks.
            if self.kind=='plane' and self._boundaries:
                return True
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
            return True
        except ValueError:
            return False

    def _chart_segments(self):
        if hasattr(self,'_clip_segments'):return self._clip_segments
        from .clipping import offset_convex
        segments=[];regions=[]
        for edge,boundary in zip(self._edges,self._boundaries):
            points=[]
            for world in boundary.points_mm:
                ok,parameter=self.evaluator.getParameterAtPoint(self._core.Point3D.create(*(v/10 for v in world)))
                if not ok:raise ValueError('Fusion could not map a pattern trim for edge-cell clipping.')
                raw=(parameter.y,parameter.x) if self._swap else (parameter.x,parameter.y)
                point=tuple((value-origin)*scale for value,origin,scale in zip(raw,self._origin,self._scale))
                if points and self.period_u_mm:
                    point=(point[0]+round((points[-1][0]-point[0])/self.period_u_mm)*self.period_u_mm,point[1])
                # Collapse collinear chart strokes (e.g. the end rim of a cylinder).
                if len(points)>=2:
                    a,b=points[-2:]
                    cross=(b[0]-a[0])*(point[1]-b[1])-(b[1]-a[1])*(point[0]-b[0])
                    if abs(cross)<=1e-8*max(1,math.dist(a,point)):
                        points.pop()
                points.append(point)
            if not self.period_u_mm and len(points)>3 and math.dist(points[0],points[-1])<1e-5:
                try:
                    loop=offset_convex(tuple(points[:-1]),0)
                except ValueError:
                    loop=()
                if loop:
                    outer=None
                    for index in range(edge.coEdges.count):
                        coedge=edge.coEdges.item(index)
                        if coedge.loop.face==self.face:outer=coedge.loop.isOuter;break
                    if outer is None:
                        centroid=tuple(sum(p[axis] for p in loop)/len(loop) for axis in (0,1))
                        outer=self.evaluator.isParameterOnFace(self._parameter(*centroid))
                    regions.append((loop,not outer,boundary.tolerance_mm))
                    continue
            for a,b in zip(points,points[1:]):
                if math.dist(a,b)<=1e-5:continue
                copies=(0,)
                if self.period_u_mm:
                    p=self.period_u_mm
                    copies=range(math.floor((self.bounds[0]-max(a[0],b[0]))/p),
                                 math.ceil((self.bounds[1]-min(a[0],b[0]))/p)+1)
                for shift in copies:
                    offset=shift*(self.period_u_mm or 0)
                    segments.append(((a[0]+offset,a[1]),(b[0]+offset,b[1]),boundary.tolerance_mm))
        if len(segments)>MAX_BOUNDARY_POINTS:
            raise ValueError('The face trim is too complex for clipped edge cells.')
        self._clip_segments=tuple(segments)
        self._clip_regions=tuple(regions)
        return self._clip_segments

    def clipped_cells(self,cell,border_mm):
        """Convex pieces inside finite trims, including partial edge cells.

        Capsule subtraction keeps a minimum solid rim around every real edge;
        periodic seams are excluded. All returned witnesses are trim-valid.
        """
        from .planner import Cell
        from .clipping import subtract_boundaries,offset_convex,difference,bounds,overlaps,halfplane
        if self.accepts(*cell.center_mm,cell.radius_mm,border_mm):return (cell,)
        polygon=tuple((cell.center_mm[0]+u,cell.center_mm[1]+v) for u,v in cell.polygon_mm)
        # General charts have variable metric; reserve the same conservative
        # scale bound used by the existing chart guards, then verify witnesses.
        border=border_mm*(1.25 if self.kind=='general' else 1)
        segments=self._chart_segments()
        fragments=(polygon,)
        for loop,hole,tolerance in self._clip_regions:
            shifted=offset_convex(loop,(-1 if hole else 1)*(border+tolerance+.002))
            parts=[]
            for fragment in fragments:
                if hole:
                    parts.extend(difference(fragment,shifted) if overlaps(bounds(fragment),bounds(shifted)) else (fragment,))
                elif shifted:
                    clipped=fragment
                    for a,b in zip(shifted,shifted[1:]+shifted[:1]):clipped=halfplane(clipped,a,b)
                    if clipped:parts.append(clipped)
            fragments=tuple(parts)
        fragments=tuple(part for fragment in fragments for part in subtract_boundaries(fragment,segments,border))
        if len(fragments)>96:raise ValueError('Too much curved trim detail in one clipped cell. Reduce cell size.')
        result=[]
        for fragment in fragments:
            origin=tuple(sum(point[axis] for point in fragment)/len(fragment) for axis in (0,1))
            try:
                self.sample(*origin)
            except ValueError:
                continue  # The capsule also separated an OUTSIDE piece.
            witnesses=fragment+tuple(((a[0]+b[0])/2,(a[1]+b[1])/2)
                                    for a,b in zip(fragment,fragment[1:]+fragment[:1]))
            for point in witnesses:
                sample=self.sample(*point)
                if any(not boundary.clears(sample.point_mm,border_mm-1e-6) for boundary in self._boundaries):
                    raise ValueError('The curved trim cannot preserve this border reliably. Increase border or select a simpler surface region.')
                parameter=self._parameter(*point)
                ok,du,dv=self.evaluator.getFirstDerivative(parameter)
                if self._swap:du,dv=dv,du
                if not ok or any(not .8<math.sqrt(_dot(_xyz(vector),_xyz(vector)))*10/scale<1.25
                                 for vector,scale in zip((du,dv),self._scale)):
                    raise ValueError('Surface distortion prevents safe edge-cell clipping.')
            result.append(Cell(origin,tuple((x-origin[0],y-origin[1]) for x,y in fragment)))
        return tuple(result)
