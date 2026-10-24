"""Non-modal face selection using Fusion's normal blue selection highlight.

Normal clicks accumulate faces. Deferred native highlighting keeps the complete
set blue; only palette Done permits preview computation.
"""

import adsk.core as core
import adsk.fusion as native
import uuid

from ...diagnostics import emit


class FaceSelection:
    def __init__(self, session):
        self.session = session
        self.app = core.Application.get()
        self.ui = self.app.userInterface
        self.body = session.faces[0].body if session.faces else None
        self.original = tuple(self.ui.activeSelections.item(i).entity
                              for i in range(self.ui.activeSelections.count))
        self.handler = _Changed(self)
        self.bound = False
        self.setting = False
        self.error = None
        self.ready = False
        self.seeded = False
        self.activation_events = []
        self.seed_event_id = None
        self.seed_handler = None
        self.paint_pending = False

    def start(self):
        # A finished zero-input preview can leave Fusion with no active command.
        # Native selection events only fire while SelectCommand is running.
        previous_command=self.ui.activeCommand
        if previous_command not in ('','SelectCommand'):
            raise ValueError('Finish the active Fusion command before selecting pattern faces.')
        if self.ui.activeSelectionChanged.add(self.handler) is False:
            raise RuntimeError('Fusion could not listen for face selection.')
        self.bound = True
        try:
            self.seed_event_id='sktech_partelier_faces_seed_'+uuid.uuid4().hex
            event=self.app.registerCustomEvent(self.seed_event_id)
            if event is None:raise RuntimeError('Fusion could not queue face selection activation.')
            self.seed_handler=_SeedRequested(self)
            self.bind_activation(event,self.seed_handler)
            if self.ui.activeCommand=='SelectCommand':self.seed()
            else:
                definition=self.ui.commandDefinitions.itemById('SelectCommand')
                if definition is None:raise RuntimeError('Fusion Select is unavailable.')
                # Built-in commands do not reliably expose commandCreated.
                # commandStarting + one main-thread custom event runs seeding
                # after native Select has really become active.
                self.bind_activation(self.ui.commandStarting,_Starting(self))
                if definition.execute() is False:
                    raise RuntimeError('Fusion could not activate face selection. Cancel and try again.')
            emit('pattern.faces.activate',before=previous_command,after=self.ui.activeCommand,ready=self.ready)
        except Exception:
            self.stop()
            raise
        finally:
            self.setting = False
        self.publish()

    def bind_activation(self,event,handler):
        if event.add(handler) is False:raise RuntimeError('Fusion could not initialize face selection.')
        self.activation_events.append((event,handler))

    def seed(self):
        if self.ready or not self.bound:return
        self.setting=True
        try:
            entities=core.ObjectCollection.create()
            for face in self.session.faces:entities.add(face)
            self.seeded=True
            self.ui.activeSelections.all=entities
            self.ready=True
            self.error=None
        finally:self.setting=False
        self.publish()

    def synchronize(self):
        if not self.ready:raise ValueError('Wait for Fusion face selection to activate, or Cancel.')
        selections=self.ui.activeSelections
        values=[selections.item(i) for i in range(selections.count)]
        emit('pattern.faces.sync',count=len(values),active_command=self.ui.activeCommand)
        self.changed(values)

    def publish(self):
        session = self.session
        session.phase = 'picking_faces'
        session.message = self.error or ('Activating Fusion face selection…' if not self.ready else
            f'{len(session.faces)} faces selected in blue. Click sides to add them, then Done. Clear selection starts over.')
        session.owner.publish(session)

    def changed(self, selections):
        if self.setting or not self.bound or not self.ready: return
        session = self.session
        session.ensure_design()
        faces = list(session.faces)
        incoming=[]
        invalid = False
        exceeded = False
        for selection in selections:
            face = native.BRepFace.cast(selection.entity)
            if face is None or not face.isValid:
                invalid = True
                continue
            if self.body is None:self.body=face.body
            if face.body!=self.body:
                invalid=True
                continue
            if face not in incoming:incoming.append(face)
            if face not in faces and len(faces)>=100:
                exceeded=True
                continue
            if face not in faces:faces.append(face)
        session.faces = tuple(faces)
        session.preview_revision = None
        self.error = 'Choose faces on the same solid. Use Clear selection to start with another body.' if invalid else None
        if exceeded:self.error='Select at most 100 faces. Use Clear selection to start over.'
        # Normal Fusion clicks may replace the native selection. The palette's
        # face set is additive; restore its blue highlight outside this callback.
        if invalid or exceeded or len(incoming)!=len(faces) or any(face not in incoming for face in faces):
            self.request_paint()
        emit('pattern.faces.changed', session_id=session.session_id, count=len(faces),native_count=len(selections), invalid=invalid)
        self.publish()

    def request_paint(self):
        if not self.paint_pending and self.seed_event_id is not None:
            self.paint_pending=True
            self.app.fireCustomEvent(self.seed_event_id,'paint')

    def paint(self):
        self.paint_pending=False
        if not self.bound or not self.ready:return
        self.setting=True
        try:
            values=core.ObjectCollection.create()
            for face in self.session.faces:values.add(face)
            self.ui.activeSelections.all=values
        finally:self.setting=False

    def clear(self):
        self.session.faces=()
        self.body=None
        self.error=None
        self.request_paint()
        self.publish()

    def stop(self):
        self.ready=False
        self.paint_pending=False
        for event,handler in tuple(self.activation_events):
            if getattr(event,'isValid',True) and event.remove(handler) is False:
                raise RuntimeError('Fusion could not release face selection activation. Try Cancel again.')
            self.activation_events.remove((event,handler))
        if self.bound:
            if self.ui.activeSelectionChanged.remove(self.handler) is False:
                raise RuntimeError('Fusion could not detach face selection. Try Cancel again.')
            self.bound = False
        if self.seed_event_id is not None:
            self.app.unregisterCustomEvent(self.seed_event_id)
            self.seed_event_id=None
            self.seed_handler=None
        if self.seeded:
            entities = core.ObjectCollection.create()
            for entity in self.original:
                if getattr(entity, 'isValid', False): entities.add(entity)
            self.ui.activeSelections.all = entities
            self.seeded=False


class _Starting(core.ApplicationCommandEventHandler):
    def __init__(self,picker):super().__init__();self.picker=picker
    def notify(self,args):
        try:
            if args.commandId=='SelectCommand' and self.picker.bound and not self.picker.ready:
                self.picker.app.fireCustomEvent(self.picker.seed_event_id,'seed')
        except Exception as error:
            self.picker.error=str(error);self.picker.publish()


class _SeedRequested(core.CustomEventHandler):
    def __init__(self,picker):super().__init__();self.picker=picker
    def notify(self,args):
        try:
            if self.picker.bound and self.picker.ui.activeCommand=='SelectCommand':
                if self.picker.ready:self.picker.paint()
                else:self.picker.seed()
        except Exception as error:
            self.picker.error=str(error);self.picker.publish()


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
