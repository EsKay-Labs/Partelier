"""Mechanism HTML sessions using the shared rollback compute/native commit lifecycle."""

from dataclasses import replace
import adsk.core as core
import adsk.fusion as native
from ..patterns import command as lifecycle
from ..hinge.native_preview import NativePreviewRunner
from .settings import MechanismSettings
from . import fusion,store
from ...diagnostics import emit

COMMIT_ID='sktech_partelier_mechanism_commit_23d8c71a'


class _Runner(NativePreviewRunner):
    def _start(self):
        super()._start();self._definition.name='Partelier: Compute mechanism'
        self._definition.description='Prepare mechanism solids and discard all scratch geometry.'


class MechanismCommands(lifecycle.PatternCommands):
    def __init__(self,report_error=None):
        super().__init__(report_error);self.runner=_Runner(report_error)
        self.runner._command_id='sktech_partelier_mechanism_compute_23d8c71a'
        self.runner._requested_event_id='sktech_partelier_mechanism_event_23d8c71a';self.runner._event_id=self.runner._requested_event_id
        self.last={'sessionId':None,'revision':0,'phase':'idle','editing':False,'settings':None,'selections':{},'previewCurrent':False,'message':'Choose a family, then New mechanism.'}

    def publish(self,session):
        self.last=session.snapshot();emit('mechanism.state',phase=session.phase,revision=session.revision,message=session.message)
        if self.callback:
            try:self.callback(self.last)
            except Exception:self.log('Partelier could not update the mechanism palette')
        return self.last

    def start(self):
        if self._registration:return
        app=core.Application.get();definition=app.userInterface.commandDefinitions.itemById(COMMIT_ID)
        if definition is None:definition=app.userInterface.commandDefinitions.addButtonDefinition(COMMIT_ID,'Partelier: Create / Rebuild mechanism','Save the reviewed mechanism as its own editable feature.')
        handler=lifecycle._Created(self);self._registration=(definition,handler)
        if definition.commandCreated.add(handler) is False:raise RuntimeError('Could not register mechanism creation.')
        for event,handler in ((app.documentDeactivating,lifecycle._DocumentChanging(self)),(app.userInterface.commandTerminated,_CommandEnded(self))):
            if event.add(handler) is False:raise RuntimeError('Could not register mechanism cleanup.')
            self._events.append((event,handler))

    def stop(self):
        if core.Application.get().userInterface.activeCommand==COMMIT_ID:core.Application.get().userInterface.terminateActiveCommand()
        super().stop()

    def begin_palette(self,settings_dict,editing=False,selected_entity=None):
        if self._registration is None or self._session or self.busy:raise ValueError('Finish or Cancel the current mechanism first.')
        if type(editing) is not bool:raise ValueError('Edit mode must be true or false.')
        settings=MechanismSettings.from_dict({**MechanismSettings().to_dict(),**settings_dict})
        session=_Session(self,lifecycle._design(),settings,editing);self._session=session
        self.publish(session)
        if editing:
            ui=core.Application.get().userInterface
            entity=selected_entity or (ui.activeSelections.item(0).entity if ui.activeSelections.count==1 else None)
            if entity is not None:session.select_target(entity)
            else:self.pick(session,'edit_target')
        else:session.validate()
        return self.publish(session)

    def reset(self,session):
        self.runner.cancel(session);session.clear_preview();session.references={};session.geometry_cache.clear()

        session.revision=min(session.revision+1,1_000_000_000);session.picking_target=None
        if session.editing:session.edit_target=None
        session.validate()

    def pick(self,session,target):
        if target != 'edit_target' or not session.editing:raise ValueError('Choose Edit to select a saved mechanism.')
        session.ensure_design();self.runner.cancel(session);session.clear_preview()
        session.picking_target=target;session.phase='selecting';session.message='Select a saved mechanism.';self.publish(session)
        self._busy=True
        try:
            try:selection=core.Application.get().userInterface.selectEntity('Select a saved Partelier mechanism.','SolidBodies,Faces,Edges,Features')
            except RuntimeError:selection=None
            if selection is None:self.reset(session)
            else:session.select_target(selection.entity)
        finally:self._busy=False;session.picking_target=None
        self.publish(session)

    def palette_action(self,action,session_id,revision=None,settings_dict=None,target=None):
        session=self._session
        if self._busy or self._pending or session and session.command:raise ValueError('Wait for mechanism picking or creation.')
        if session is None or session.closed or session.session_id!=session_id:raise ValueError('This mechanism session has ended.')
        session.ensure_design()
        try:
            if action in ('mechanism_update','mechanism_preview','mechanism_commit'):
                session.update(settings_dict,revision)
                if action=='mechanism_update':session.validate()
                elif action=='mechanism_preview':session.show_preview()
                else:
                    if not session.preview_current or session.phase!='preview' or self.runner.busy:raise ValueError('Wait for the current mechanism preview before Create.')
                    store.validate(session.prepared);session.phase='opening';session.message='Applying the reviewed mechanism…';self.publish(session)
                    if session.closed or getattr(session,'cancel_requested',False):raise ValueError('The mechanism was cancelled before Create.')
                    self._pending=session
                    if self._registration[0].execute() is False:self._pending=None;raise RuntimeError('Could not start the mechanism transaction.')
            elif action=='mechanism_focus':
                if self.runner.busy:raise ValueError('Wait for mechanism computation before picking.')
                self.pick(session,target)
            elif action=='mechanism_reset':self.reset(session)
            elif action=='mechanism_cancel':session.close()
            else:raise ValueError('Unsupported mechanism action.')
            return self.publish(session)
        except Exception as error:
            if not session.closed:session.phase='error';session.message=str(error);self.publish(session)
            raise


