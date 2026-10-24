"""HTML pattern sessions, rollback-only computation and explicit native commits."""

import traceback
import time
import uuid

import adsk.core as core
import adsk.fusion as native

from .settings import PatternSettings
from . import fusion, recipe, display_export
from .preview import PatternPreviewRunner
from .face_selection import FaceSelection
from ..hinge.visibility import BodyVisibilityLease
from ...diagnostics import emit


COMMIT_ID="sktech_partelier_pattern_commit_23bc07a1"


def _active_command():
    try:return core.Application.get().userInterface.activeCommand
    except Exception:return None


def _design():
    value=native.Design.cast(core.Application.get().activeProduct)
    if value is None:
        raise ValueError("Open a Fusion Design before creating a pattern.")
    return value


class PatternCommands:
    def __init__(self,report_error=None):
        self.report_error=report_error
        self.runner=PatternPreviewRunner()
        self._registration=None
        self._events=[]
        self._session=None
        self._pending=None
        self._busy=False
        self.callback=None
        self.last={'sessionId':None,'revision':0,'phase':'idle','editing':False,'settings':None,
                   'selections':{},'previewCurrent':False,'message':'Select a face or body for the pattern.'}

    @property
    def busy(self):
        return self._busy or self.runner.busy

    def set_state_callback(self,callback):
        self.callback=callback

    def palette_state(self):
        return self._session.snapshot() if self._session else self.last

    def publish(self,session):
        self.last=session.snapshot()
        emit('pattern.state',session_id=session.session_id,revision=session.revision,phase=session.phase,
             closed=session.closed,preview_current=self.last['previewCurrent'],
             selected=self.last['selections']['surface']['selected'],message=session.message)
        if self.callback:
            try:self.callback(self.last)
            except Exception:self.log("Partelier could not update the pattern palette")
        return self.last

    def log(self,summary):
        core.Application.get().log(summary+'\n'+traceback.format_exc())

    def start(self):
        if self._registration:return
        app=core.Application.get()
        definition=app.userInterface.commandDefinitions.itemById(COMMIT_ID)
        if definition is None:
            definition=app.userInterface.commandDefinitions.addButtonDefinition(COMMIT_ID,
                'Partelier: Create / Rebuild pattern','Apply the reviewed pattern to the same existing body.')
        handler=_Created(self)
        self._registration=(definition,handler)
        if definition.commandCreated.add(handler) is False:
            raise RuntimeError("Fusion could not register the pattern command.")
        for event,handler in ((app.documentDeactivating,_DocumentChanging(self)),
                              (app.userInterface.commandTerminated,_CommandEnded(self))):
            if event.add(handler) is False:raise RuntimeError("Fusion could not register pattern cleanup.")
            self._events.append((event,handler))

    def stop(self):
        errors=[]
        def attempt(action):
            try:action()
            except Exception as error:errors.append(error)
        if core.Application.get().userInterface.activeCommand==COMMIT_ID:
            attempt(core.Application.get().userInterface.terminateActiveCommand)
        if self._session:attempt(self._session.close)
        attempt(self.runner.stop)
        for event,handler in self._events:attempt(lambda event=event,handler=handler:event.remove(handler))
        self._events.clear()
        if self._registration:
            definition,handler=self._registration
            attempt(lambda:definition.commandCreated.remove(handler))
            if definition.isValid:attempt(definition.deleteMe)
            self._registration=None
        self._pending=None
        if errors:raise RuntimeError("Pattern cleanup needs another Stop attempt. "+str(errors[0]))

    def begin_palette(self,settings_dict,editing=False):
        emit('pattern.begin',editing=editing,busy=self.busy,existing_session=self._session is not None,
             active_command=_active_command(),settings=settings_dict)
        if self._registration is None:raise ValueError("Run Partelier to enable patterns.")
        if self._session or self.busy:raise ValueError("Finish or cancel the current pattern first.")
        if type(editing) is not bool:raise ValueError("Edit mode must be true or false.")
        values=PatternSettings.from_dict({**PatternSettings().to_dict(),**settings_dict})
        session=_Session(self,_design(),values,editing)
        self._session=session
        self.publish(session)
        self._busy=True
        try:
            selections=core.Application.get().userInterface.activeSelections
            entities=[selections.item(i).entity for i in range(selections.count)]
            emit('pattern.preselection',session_id=session.session_id,count=len(entities))
            if editing and len(entities)==1:
                session.select_target(entities[0])
            elif not editing and values.selection_scope=='faces' and entities and all(native.BRepFace.cast(e) is not None for e in entities):
                if len(entities)>100:raise ValueError('Select at most 100 faces.')
                if any(face.body!=entities[0].body for face in entities):raise ValueError('Choose faces on the same solid body.')
                session.set_faces(entities)
                self.pick(session,'add_face')
            else:self.pick(session,'edit_target' if editing else values.selection_scope)
            return self.publish(session)
        finally:self._busy=False

    def export_colour(self):
        if self._session or self.busy:
            raise ValueError('Create or Cancel the current preview before exporting.')
        design=_design()
        ui=core.Application.get().userInterface
        self._busy=True
        try:
            selected=ui.activeSelections
            entity=(selected.item(0).entity if selected.count==1 else
                    ui.selectEntity('Select the base or colour body of a Flat colour pattern.','SolidBodies,Faces,Edges').entity)
            target=recipe.read_edit_target(design,entity)
            if target.settings.mode!='inlay':raise ValueError('Select a created Flat colour pattern to export.')
            dialog=ui.createFileDialog()
            dialog.title='Export Partelier flat colour'
            dialog.filter='3MF files (*.3mf)'
            dialog.initialFilename='Partelier-flat-colour.3mf'
            if dialog.showSave()!=core.DialogResults.DialogOK:return 'Export cancelled.'
            if core.Application.get().activeProduct!=design:
                raise ValueError('Return to the original design before exporting.')
            from .colour_export import export
            export(design,target,dialog.filename)
            return 'Exported two aligned parts. Assign filaments to Base and Pattern colour in Bambu Studio.'
        finally:self._busy=False

    def pick(self,session,target):
        emit('pattern.pick.begin',session_id=session.session_id,target=target,revision=session.revision)
        session.ensure_design()
        session.clear_preview()
        if target in {'faces','add_face'} and not session.editing:
            if session.settings.selection_scope!='faces':
                raise ValueError('Use face selection scope before selecting individual faces.')
            if session.face_picker is not None:raise ValueError('Finish the current face selection with Done.')
            if target=='faces':session.faces=()
            session.face_picker=FaceSelection(session)
            try:session.face_picker.start()
            except Exception as error:
                # Retain the cleanup owner even if registration/restoration
                # fails, so Cancel/Stop can retry instead of leaking a handler.
                session.face_picker.error=str(error)
                raise
            return
        ui=core.Application.get().userInterface
        if session.editing:
            if target!='edit_target':raise ValueError("Select an existing Partelier pattern result.")
            prompt,filters='Select an existing Partelier pattern result. Esc cancels picking.','SolidBodies,Faces,Edges'
        elif target=='body' and session.settings.selection_scope=='body':
            prompt,filters='Select the solid to pattern on all its faces. Esc cancels picking.','SolidBodies'
        elif target in {'faces','add_face'} and session.settings.selection_scope=='faces':
            prompt,filters=('Select more faces on this body. Esc finishes the selection.' if target=='add_face'
                            else 'Select the first face. Use Add faces for more sides. Esc cancels picking.'),'Faces'
        else:raise ValueError("Use the current pattern selection scope.")
        session.phase='selecting';session.message=prompt;self.publish(session)
        faces=[]
        emit('pattern.pick.wait',session_id=session.session_id,target=target,filters=filters,count=len(faces),
             active_command=_active_command())
        while True:
            try:selected=ui.selectEntity(prompt,filters)
            except RuntimeError as error:
                emit('pattern.pick.interrupted',session_id=session.session_id,error=str(error))
                selected=None
            emit('pattern.pick.return',session_id=session.session_id,target=target,
                 has_entity=selected is not None and selected.entity is not None)
            session.ensure_design()
            if selected is None or selected.entity is None:break
            if session.editing:
                session.select_target(selected.entity)
            elif target=='body':
                body=native.BRepBody.cast(selected.entity)
                session.set_faces([body.faces.item(i) for i in range(body.faces.count)])
            else:
                face=native.BRepFace.cast(selected.entity)
                if face is None:raise ValueError("Select a solid face.")
                if faces and face.body!=faces[0].body:raise ValueError("Choose faces on the same solid body.")
                if face not in faces:
                    if len(faces)>=100:raise ValueError("Select at most 100 faces.")
                    faces.append(face)
                emit('pattern.pick.accepted',session_id=session.session_id,count=len(faces))
                session.set_faces(faces)
            self.publish(session)
            break
        session.validate()
        emit('pattern.pick.end',session_id=session.session_id,target=target,count=len(session.faces),phase=session.phase)

    def palette_action(self,action,session_id,revision=None,settings_dict=None,target=None):
        emit('pattern.action',action=action,session_id=session_id,revision=revision,target=target,
             owner_busy=self._busy,pending_commit=self._pending is not None,runner_busy=self.runner.busy)
        session=self._session
        if self._busy or self._pending or (session and session.command):
            raise ValueError("Finish picking or wait for pattern creation.")
        if session is None or session.closed or session.session_id!=session_id:
            raise ValueError("This pattern session has ended. Start a new pattern.")
        session.ensure_design()
        if session.face_picker is not None and action not in {'pattern_finish_faces','pattern_clear_faces','pattern_cancel'}:
            raise ValueError('Finish face selection with Done, or Cancel the pattern.')
        try:
            if action in {'pattern_update','pattern_preview','pattern_commit'}:
                session.update(settings_dict,revision)
                if action=='pattern_update':session.validate()
                elif action=='pattern_preview':session.show_preview()
                else:
                    if not session.preview_current or session.phase!='preview' or self.runner.busy:
                        raise ValueError("Wait for the current pattern preview before creating it.")
                    recipe.validate_preview_sources(session.prepared)
                    session.phase='opening';session.message='Rebuilding pattern…' if session.editing else 'Creating pattern…'
                    self.publish(session);self._pending=session
                    if self._registration[0].execute() is False:
                        self._pending=None;raise RuntimeError("Fusion could not open the pattern transaction.")
            elif action=='pattern_focus':
                if self.runner.busy:raise ValueError("Wait for pattern computation before picking again.")
                self._busy=True
                try:self.pick(session,target)
                finally:self._busy=False
            elif action=='pattern_cancel':session.close()
            elif action=='pattern_finish_faces':session.finish_faces()
            elif action=='pattern_clear_faces':
                if session.face_picker is None:raise ValueError('Start selecting faces before clearing them.')
                session.face_picker.clear()
            else:raise ValueError("This pattern action is unavailable.")
            return self.publish(session)
        except Exception as error:
            if not session.closed:
                session.phase='error';session.message=str(error);self.publish(session)
            raise


