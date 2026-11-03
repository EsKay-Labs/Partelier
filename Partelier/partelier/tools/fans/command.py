"""Fan HTML sessions using the shared rollback compute/native commit lifecycle."""

from dataclasses import replace
import adsk.core as core
import adsk.fusion as native
from ..patterns import command as lifecycle
from ..hinge.native_preview import NativePreviewRunner
from .settings import FanSettings
from . import fusion,store,references
from ...diagnostics import emit

COMMIT_ID='sktech_partelier_fan_commit_e46bf1a9'


class _Runner(NativePreviewRunner):
    def _start(self):
        super()._start();self._definition.name='Partelier: Compute fan'
        self._definition.description='Prepare fan solids and discard all scratch geometry.'


class FanCommands(lifecycle.PatternCommands):
    def __init__(self,report_error=None):
        super().__init__(report_error);self.runner=_Runner(report_error)
        self.runner._command_id='sktech_partelier_fan_compute_e46bf1a9'
        self.runner._requested_event_id='sktech_partelier_fan_event_e46bf1a9';self.runner._event_id=self.runner._requested_event_id
        self.last={'sessionId':None,'revision':0,'phase':'idle','editing':False,'settings':None,'selections':{},'previewCurrent':False,'message':'Choose a preset or Custom, then New fan.'}

    def publish(self,session):
        self.last=session.snapshot();emit('fan.state',phase=session.phase,revision=session.revision,message=session.message)
        if self.callback:
            try:self.callback(self.last)
            except Exception:self.log('Partelier could not update the fan palette')
        return self.last

    def start(self):
        if self._registration:return
        app=core.Application.get();definition=app.userInterface.commandDefinitions.itemById(COMMIT_ID)
        if definition is None:definition=app.userInterface.commandDefinitions.addButtonDefinition(COMMIT_ID,'Partelier: Create / Rebuild fan','Save the reviewed fan as its own editable feature.')
        handler=lifecycle._Created(self);self._registration=(definition,handler)
        if definition.commandCreated.add(handler) is False:raise RuntimeError('Could not register fan creation.')
        for event,handler in ((app.documentDeactivating,lifecycle._DocumentChanging(self)),(app.userInterface.commandTerminated,_CommandEnded(self))):
            if event.add(handler) is False:raise RuntimeError('Could not register fan cleanup.')
            self._events.append((event,handler))

    def stop(self):
        if core.Application.get().userInterface.activeCommand==COMMIT_ID:core.Application.get().userInterface.terminateActiveCommand()
        super().stop()

    def begin_palette(self,settings_dict,editing=False,selected_entity=None):
        if self._registration is None or self._session or self.busy:raise ValueError('Finish or Cancel the current fan first.')
        if type(editing) is not bool:raise ValueError('Edit mode must be true or false.')
        settings=FanSettings.from_dict({**FanSettings().to_dict(),**settings_dict})
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
        session.settings=replace(session.settings,outline_mode='generated',size_preset='custom')
        session.revision=min(session.revision+1,1_000_000_000);session.picking_target=None
        if session.editing:session.edit_target=None
        session.validate()

    def pick(self,session,target):
        if target not in ('circle','outline','edit_target'):raise ValueError('Choose a supported fan reference.')
        session.ensure_design();self.runner.cancel(session);session.clear_preview()
        if target=='edit_target' and not session.editing:raise ValueError('Start Edit to choose a saved fan.')
        prompt,filter_={'circle':('Select one complete circular opening edge.','Edges'),
            'outline':('Select one closed sketch blade outline with finite root and tip widths.','Profiles'),
            'edit_target':('Select a saved fan body or its feature.','SolidBodies,Faces,Edges,Features')}[target]
        session.picking_target=target;session.phase='selecting';session.message=prompt;self.publish(session)
        self._busy=True
        try:
            try:selection=core.Application.get().userInterface.selectEntity(prompt+' Esc resets references.',filter_)
            except RuntimeError:selection=None
            session.ensure_design()
            if selection is None:self.reset(session);return
            entity=selection.entity
            if target=='edit_target':session.select_target(entity)
            elif target=='circle':
                if session.edit_target and getattr(entity,'body',None) in session.edit_target.bodies:raise ValueError('Choose an independent opening, outside the fan being edited.')
                _,diameter=references.circle(entity)
                session.references['circle']=entity.entityToken
                session.settings=replace(session.settings,diameter_mm=diameter-2*session.settings.tip_gap_mm,size_preset='custom')
            else:
                references.outline(entity);session.references['outline']=entity.entityToken
                session.settings=replace(session.settings,outline_mode='sketch',size_preset='custom')
            session.revision=min(session.revision+1,1_000_000_000);session.validate()
        finally:self._busy=False;session.picking_target=None
        self.publish(session)

    def palette_action(self,action,session_id,revision=None,settings_dict=None,target=None):
        session=self._session
        if self._busy or self._pending or session and session.command:raise ValueError('Wait for fan picking or creation.')
        if session is None or session.closed or session.session_id!=session_id:raise ValueError('This fan session has ended.')
        session.ensure_design()
        try:
            if action in ('fan_update','fan_preview','fan_commit'):
                session.update(settings_dict,revision)
                if action=='fan_update':session.validate()
                elif action=='fan_preview':session.show_preview()
                else:
                    if not session.preview_current or session.phase!='preview' or self.runner.busy:raise ValueError('Wait for the current fan preview before Create.')
                    store.validate(session.prepared);session.phase='opening';session.message='Applying the reviewed fan…';self.publish(session)
                    if session.closed or getattr(session,'cancel_requested',False):raise ValueError('The fan was cancelled before Create.')
                    self._pending=session
                    if self._registration[0].execute() is False:self._pending=None;raise RuntimeError('Could not start the fan transaction.')
            elif action=='fan_focus':
                if self.runner.busy:raise ValueError('Wait for fan computation before picking.')
                self.pick(session,target)
            elif action=='fan_reset':self.reset(session)
            elif action=='fan_cancel':session.close()
            else:raise ValueError('Unsupported fan action.')
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
            'selections':{'surface':{'selected':valid,'label':'Saved fan' if self.editing else 'Circular opening' if 'circle' in self.references else 'Document XY / Z axis'},
                'circle':{'selected':'circle' in self.references,'label':'Opening fitted' if 'circle' in self.references else 'Optional'},
                'outline':{'selected':'outline' in self.references,'label':'Sketch outline' if 'outline' in self.references else 'Generated'},
                'edit_target':{'selected':self.edit_target is not None,'label':'Saved fan'}},
            'pickingTarget':self.picking_target,'previewCurrent':self.preview_current,'message':self.message}

    def select_target(self,entity):
        self.clear_preview();self.edit_target=store.read(self.design,entity);self.settings=self.edit_target.settings
        self.references=dict(self.edit_target.recipe['references']);self.validate()

    def require_selections(self):
        self.ensure_design();self.settings.validate()
        if self.editing and self.edit_target is None:raise ValueError('Choose the saved fan to edit.')
        references.resolve(self.design,self.references,self.settings)

    def validate(self):
        try:self.require_selections();self.phase='ready';self.message='Ready for live preview. Hub interfaces need measured dimensions.'
        except ValueError as error:self.phase='selecting';self.message=str(error)

    def update(self,values,revision):
        settings=FanSettings.from_dict(values)
        if type(revision) is not int or not 0<=revision<=1_000_000_000 or revision<self.revision or revision==self.revision and settings!=self.settings:raise ValueError('These fan settings are stale.')
        if 'circle' in self.references:
            edge=self.design.findEntityByToken(self.references['circle'])
            if len(edge)!=1:raise ValueError('Opening reference changed. Pick it again.')
            _,diameter=references.circle(edge[0]);settings=replace(settings,diameter_mm=diameter-2*settings.tip_gap_mm,size_preset='custom')
        if settings.outline_mode=='generated' or settings.output=='guard':self.references.pop('outline',None)
        if settings!=self.settings:self.preview_revision=None
        self.settings,self.revision=settings,revision

    def prepare(self,settings):
        self.require_selections();placement,outline,signature=references.resolve(self.design,self.references,settings)
        prepared=fusion.prepare(self.design,settings,placement,dict(self.references),outline,self.edit_target,self.geometry_cache)
        return fusion.cache(replace(prepared,reference_signature=signature))

    def show_preview(self):
        self.require_selections();settings,revision=self.settings,self.revision
        self.phase='computing';self.message='Computing fan…';self.owner.publish(self)
        def failed(error):
            if self.closed or self.revision!=revision:return
            self.phase='error';self.preview_revision=None;self.message=str(error);self.owner.publish(self)
        def completed(prepared):
            if self.closed or self.owner._session is not self or self.revision!=revision:return
            try:
                store.validate(prepared);candidate=fusion.draw(prepared)
                try:
                    self.visibility.hide(self.edit_target.bodies if self.edit_target else ())
                    if self.preview is not None and self.preview.isValid and self.preview.deleteMe() is False:raise ValueError('Could not remove the previous fan preview.')
                except Exception:
                    candidate.deleteMe()
                    if self.preview is None:self.visibility.restore()
                    raise
                self.preview=candidate;self.prepared=prepared;self.preview_revision=revision;self.phase='preview'
                self.message=f'{prepared.plan.blade_count} blades · Ø{settings.diameter_mm:g} mm · {len(prepared.bodies)} output body/bodies. Geometry prototype; validate balance and strength before operation.' if settings.output!='hub_test' else 'Hub-only fitting coupon. Confirm the motor/shaft fit first.'
                if settings.output=='guard':self.message=f'{settings.guard_type.title()} guard · {settings.frame_width_mm:g} mm · {settings.guard_thickness_mm:g} mm thick · one body.'
                self.owner.publish(self)
            except Exception as error:failed(error)
        self.owner.runner.request(self,lambda:self.prepare(settings),completed,failed)

    def execute(self,args):
        try:
            if not self.preview_current:raise ValueError('Refresh the fan preview before Create.')
            prepared=self.prepared;store.validate(prepared);self.clear_preview()
            from ... import operations
            start=self.design.timeline.count;anchor=store.apply(prepared)
            operations.capture(self.design,anchor,'fan',self.settings.to_dict(),start,editing=self.editing)
            self.phase='created';self.message='Fan rebuilt.' if self.editing else 'Fan created. Saved features → Edit loads its parameters.'
        except Exception as error:
            args.executeFailed=True;args.executeFailedMessage=str(error);self.phase='error';self.message=str(error);self.owner.log('Partelier could not create the fan')
        self.owner.publish(self)

    def close(self):
        if self.closed:return
        self.owner.runner.cancel(self);self.clear_preview();self.geometry_cache.clear()
        if self.phase!='created':self.phase='cancelled';self.message='Fan cancelled.'
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