class _Session(lifecycle._Session):
    def __init__(self,owner,design,settings,editing):
        super().__init__(owner,design,settings,editing);self.references={};self.geometry_cache={};self.validate()

    def snapshot(self):
        valid=not self.editing or self.edit_target is not None
        return {'sessionId':None if self.closed else self.session_id,'endedSessionId':self.session_id if self.closed else None,
            'revision':self.revision,'phase':self.phase,'editing':self.editing,'settings':self.settings.to_dict(),
            'selections':{'surface':{'selected':valid,'label':'Saved mechanism' if self.editing else 'Separate parts at document origin / XYZ offset'},
                'edit_target':{'selected':self.edit_target is not None,'label':'Saved mechanism'}},
            'pickingTarget':self.picking_target,'previewCurrent':self.preview_current,'message':self.message}

    def select_target(self,entity):
        self.clear_preview();self.edit_target=store.read(self.design,entity);self.settings=self.edit_target.settings
        self.references=dict(self.edit_target.recipe['references']);self.validate()

    def require_selections(self):
        self.ensure_design();self.settings.validate()
        if self.editing and self.edit_target is None:raise ValueError('Choose the saved mechanism to edit.')


    def validate(self):
        try:self.require_selections();self.phase='ready';self.message='Ready for live preview. Separate mating parts; test clearances before use.'
        except ValueError as error:self.phase='selecting';self.message=str(error)

    def update(self,values,revision):
        settings=MechanismSettings.from_dict(values)
        if type(revision) is not int or not 0<=revision<=1_000_000_000 or revision<self.revision or revision==self.revision and settings!=self.settings:raise ValueError('These mechanism settings are stale.')
        if settings!=self.settings:self.preview_revision=None
        self.settings,self.revision=settings,revision

    def prepare(self,settings):
        self.require_selections()
        return fusion.cache(fusion.prepare(self.design,settings,self.edit_target))

    def show_preview(self):
        self.require_selections();settings,revision=self.settings,self.revision
        self.phase='computing';self.message='Computing mechanism…';self.owner.publish(self)
        def failed(error):
            if self.closed or self.revision!=revision:return
            self.phase='error';self.preview_revision=None;self.message=str(error);self.owner.publish(self)
        def completed(prepared):
            if self.closed or self.owner._session is not self or self.revision!=revision:return
            try:
                store.validate(prepared);candidate=fusion.draw(prepared)
                try:
                    self.visibility.hide(self.edit_target.bodies if self.edit_target else ())
                    if self.preview is not None and self.preview.isValid and self.preview.deleteMe() is False:raise ValueError('Could not remove the previous mechanism preview.')
                except Exception:
                    candidate.deleteMe()
                    if self.preview is None:self.visibility.restore()
                    raise
                self.preview=candidate;self.prepared=prepared;self.preview_revision=revision;self.phase='preview'
                self.message=f'{settings.family.replace("_"," ").title()} · {len(prepared.bodies)} separate parts. Test fit and motion before use.'
                self.owner.publish(self)
            except Exception as error:failed(error)
        self.owner.runner.request(self,lambda:self.prepare(settings),completed,failed)

    def execute(self,args):
        try:
            if not self.preview_current:raise ValueError('Refresh the mechanism preview before Create.')
            prepared=self.prepared;store.validate(prepared);self.clear_preview()
            from ... import operations
            start=self.design.timeline.count;anchor=store.apply(prepared)
            operations.capture(self.design,anchor,'mechanism',self.settings.to_dict(),start,editing=self.editing)
            self.phase='created';self.message='Mechanism rebuilt.' if self.editing else 'Mechanism created. Saved features → Edit loads its parameters.'
        except Exception as error:
            args.executeFailed=True;args.executeFailedMessage=str(error);self.phase='error';self.message=str(error);self.owner.log('Partelier could not create the mechanism')
        self.owner.publish(self)

    def close(self):
        if self.closed:return
        self.owner.runner.cancel(self);self.clear_preview();self.geometry_cache.clear()
        if self.phase!='created':self.phase='cancelled';self.message='Mechanism cancelled.'
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
