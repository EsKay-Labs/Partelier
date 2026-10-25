"""Small details HTML sessions on the proven rollback/commit lifecycle."""

import uuid
from dataclasses import replace
import adsk.core as core
import adsk.fusion as native
from ..patterns import command as lifecycle
from ..hinge.native_preview import NativePreviewRunner
from ...diagnostics import emit
from .settings import DetailSettings
from . import fusion,store


COMMIT_ID='sktech_partelier_detail_commit_3cc4981e'


class _DetailPreviewRunner(NativePreviewRunner):
    def _start(self):
        super()._start()
        self._definition.name='Partelier: Compute Small detail'
        self._definition.description='Prepare the detail and roll back all temporary display geometry.'


class DetailCommands(lifecycle.PatternCommands):
    def __init__(self,report_error=None):
        super().__init__(report_error)
        self.runner=_DetailPreviewRunner(report_error)
        self.runner._command_id='sktech_partelier_detail_compute_3cc4981e'
        self.runner._requested_event_id='sktech_partelier_detail_compute_event_3cc4981e'
        self.runner._event_id=self.runner._requested_event_id
        self.last={'sessionId':None,'revision':0,'phase':'idle','editing':False,'settings':None,
            'selections':{},'previewCurrent':False,'message':'Choose a detail and its two support faces.'}

    def publish(self,session):
        self.last=session.snapshot()
        emit('detail.state',session_id=session.session_id,revision=session.revision,phase=session.phase,message=session.message)
        if self.callback:
            try:self.callback(self.last)
            except Exception:self.log('Partelier could not update the Small details UI')
        return self.last

    def start(self):
        if self._registration:return
        app=core.Application.get();definition=app.userInterface.commandDefinitions.itemById(COMMIT_ID)
        if definition is None:definition=app.userInterface.commandDefinitions.addButtonDefinition(COMMIT_ID,'Partelier: Create / Rebuild detail','Apply the reviewed detail to the existing bodies.')
        handler=lifecycle._Created(self);self._registration=(definition,handler)
        if definition.commandCreated.add(handler) is False:raise RuntimeError('Could not register the detail commit.')
        handler=lifecycle._DocumentChanging(self)
        if app.documentDeactivating.add(handler) is False:raise RuntimeError('Could not register detail cleanup.')
        self._events.append((app.documentDeactivating,handler))

    def stop(self):
        ui=core.Application.get().userInterface
        if ui.activeCommand==COMMIT_ID:ui.terminateActiveCommand()
        return super().stop()

    def begin_palette(self,settings_dict,editing=False,selected_entity=None):
        if self._registration is None or self._session or self.busy:raise ValueError('Finish or Cancel the active detail first.')
        if type(editing) is not bool:raise ValueError('Edit mode must be true or false.')
        settings=DetailSettings.from_dict({**DetailSettings().to_dict(),**settings_dict})
        session=_Session(self,lifecycle._design(),settings,editing);self._session=session
        ui=core.Application.get().userInterface;entities=[ui.activeSelections.item(i).entity for i in range(ui.activeSelections.count)]
        self.publish(session)
        self._busy=True
        try:
            if editing and selected_entity is not None:session.select_target(selected_entity)
            elif editing and len(entities)==1:session.select_target(entities[0])
            elif not editing and len(entities)==2 and all(native.BRepFace.cast(e) is not None and e.isValid for e in entities):
                session.faces=tuple(entities);session.validate()
            else:self.pick(session,'edit_target' if editing else 'face_a')
        except ValueError as error:
            session.phase='error';session.message=str(error)
        finally:self._busy=False
        session.offer_sides()
        return self.publish(session)

    def reset(self,session):
        if getattr(session,'side_picker',None) is not None:
            session.side_picker.clear();return
        session.revision=min(session.revision+1,1_000_000_000);self.runner.cancel(session)
        session.clear_preview();session.faces=(None,None);session.edit_target=None;session.picking_target=None
        session.phase='selecting';session.message='Selection reset. Pick face A to start again. Dimensions kept.'
        session.sides_confirmed=False

    def pick(self,session,target):
        if target=='lip_sides':session.start_sides();return
        targets=('edit_target',) if session.editing else ('face_a','face_b')
        if target not in targets:raise ValueError('Choose a supported detail reference.')
        for current in targets[targets.index(target):]:
            if not self._pick_one(session,current):break
        session.picking_target=None
        if hasattr(session,'offer_sides'):session.offer_sides()
        self.publish(session)

    def _pick_one(self,session,target):
        if target not in (('edit_target',) if session.editing else ('face_a','face_b')):raise ValueError('Choose a supported detail reference.')
        session.ensure_design();session.clear_preview()
        prompt=('Select the generated detail or its timeline feature.' if target=='edit_target' else
            'Select support face A.' if target=='face_a' else 'Select support face B on the same body.' if session.settings.kind=='ribs' else 'Select the lid inside face facing A.')
        filters='Features,SolidBodies,Faces' if target=='edit_target' else 'PlanarFaces'
        session.picking_target=target;session.phase='selecting';session.message=prompt;self.publish(session)
        try:choice=core.Application.get().userInterface.selectEntity(prompt+' Esc resets all selections.',filters)
        except RuntimeError:choice=None
        session.ensure_design()
        if choice is not None and choice.entity is not None:
            if target=='edit_target':session.select_target(choice.entity)
            else:
                faces=list(session.faces);faces[0 if target=='face_a' else 1]=choice.entity;session.faces=tuple(faces)
                session.sides_confirmed=False
            session.validate();return True
        self.reset(session);return False

    def palette_action(self,action,session_id,revision=None,settings_dict=None,target=None):
        session=self._session
        if self._busy or self._pending or (session and session.command):raise ValueError('Wait for picking or detail creation.')
        if session is None or session.closed or session.session_id!=session_id:raise ValueError('This detail session has ended.')
        session.ensure_design()
        try:
            if session.side_picker is not None and action not in ('detail_finish_sides','detail_clear_sides','detail_cancel','detail_reset'):
                raise ValueError('Finish choosing lip sides with Done, or Cancel.')
            if action in ('detail_update','detail_preview','detail_commit'):
                session.update(settings_dict,revision)
                if session.offer_sides():return self.publish(session)
                if action=='detail_update':session.validate()
                elif action=='detail_preview':session.show_preview()
                else:
                    if not session.preview_current or session.phase!='preview' or self.runner.busy:raise ValueError('Wait for the current detail preview before Create.')
                    store.validate(session.prepared);session.phase='opening';session.message='Applying the reviewed detail…'
                    self.publish(session);self._pending=session
                    if self._registration[0].execute() is False:self._pending=None;raise RuntimeError('Fusion could not open the detail transaction.')
            elif action=='detail_focus':
                if self.runner.busy:raise ValueError('Wait for preview computation before picking again.')
                self._busy=True
                try:self.pick(session,target)
                finally:self._busy=False
            elif action=='detail_reset':self.reset(session)
            elif action=='detail_finish_sides':session.finish_sides()
            elif action=='detail_clear_sides':
                if session.side_picker is None:raise ValueError('Start choosing lip sides first.')
                session.side_picker.clear()
            elif action=='detail_cancel':session.close()
            else:raise ValueError('This detail action is unavailable.')
            return self.publish(session)
        except Exception as error:
            if not session.closed:
                if session.side_picker is not None:session.side_picker.error=str(error);session.side_picker.publish()
                else:session.picking_target=None;session.phase='error';session.message=str(error);self.publish(session)
            raise


