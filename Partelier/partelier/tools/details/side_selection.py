"""Additive native edge picking for rectangular lip sides, with explicit Done."""

import math
from types import SimpleNamespace
import adsk.core as core
import adsk.fusion as native
from ..patterns.face_selection import FaceSelection
from . import fusion,store,planner


def side_index(bounds,one,two,tolerance=1e-4):
    """Match a complete projected boundary; orientation and height are irrelevant."""
    corners=planner.rectangle(bounds)
    for index,start in enumerate(corners):
        end=corners[(index+1)%4]
        if ((math.dist(one,start)<=tolerance and math.dist(two,end)<=tolerance)
                or (math.dist(two,start)<=tolerance and math.dist(one,end)<=tolerance)):
            return index
    return None


class SideSelection(FaceSelection):
    def __init__(self,detail):
        self.detail=detail
        if detail.editing:
            with store.input_scope(detail.design,detail.edit_target):
                face=store._resolve(detail.design,detail.edit_target.recipe['sources']['faces'][0])
                self.frame,self.bounds=fusion._frame(face)
            self.targets=detail.edit_target.targets
        else:
            self.frame,self.bounds=fusion._frame(detail.faces[0])
            self.targets=tuple(face.body for face in detail.faces)
        proxy=SimpleNamespace(faces=(),ensure_design=detail.ensure_design)
        super().__init__(proxy)
        # Repicking starts with the saved sides. A newly selected layout starts empty.
        if detail.sides_confirmed:
            edges={}
            for body in self.targets:
                for edge in fusion.h._items(body.edges):
                    index=self.index(edge)
                    if index is not None and detail.settings.lip_sides&(1<<index):edges[index]=edge
            proxy.faces=tuple(edges[i] for i in sorted(edges))

    def index(self,entity):
        edge=native.BRepEdge.cast(entity)
        if edge is None or not edge.isValid or edge.body not in self.targets or core.Line3D.cast(edge.geometry) is None:return None
        return side_index(self.bounds,*(fusion._local(self.frame,fusion._xyz(v.geometry)) for v in (edge.startVertex,edge.endVertex)))

    def changed(self,selections):
        if self.setting or not self.bound or not self.ready:return
        self.detail.ensure_design()
        edges={self.index(e):e for e in self.session.faces}
        incoming={};invalid=False
        for selection in selections:
            index=self.index(selection.entity)
            if index is None:invalid=True
            else:incoming[index]=selection.entity;edges[index]=selection.entity
        edges.pop(None,None)
        self.session.faces=tuple(edges[i] for i in sorted(edges))
        self.error='Select a complete straight outer edge of face A, or its matching edge on lid B.' if invalid else None
        if invalid or set(incoming)!=set(edges):self.request_paint()
        self.publish()

    @property
    def mask(self):
        return sum(1<<self.index(edge) for edge in self.session.faces)

    def publish(self):
        detail=self.detail
        detail.phase='picking_sides';detail.picking_target='lip_sides'
        detail.message=self.error or ('Activating Fusion side selection…' if not self.ready else
            f'{len(self.session.faces)} sides selected in blue. Click edges to add sides, then Done. Esc clears sides.')
        detail.owner.publish(detail)

    def clear(self):
        self.session.faces=();self.error=None;self.request_paint();self.publish()