class _Session:
    def __init__(self,owner,design,settings,editing):
        self.owner,self.design,self.settings,self.editing=owner,design,settings,editing
        self.session_id=str(uuid.uuid4());self.revision=0
        self.phase='selecting';self.message='Select the pattern surfaces.'
        self.faces=();self.edit_target=None;self.closed=False
        self.preview=None;self.prepared=None;self.preview_revision=None
        self.visibility=BodyVisibilityLease();self.command=None;self.handlers=[]
        self.face_picker=None

    @property
    def preview_current(self):
        return self.preview is not None and self.preview.isValid and self.preview_revision==self.revision and self.prepared is not None

    def snapshot(self):
        valid=(self.edit_target is not None if self.editing else bool(self.faces) and all(face.isValid for face in self.faces))
        label=('Pattern selected' if self.editing else str(len(self.faces))+' face(s) on '+self.faces[0].body.name) if valid else 'Not selected'
        sizes=([layout.cell_size_mm for layout in self.prepared.layouts if layout.cell_count and layout.cell_size_mm is not None]
               if self.settings.layout_mode=='auto' and self.preview_current else [])
        return {'sessionId':self.session_id,'revision':self.revision,'phase':self.phase,'editing':self.editing,
                'settings':self.settings.to_dict(),'selections':{'surface':{'selected':bool(valid),'label':label}},
                'previewCurrent':self.preview_current,'message':self.message,
                'pickingFaces':self.face_picker is not None,
                'canFinishFaces':bool(self.face_picker is not None and self.face_picker.ready and valid and not self.face_picker.error),
                'suggestedSizeMm':min(sizes) if sizes else None}

    def ensure_design(self):
        if self.closed or _design()!=self.design:raise ValueError("The active design changed. Start a new pattern.")

    def set_faces(self,faces):
        self.clear_preview();self.faces=tuple(faces);self.validate()

    def finish_faces(self):
        if self.face_picker is None:raise ValueError('There is no active face selection.')
        self.face_picker.synchronize()
        if self.face_picker.error:raise ValueError(self.face_picker.error)
        if not self.faces:raise ValueError('Select at least one face before clicking Done.')
        self.face_picker.stop();self.face_picker=None
        self.validate()

    def select_target(self,entity):
        self.clear_preview();self.edit_target=recipe.read_edit_target(self.design,entity)
        self.settings=self.edit_target.settings;self.validate()

    def require_selections(self):
        self.ensure_design();self.settings.validate()
        if (self.editing and self.edit_target is None) or (not self.editing and not self.faces):
            raise ValueError("Select an existing pattern." if self.editing else "Select the faces or body to pattern.")

    def validate(self):
        try:self.require_selections();self.phase='ready';self.message='Surfaces selected. Live preview will update.'
        except ValueError as error:self.phase='selecting';self.message=str(error)

    def update(self,values,revision):
        if type(revision) is not int or not 0<=revision<=1_000_000_000:raise ValueError("Use a valid pattern revision.")
        settings=PatternSettings.from_dict(values)
        if revision<self.revision or (revision==self.revision and settings!=self.settings):
            raise ValueError("These pattern settings are stale.")
        if settings.selection_scope!=self.settings.selection_scope:
            if self.editing:raise ValueError("Start a new pattern to change the selection scope.")
            self.owner.runner.cancel(self);self.clear_preview();self.faces=()
        if settings!=self.settings:self.preview_revision=None
        self.settings,self.revision=settings,revision

    def prepare(self,settings):
        if self.face_picker is not None:raise ValueError('Finish face selection with Done before previewing.')
        self.require_selections()
        if self.editing:
            target=recipe.read_edit_target(self.design,self.edit_target.anchor)
            prepared=recipe.prepare_edit_pattern(self.design,target,settings)
        else:prepared=fusion.prepare_pattern(self.design,self.faces,settings)
        return display_export.prepare(prepared)

    def show_preview(self):
        emit('pattern.preview.request',session_id=self.session_id,revision=self.revision,settings=self.settings.to_dict())
        self.require_selections()
        settings,revision=self.settings,self.revision
        self.phase='computing';self.message='Computing surface pattern…';self.owner.publish(self)
        def completed(prepared):
            if self.closed or self.owner._session is not self or revision!=self.revision:
                emit('pattern.preview.discarded',session_id=self.session_id,revision=revision,
                     current_revision=self.revision,closed=self.closed)
                return
            try:
                recipe.validate_preview_sources(prepared)
                emit('pattern.draw.begin',session_id=self.session_id,revision=revision,cells=prepared.cell_count)
                draw_started=time.perf_counter()
                candidate=fusion.preview_pattern(prepared)
                if candidate is None or not candidate.isValid:
                    raise ValueError("Fusion could not draw the pattern preview. Original visibility is unchanged.")
                try:
                    self.visibility.hide(fusion.preview_hide_bodies(prepared))
                    if self.preview is not None and self.preview.isValid and self.preview.deleteMe() is False:
                        raise RuntimeError("Fusion could not replace the old pattern preview.")
                except Exception:
                    if candidate and candidate.isValid:candidate.deleteMe()
                    if self.preview is None:self.visibility.restore()
                    raise
                self.preview=candidate;self.prepared=prepared;self.preview_revision=revision
                emit('pattern.draw.end',session_id=self.session_id,revision=revision,
                     elapsed_ms=(time.perf_counter()-draw_started)*1000)
                timings=getattr(prepared,'timings',None)
                if isinstance(timings,dict):
                    timings['graphics_draw_ms']=(time.perf_counter()-draw_started)*1000
                    try:
                        core.Application.get().log('Partelier pattern preview timings: '+
                            ' '.join(f'{key}={value:.3f}' for key,value in timings.items() if type(value) in (int,float)))
                    except Exception:pass
                self.phase='preview';self.message=str(prepared.cell_count)+' cells. Review the pattern before Create.'
                if self.settings.layout_mode=='auto':
                    sizes=[layout.cell_size_mm for layout in prepared.layouts if layout.cell_count]
                    caption=f'{min(sizes):.2f}' if max(sizes)-min(sizes)<.005 else f'{min(sizes):.2f}–{max(sizes):.2f}'
                    self.message=f'Auto fit · {self.settings.density} · {prepared.cell_count} cells · cell size {caption} mm'
                    emit('pattern.auto_fit',session_id=self.session_id,revision=revision,
                         proposals=sum(layout.proposals_evaluated for layout in prepared.layouts),
                         acceptance_checks=sum(layout.acceptance_checks for layout in prepared.layouts),
                         cells=prepared.cell_count,sizes_mm=sizes)
                elif any(getattr(layout,'repeat_u_mm',None) is not None for layout in getattr(prepared,'layouts',())):
                    sizes=[layout.cell_size_mm for layout in prepared.layouts if layout.cell_count]
                    caption=f'{min(sizes):.2f}' if max(sizes)-min(sizes)<.005 else f'{min(sizes):.2f}–{max(sizes):.2f}'
                    self.message=f'{prepared.cell_count} cells · cell size {caption} mm · minimum gap {self.settings.web_mm:g} mm'
                elif self.settings.layout_mode=='balanced':
                    size=self.settings.pitch_mm-self.settings.web_mm
                    pitches=[layout.effective_pitch_mm for layout in getattr(prepared,'layouts',()) if layout.cell_count]
                    gap=min(pitches)-size if pitches else self.settings.web_mm
                    self.message=f'{prepared.cell_count} cells · cell size {size:g} mm · grid gap ≈ {gap:.2f} mm'
                elif self.settings.layout_mode=='fit':
                    pitches=[layout.effective_pitch_mm for layout in getattr(prepared,'layouts',()) if layout.cell_count]
                    if pitches:
                        low,high=min(pitches),max(pitches)
                        low-=self.settings.web_mm;high-=self.settings.web_mm
                        caption=f'{low:.2f}' if abs(high-low)<.005 else f'{low:.2f}–{high:.2f}'
                        dimension='cell size'
                        self.message=f'{prepared.cell_count} cells · {dimension} {caption} mm'
                elif self.settings.layout_mode=='fill':
                    self.message=(f'{prepared.cell_count} cells · size {self.settings.pitch_mm-self.settings.web_mm:g} mm'
                                  f' · minimum gap {self.settings.web_mm:g} mm · border ≥ {self.settings.border_mm:g} mm')
                self.owner.publish(self)
            except Exception as error:failed(error)
        def failed(error):
            emit('pattern.preview.error',session_id=self.session_id,revision=revision,error=str(error),
                 traceback=traceback.format_exc())
            if self.closed or revision!=self.revision:return
            self.phase='error';self.preview_revision=None;self.message=str(error).replace('hinge','pattern');self.owner.publish(self)
        self.owner.runner.request(self,lambda:self.prepare(settings),completed,failed)

    def clear_preview(self):
        emit('pattern.preview.clear',session_id=self.session_id,phase=self.phase,had_preview=self.preview is not None)
        self.preview_revision=None;self.prepared=None
        if self.preview is not None and self.preview.isValid:
            if self.preview.deleteMe() is False:raise RuntimeError("Fusion could not remove the pattern preview. Cancel or Stop will retry.")
        self.preview=None;self.visibility.restore()

    def execute(self,args):
        emit('pattern.commit.begin',session_id=self.session_id,revision=self.revision,editing=self.editing)
        try:
            prepared=self.prepared
            if prepared is None or self.preview_revision!=self.revision:raise ValueError("Refresh the pattern preview before Create.")
            recipe.validate_preview_sources(prepared)
            self.clear_preview()
            if self.editing:recipe.rebuild_pattern(self.design,self.edit_target,prepared)
            else:recipe.create_pattern(self.design,prepared)
            self.phase='created';self.message='Pattern rebuilt successfully.' if self.editing else 'Pattern created on the selected body.'
            emit('pattern.commit.end',session_id=self.session_id,revision=self.revision)
        except Exception as error:
            emit('pattern.commit.error',session_id=self.session_id,error=str(error),traceback=traceback.format_exc())
            args.executeFailed=True;args.executeFailedMessage=str(error)[:1200]
            self.phase='error';self.message=str(error);self.owner.log('Partelier could not create or rebuild the pattern')
        self.owner.publish(self)

    def close(self):
        emit('pattern.session.close',session_id=self.session_id,phase=self.phase,closed=self.closed)
        if self.closed:return
        if self.face_picker is not None:
            self.face_picker.stop();self.face_picker=None
        self.owner.runner.cancel(self);self.clear_preview()
        if self.phase!='created':self.phase='cancelled';self.message='Pattern cancelled.'
        self.closed=True
        if self.owner._session is self:self.owner._session=None
        self.owner.publish(self)


