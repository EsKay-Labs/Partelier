"""Knob grip sessions using rollback preview and one owned native Cut."""

import adsk.core as core
from ..patterns import command as lifecycle
from ..hinge.native_preview import NativePreviewRunner
from .settings import KnurlSettings
from . import fusion,store
from ...diagnostics import emit

COMMIT_ID='sktech_partelier_knurling_commit_b23c9a71'


class _Runner(NativePreviewRunner):
    def _start(self):
        super()._start();self._definition.name='Partelier: Compute knurling'
        self._definition.description='Prepare knurling solids and discard all scratch geometry.'


class KnurlCommands(lifecycle.PatternCommands):
    def __init__(self,report_error=None):
        super().__init__(report_error);self.runner=_Runner(report_error)
        self.runner._command_id='sktech_partelier_knurling_compute_b23c9a71'
        self.runner._requested_event_id='sktech_partelier_knurling_event_b23c9a71';self.runner._event_id=self.runner._requested_event_id
        self.last={'sessionId':None,'revision':0,'phase':'idle','editing':False,'settings':None,'selections':{},'previewCurrent':False,'message':'Choose a grip style, then select an external cylinder.'}

    def publish(self,session):
        self.last=session.snapshot();emit('knurling.state',phase=session.phase,revision=session.revision,message=session.message)
        if self.callback:
            try:self.callback(self.last)
            except Exception:self.log('Partelier could not update the knurling palette')
        return self.last

    def start(self):
        if self._registration:return
        app=core.Application.get();definition=app.userInterface.commandDefinitions.itemById(COMMIT_ID)
        if definition is None:definition=app.userInterface.commandDefinitions.addButtonDefinition(COMMIT_ID,'Partelier: Create / Rebuild knurling','Save the reviewed knurling as its own editable feature.')
        handler=lifecycle._Created(self);self._registration=(definition,handler)
        if definition.commandCreated.add(handler) is False:raise RuntimeError('Could not register knurling creation.')
        for event,handler in ((app.documentDeactivating,lifecycle._DocumentChanging(self)),(app.userInterface.commandTerminated,_CommandEnded(self))):
            if event.add(handler) is False:raise RuntimeError('Could not register knurling cleanup.')
            self._events.append((event,handler))

    def stop(self):
        if core.Application.get().userInterface.activeCommand==COMMIT_ID:core.Application.get().userInterface.terminateActiveCommand()
        super().stop()

    def begin_palette(self,settings_dict,editing=False,selected_entity=None):
        if self._registration is None or self._session or self.busy:raise ValueError('Finish or Cancel the current knurling first.')
        if type(editing) is not bool:raise ValueError('Edit mode must be true or false.')
        settings=KnurlSettings.from_dict({**KnurlSettings().to_dict(),**settings_dict})
        session=_Session(self,lifecycle._design(),settings,editing);self._session=session
        self.publish(session)
        if editing:
            ui=core.Application.get().userInterface
            entity=selected_entity or (ui.activeSelections.item(0).entity if ui.activeSelections.count==1 else None)
            if entity is not None:session.select_target(entity)
            else:self.pick(session,'edit_target')
        else:
            ui=core.Application.get().userInterface
            entity=selected_entity or (ui.activeSelections.item(0).entity if ui.activeSelections.count==1 else None)
            if entity is not None:
                session.settings=fusion.fit(settings,entity);session.references={'face_a':entity.entityToken}
                session.validate()
            else:self.pick(session,'face_a')
        return self.publish(session)

    def reset(self,session):
        self.runner.cancel(session);session.clear_preview();session.references={};session.geometry_cache.clear()
        session.revision=min(session.revision+1,1_000_000_000);session.picking_target=None
        if session.editing:session.edit_target=None
        session.validate()

    def pick(self,session,target):
        if target not in ('face_a','edit_target'):raise ValueError('Choose a cylinder or saved knurling.')
        if session.editing and target!='edit_target':raise ValueError('Saved knurlings retain their original source faces.')
        session.ensure_design();self.runner.cancel(session);session.clear_preview();self._busy=True
        try:
            targets=(target,)
            for role in targets:
                prompt='Select a saved knob knurling.' if role=='edit_target' else 'Select the external cylindrical face of the knob.'
                session.picking_target=role;session.phase='selecting';session.message=prompt;self.publish(session)
                try:selected=core.Application.get().userInterface.selectEntity(prompt+' Esc resets selection.','Features,SolidBodies,Faces' if role=='edit_target' else 'CylindricalFaces')
                except RuntimeError:selected=None
                session.ensure_design()
                if selected is None:self.reset(session);return
                if role=='edit_target':session.select_target(selected.entity)
                else:
                    fusion.cylinder(selected.entity)
                    if role=='face_a':
                        session.settings=fusion.fit(session.settings,selected.entity)
                        session.references={}
                    session.references[role]=selected.entity.entityToken
                session.revision=min(session.revision+1,1_000_000_000)
            session.validate()
        finally:self._busy=False;session.picking_target=None
        self.publish(session)

    def palette_action(self,action,session_id,revision=None,settings_dict=None,target=None):
        session=self._session
        if self._busy or self._pending or session and session.command:raise ValueError('Wait for knurling picking or creation.')
        if session is None or session.closed or session.session_id!=session_id:raise ValueError('This knurling session has ended.')
        session.ensure_design()
        try:
            if action in ('knurling_update','knurling_preview','knurling_commit'):
                session.update(settings_dict,revision)
                if action=='knurling_update':session.validate()
                elif action=='knurling_preview':session.show_preview()
                else:
                    if not session.preview_current or session.phase!='preview' or self.runner.busy:raise ValueError('Wait for the current knurling preview before Create.')
                    store.validate(session.prepared);session.phase='opening';session.message='Applying the reviewed knurling…';self.publish(session)
                    if session.closed or getattr(session,'cancel_requested',False):raise ValueError('The knurling was cancelled before Create.')
                    self._pending=session
                    if self._registration[0].execute() is False:self._pending=None;raise RuntimeError('Could not start the knurling transaction.')
            elif action=='knurling_focus':
                if self.runner.busy:raise ValueError('Wait for knurling computation before picking.')
                self.pick(session,target)
            elif action=='knurling_reset':self.reset(session)
            elif action=='knurling_cancel':session.close()
            else:raise ValueError('Unsupported knurling action.')
            return self.publish(session)
        except Exception as error:
            if not session.closed:session.phase='error';session.message=str(error);self.publish(session)
            raise


