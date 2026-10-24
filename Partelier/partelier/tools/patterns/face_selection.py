"""Non-modal face selection using Fusion's normal blue selection highlight.

The event only reads native selection. Ctrl add/remove, Orbit and palette Done
remain available; no selectEntity loop, graphics mesh or model edit is needed.
"""

import adsk.core as core
import adsk.fusion as native

from ...diagnostics import emit


class FaceSelection:
    def __init__(self, session):
        self.session = session
        self.ui = core.Application.get().userInterface
        self.body = session.faces[0].body
        self.original = tuple(self.ui.activeSelections.item(i).entity
                              for i in range(self.ui.activeSelections.count))
        self.handler = _Changed(self)
        self.bound = False
        self.setting = False
        self.error = None

    def start(self):
        if self.ui.activeSelectionChanged.add(self.handler) is False:
            raise RuntimeError('Fusion could not listen for face selection.')
        self.bound = True
        try:
            self.setting = True
            entities = core.ObjectCollection.create()
            for face in self.session.faces: entities.add(face)
            self.ui.activeSelections.all = entities
        except Exception:
            self.stop()
            raise
        finally:
            self.setting = False
        self.publish()

    def publish(self):
        session = self.session
        session.phase = 'picking_faces'
        session.message = self.error or (
            f'{len(session.faces)} faces selected in blue. Hold Ctrl to add/remove sides, then click Done in Partelier.')
        session.owner.publish(session)

    def changed(self, selections):
        if self.setting or not self.bound: return
        session = self.session
        session.ensure_design()
        faces = []
        invalid = False
        for selection in selections:
            face = native.BRepFace.cast(selection.entity)
            if face is None or not face.isValid or face.body != self.body:
                invalid = True
                continue
            if face not in faces: faces.append(face)
            if len(faces) > 100:
                self.error = 'Select at most 100 faces. Hold Ctrl to deselect the extra faces.'
                self.publish()
                return
        session.faces = tuple(faces)
        session.preview_revision = None
        self.error = 'Select only faces on the original body. Hold Ctrl to remove other selections.' if invalid else None
        emit('pattern.faces.changed', session_id=session.session_id, count=len(faces), invalid=invalid)
        self.publish()

    def stop(self):
        if self.bound:
            if self.ui.activeSelectionChanged.remove(self.handler) is False:
                raise RuntimeError('Fusion could not detach face selection. Try Cancel again.')
            self.bound = False
        entities = core.ObjectCollection.create()
        for entity in self.original:
            if getattr(entity, 'isValid', False): entities.add(entity)
        self.ui.activeSelections.all = entities


class _Changed(core.ActiveSelectionEventHandler):
    def __init__(self, picker):
        super().__init__()
        self.picker = picker

    def notify(self, args):
        try:
            self.picker.changed(args.currentSelection)
        except Exception as error:
            emit('pattern.faces.error', error=str(error))
            self.picker.error = str(error)
            self.picker.publish()