class _Created(core.CommandCreatedEventHandler):
    def __init__(self,owner):super().__init__();self.owner=owner
    def notify(self,args):
        emit('pattern.commit.created',has_pending=self.owner._pending is not None)
        session=self.owner._pending;self.owner._pending=None;command=args.command
        command.isExecutedWhenPreEmpted=False;command.isRepeatable=False
        try:
            if session is None or session.closed:raise ValueError("Start the pattern from the Partelier palette.")
            session.ensure_design();session.command=command
            for event,handler in ((command.destroy,_Destroyed(session)),(command.execute,_Execute(session))):
                session.handlers.append((event,handler))
                if event.add(handler) is False:raise RuntimeError("Fusion could not attach the pattern transaction handler.")
            command.isAutoExecute=True
        except Exception as error:
            command.isAutoExecute=True;command.isOKButtonVisible=False
            if session:
                session.command=None;session.phase='error';session.message=str(error)
                for event,handler in session.handlers:
                    try:event.remove(handler)
                    except Exception:self.owner.log('Partelier could not detach a refused pattern handler')
                session.handlers.clear();self.owner.publish(session)


class _Execute(core.CommandEventHandler):
    def __init__(self,session):super().__init__();self.session=session
    def notify(self,args):
        if self.session.command is None or self.session.phase!='opening':
            args.executeFailed=True;args.executeFailedMessage='The pattern transaction did not initialize.';return
        self.session.execute(args)