class _Session(lifecycle._Session):
    def __init__(self,owner,design,settings,editing):
        super().__init__(owner,design,settings,editing);self.references={};self.geometry_cache={};self.validate()

    def snapshot(self):
        valid=self.edit_target is not None if self.editing else 'face_a' in self.references
        selections={'face_a':{'selected':'face_a' in self.references,'label':'External cylinder'}}
        selections['surface']={'selected':valid,'label':'Cylinder selected' if valid else 'Choose cylinder'}
        return {'sessionId':None if self.closed else self.session_id,'endedSessionId':self.session_id if self.closed else None,
            'revision':self.revision,'phase':self.phase,'editing':self.editing,'settings':self.settings.to_dict(),
            'selections':selections,'pickingTarget':self.picking_target,'previewCurrent':self.preview_current,'message':self.message}

    def resolved_faces(self):
        faces=[]
        for role in ('face_a',):
            if role not in self.references:continue
            matches=self.design.findEntityByToken(self.references[role])
            if len(matches)!=1:raise ValueError('The cylinder changed. Select it again.')
            faces.append(matches[0])
        return tuple(faces)

    def select_target(self,entity):
        self.clear_preview();self.edit_target=store.read(self.design,entity);self.settings=self.edit_target.settings
        self.references=dict(zip(('face_a',),self.edit_target.recipe['sources']['faces']));self.validate()

    def require_selections(self):
        self.ensure_design();self.settings.validate()
        if self.editing:
            if self.edit_target is None:raise ValueError('Choose the saved knurling to edit.')
        else:fusion.selection(self.design,self.resolved_faces(),self.settings)

    def validate(self):
        try:self.require_selections();self.phase='ready';self.message='Ready for knurling preview.'
        except ValueError as error:self.phase='selecting';self.message=str(error)

    def update(self,values,revision):
        settings=KnurlSettings.from_dict(values)
        if type(revision) is not int or not 0<=revision<=1_000_000_000 or revision<self.revision or revision==self.revision and settings!=self.settings:raise ValueError('These knurling settings are stale.')
        if settings!=self.settings:self.preview_revision=None
        self.settings,self.revision=settings,revision

    def prepare(self,settings):
        self.require_selections()
        prepared=store.prepare_edit(self.design,self.edit_target,settings) if self.editing else fusion.prepare(self.design,self.resolved_faces(),settings)
        return fusion.cache(prepared)

    def show_preview(self):
        self.require_selections();settings,revision=self.settings,self.revision
        self.phase='computing';self.message='Computing knurling…';self.owner.publish(self)
        def failed(error):
            if self.closed or self.revision!=revision:return
            self.phase='error';self.preview_revision=None;self.message=str(error);self.owner.publish(self)
        def completed(prepared):
            if self.closed or self.owner._session is not self or self.revision!=revision:return
            try:
                store.validate(prepared);candidate=fusion.draw(prepared)
                try:
                    self.visibility.hide(prepared.targets)
                    if self.preview is not None and self.preview.isValid and self.preview.deleteMe() is False:raise ValueError('Could not remove the previous knurling preview.')
                except Exception:
                    candidate.deleteMe()
                    if self.preview is None:self.visibility.restore()
                    raise
                self.preview=candidate;self.prepared=prepared;self.preview_revision=revision;self.phase='preview'
                self.message='Review the knob grip. Print with its cylinder axis upright.'
                self.owner.publish(self)
            except Exception as error:failed(error)
        self.owner.runner.request(self,lambda:self.prepare(settings),completed,failed)

    def execute(self,args):
        try:
            if not self.preview_current:raise ValueError('Refresh the knurling preview before Create.')
            prepared=self.prepared;store.validate(prepared);self.clear_preview()
            from ... import operations
            start=self.design.timeline.count;anchor=store.apply(prepared)
            operations.capture(self.design,anchor,'knurling',self.settings.to_dict(),start,editing=self.editing)
            self.phase='created';self.message='Knurling rebuilt.' if self.editing else 'Knurling created. Saved features → Edit loads its parameters.'
        except Exception as error:
            args.executeFailed=True;args.executeFailedMessage=str(error);self.phase='error';self.message=str(error);self.owner.log('Partelier could not create the knurling')
        self.owner.publish(self)

    def close(self):
        if self.closed:return
        self.owner.runner.cancel(self);self.clear_preview();self.geometry_cache.clear()
        if self.phase!='created':self.phase='cancelled';self.message='Knurling cancelled.'
        self.closed=True
        if self.owner._session is self:self.owner._session=None
        self.owner.publish(self)


class _CommandEnded(core.ApplicationCommandEventHandler):
    def __init__(self,owner):super().__init__();self.owner=owner
    def notify(self,args):
        session=self.owner._session
        if session is None or not session.preview_current or self.owner.busy:return
        try:store.validate(session.prepared)
        except Exception as error:session.clear_preview();session.phase='error';session.message=str(error);self.owner.publish(session)