class _Session(lifecycle._Session):
    def __init__(self,owner,design,settings,editing):
        super().__init__(owner,design,settings,editing);self.faces=(None,None);self.picking_target=None
        self.side_picker=None;self.sides_confirmed=False

    @property
    def needs_sides(self):return self.settings.kind=='lid' and self.settings.lip_layout=='selected'

    def offer_sides(self):
        if self.side_picker is not None:return True
        supports=self.edit_target is not None if self.editing else all(f is not None and f.isValid for f in self.faces)
        if self.needs_sides and supports and not self.sides_confirmed:
            self.start_sides();return True
        return False

    def start_sides(self):
        if not self.needs_sides:raise ValueError('Choose Selected sides for the lip layout first.')
        if self.side_picker is not None:return
        if self.editing and self.edit_target is None or not self.editing and any(f is None or not f.isValid for f in self.faces):
            raise ValueError('Select both support faces before choosing lip sides.')
        from .side_selection import SideSelection
        self.owner.runner.cancel(self);self.clear_preview();self.preview_revision=None
        picker=SideSelection(self);self.side_picker=picker
        try:picker.start()
        except Exception:
            self.side_picker=None;self.picking_target=None;raise

    def finish_sides(self):
        picker=self.side_picker
        if picker is None:raise ValueError('Start choosing lip sides first.')
        picker.synchronize()
        if picker.error:raise ValueError(picker.error)
        mask=picker.mask
        if not mask:raise ValueError('Choose at least one lip side before Done.')
        picker.stop();self.side_picker=None;self.picking_target=None
        self.settings=replace(self.settings,lip_sides=mask);self.sides_confirmed=True
        self.revision=min(self.revision+1,1_000_000_000);self.validate()

    def snapshot(self):
        valid=self.edit_target is not None if self.editing else all(f is not None and f.isValid for f in self.faces)
        selections={'edit_target':{'selected':self.edit_target is not None,'label':'Detail selected'}} if self.editing else {
            key:{'selected':face is not None and face.isValid,'label':face.body.name if face is not None and face.isValid else ''}
            for key,face in zip(('face_a','face_b'),self.faces)}
        selections['surface']={'selected':bool(valid),'label':'Supports selected' if valid else 'Pick'}
        if self.needs_sides:
            count=len(self.side_picker.session.faces) if self.side_picker else self.settings.lip_sides.bit_count()
            selections['lip_sides']={'selected':self.sides_confirmed and self.side_picker is None,'label':f'{count} sides'}
            selections['surface']['selected']=bool(valid and self.sides_confirmed and self.side_picker is None)
        return {'sessionId':None if self.closed else self.session_id,'revision':self.revision,'phase':self.phase,'editing':self.editing,
            'endedSessionId':self.session_id if self.closed else None,'pickingTarget':self.picking_target,
            'pickingSides':self.side_picker is not None,'canFinishSides':bool(self.side_picker and self.side_picker.ready and self.side_picker.session.faces and not self.side_picker.error),
            'settings':self.settings.to_dict(),'selections':selections,'previewCurrent':self.preview_current,'message':self.message}

    def select_target(self,entity):
        self.clear_preview();self.edit_target=store.read(self.design,entity,self.settings.kind)
        self.settings=self.edit_target.settings;self.sides_confirmed=True;self.validate()

    def require_selections(self):
        self.ensure_design();self.settings.validate()
        if self.editing:
            if self.edit_target is None:raise ValueError('Select an existing detail.')
        elif any(f is None or not f.isValid for f in self.faces):raise ValueError('Select both support faces to preview.')
        if self.needs_sides and (not self.sides_confirmed or self.side_picker is not None):raise ValueError('Choose lip sides, then Done to preview.')

    def validate(self):
        try:self.require_selections();self.phase='ready';self.message='Supports selected. Live preview will update.'
        except ValueError as error:self.phase='selecting';self.message=str(error)

    def update(self,values,revision):
        settings=DetailSettings.from_dict(values)
        if type(revision) is not int or not 0<=revision<=1_000_000_000 or revision<self.revision or (revision==self.revision and settings!=self.settings):
            raise ValueError('These detail settings are stale.')
        if settings.kind!=self.settings.kind:raise ValueError('Cancel before changing the detail tool.')
        if settings.lip_layout!=self.settings.lip_layout:self.sides_confirmed=False
        if settings.lip_sides!=self.settings.lip_sides:raise ValueError('Choose lip sides on the model, then Done.')
        if settings!=self.settings:self.preview_revision=None
        self.settings,self.revision=settings,revision

    def prepare(self,settings):
        self.require_selections()
        prepared=store.prepare_edit(self.design,self.edit_target,settings) if self.editing else fusion.prepare(self.design,self.faces,settings)
        return fusion.cache(prepared)

    def show_preview(self):
        self.require_selections();settings,revision=self.settings,self.revision
        self.phase='computing';self.message='Computing Small detail…';self.owner.publish(self)
        def failed(error):
            if self.closed or self.revision!=revision:return
            self.phase='error';self.preview_revision=None;self.message=str(error);self.owner.publish(self)
        def completed(prepared):
            if self.closed or self.owner._session is not self or self.revision!=revision:return
            try:
                store.validate(prepared);candidate=fusion.draw(prepared)
                try:
                    self.visibility.hide(prepared.targets)
                    if self.preview is not None and self.preview.isValid and self.preview.deleteMe() is False:raise ValueError('The previous detail preview could not be removed.')
                except Exception:
                    if candidate.isValid:candidate.deleteMe()
                    if self.preview is None:self.visibility.restore()
                    raise
                self.preview=candidate;self.prepared=prepared;self.preview_revision=revision;self.phase='preview'
                self.message='Review the matching lip and groove.' if settings.kind=='lid' else f'Review {settings.pin_count} pins and their receiving holes.' if settings.kind=='alignment' else f'Review {settings.rib_count} attached ribs.'
                emit('detail.preview',kind=settings.kind,revision=revision,timings=prepared.timings)
                self.owner.publish(self)
            except Exception as error:failed(error)
        self.owner.runner.request(self,lambda:self.prepare(settings),completed,failed)

    def execute(self,args):
        try:
            if not self.preview_current:raise ValueError('Refresh the detail preview before Create.')
            self.clear_preview_for_commit()
            from ... import operations
            start=self.design.timeline.count
            anchor=store.apply(self.prepared)
            operations.capture(self.design,anchor,'detail',self.settings.to_dict(),start,editing=self.editing)
            self.phase='created';self.message='Detail rebuilt.' if self.editing else 'Detail created.'
        except Exception as error:
            args.executeFailed=True;args.executeFailedMessage=str(error);self.phase='error';self.message=str(error)
            self.owner.log('Partelier could not apply the Small detail')
        self.owner.publish(self)

    def clear_preview_for_commit(self):
        if self.preview is not None and self.preview.isValid and self.preview.deleteMe() is False:raise ValueError('Could not remove the detail preview.')
        self.preview=None;self.visibility.restore()

    def close(self):
        if self.closed:return
        if self.side_picker is not None:self.side_picker.stop();self.side_picker=None;self.picking_target=None
        self.owner.runner.cancel(self);self.clear_preview()
        if self.phase!='created':self.phase='cancelled';self.message='Detail cancelled.'
        self.closed=True
        if self.owner._session is self:self.owner._session=None
        self.owner.publish(self)