class _Destroyed(core.CommandEventHandler):
    def __init__(self,session):super().__init__();self.session=session
    def notify(self,args):
        emit('pattern.commit.destroyed',session_id=self.session.session_id,phase=self.session.phase)
        session=self.session
        for event,handler in session.handlers:
            try:event.remove(handler)
            except Exception:session.owner.log('Partelier could not detach its pattern transaction handler')
        session.handlers.clear();session.command=None
        if session.phase=='created':session.close()
        else:
            if session.phase=='opening':session.phase='error';session.message='Creation was interrupted. Refresh preview.'
            session.owner.publish(session)


class _DocumentChanging(core.DocumentEventHandler):
    def __init__(self,owner):super().__init__();self.owner=owner
    def notify(self,args):
        emit('pattern.document.deactivating',has_session=self.owner._session is not None)
        if self.owner._session:self.owner._session.close()


class _CommandEnded(core.ApplicationCommandEventHandler):
    def __init__(self,owner):super().__init__();self.owner=owner
    def notify(self,args):
        session=self.owner._session
        if not session or not session.preview_current or self.owner.busy or args.commandId in {COMMIT_ID,'SelectCommand'}:return
        try:recipe.validate_preview_sources(session.prepared)
        except Exception as error:
            emit('pattern.source.invalidated',command=args.commandId,session_id=session.session_id,error=str(error))
            session.clear_preview();session.phase='error';session.message=str(error);self.owner.publish(session)
