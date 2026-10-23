"""Fixed standard-export smoke check; only an owned unsaved document is changed."""

import importlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import uuid


def _camera_signature(camera):
    def xyz(point):return tuple(round(x,8) for x in (point.x,point.y,point.z))
    ok,width,height=camera.getExtents()
    return xyz(camera.eye),xyz(camera.target),xyz(camera.upVector),camera.cameraType,round(width,8),round(height,8),ok


def run(context):
    if context.get('dry_run'):
        report={'scenario':'pattern_display','success':False,'dry_run':True,'route':'standard_stl_export','model_accessed':False}
        if context.get('report_path'):Path(context['report_path']).write_text(json.dumps(report),encoding='utf-8')
        if context.get('on_complete'):context['on_complete'](report)
        return
    import adsk.core as core
    import adsk.fusion as native
    app=core.Application.get()
    root=Path(__file__).resolve().parents[3]
    output=Path(context['report_path'])
    progress=output.with_suffix('.progress.json')
    def checkpoint(stage,**details):
        progress.write_text(json.dumps({'stage':stage,'utc':time.time(),**details}),encoding='utf-8')
    checkpoint('load_export_adapter')
    name='_partelier_export_display_probe_'+uuid.uuid4().hex
    folder=root/'Partelier/partelier'
    spec=importlib.util.spec_from_file_location(name,folder/'__init__.py',submodule_search_locations=[str(folder)])
    package=importlib.util.module_from_spec(spec);sys.modules[name]=package;spec.loader.exec_module(package)
    display=importlib.import_module(name+'.tools.patterns.display_export')
    original=app.activeDocument
    design=native.Design.cast(app.activeProduct)
    if original is None or design is None:raise ValueError('Open a Fusion Design for the fixed display check.')
    camera=app.activeViewport.camera;camera_signature=_camera_signature(camera)
    originals=tuple((design.rootComponent.bRepBodies.item(i),display.hinge._body_signature(design.rootComponent.bRepBodies.item(i)),design.rootComponent.bRepBodies.item(i).isLightBulbOn) for i in range(design.rootComponent.bRepBodies.count))
    history=(design.timeline.count,design.timeline.markerPosition)
    appearance=None
    for body,_,_ in originals:
        appearance=body.appearance or (body.material.appearance if body.material else None)
        if appearance is not None:break
    if appearance is None:
        for i in range(app.materialLibraries.count):
            library=app.materialLibraries.item(i)
            if library.appearances.count:appearance=library.appearances.item(0);break
    if appearance is None:raise ValueError('An existing appearance is required for the fixed display check.')
    scratch=None;group=None
    report={'scenario':'pattern_display','route':'standard_stl_export','success':False,'cycles':[],'fusion_version':app.version}
    errors=[]
    deferred=[False];runtime={'cancel_requested':context.get('cancel_requested')}
    def finish():
        if runtime.get('finished'):return
        runtime['finished']=True
        if runtime.get('runner') is not None:
            try:runtime['runner'].stop()
            except Exception as error:errors.append(str(error))
        if runtime.get('event_id'):
            try:app.unregisterCustomEvent(runtime['event_id'])
            except Exception as error:errors.append(str(error))
        checkpoint('cleanup')
        def attempt(label,action):
            try:
                if action() is False:raise RuntimeError('operation refused')
            except Exception as error:errors.append(label+': '+str(error))
        if group is not None and group.isValid:attempt('remove owned display',group.deleteMe)
        if scratch is not None and scratch!=original and scratch.isValid:attempt('discard owned document',lambda:scratch.close(False))
        if original.isValid:
            attempt('activate original document',original.activate)
            if app.activeDocument==original:
                def restore_camera():
                    app.activeViewport.camera=camera;app.activeViewport.refresh()
                attempt('restore original camera',restore_camera)
        unchanged=(app.activeDocument==original and history==(design.timeline.count,design.timeline.markerPosition)
            and design.rootComponent.bRepBodies.count==len(originals)
            and all(body.isValid and display.hinge._body_signature(body)==signature and body.isLightBulbOn==visible for body,signature,visible in originals)
            and _camera_signature(app.activeViewport.camera)==camera_signature)
        report['original_model_and_camera_unchanged']=unchanged
        report['cleanup_errors']=errors
        report['success']=unchanged and len(report['cycles'])==12 and report.get('workflow_passed') is True and not errors and not report.get('error') and not report.get('workflow_error')
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        checkpoint('complete',success=report['success'])
        if context.get('on_complete'):context['on_complete'](report)

    try:
        checkpoint('create_owned_document')
        scratch=app.documents.add(core.DocumentTypes.FusionDesignDocumentType)
        if scratch is None or scratch==original:raise RuntimeError('Could not create an independent scratch document.')
        owned=native.Design.cast(app.activeProduct)
        manager=native.TemporaryBRepManager.get()
        checkpoint('create_owned_box')
        body=manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create(0,0,0),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),4,3,.3))
        def box(x,y,length,width,depth):
            return manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create(x,y,0),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),length,width,depth))
        checkpoint('create_owned_dense_plate')
        dense=box(0,0,4,3,.3)
        for row in range(12):
            for column in range(16):
                checkpoint('cut_owned_cell',cell=row*16+column+1)
                if not manager.booleanOperation(dense,box(-1.5+column*.2,-1.1+row*.2,.13,.13,.6),native.BooleanTypes.DifferenceBooleanType):
                    raise RuntimeError('The fixed dense display fixture failed.')
        fixtures=[('box',body,(-2,-1.5,-.15),(2,1.5,.15)),
            ('dense',dense,(-2,-1.5,-.15),(2,1.5,.15)),
            ('cylinder',manager.createCylinderOrCone(core.Point3D.create(0,0,0),1.6,core.Point3D.create(0,0,3.2),1.6),(-1.6,-1.6,0),(1.6,1.6,3.2)),
            ('sphere',manager.createSphere(core.Point3D.create(0,0,0),1.6),(-1.6,-1.6,-1.6),(1.6,1.6,1.6))]
        for label,body,low,high in fixtures:
            for cycle in range(3):
                cancelled=context.get('cancel_requested')
                if cancelled and cancelled():raise RuntimeError('Display export check cancelled.')
                checkpoint('capture_cycle',fixture=label,cycle=cycle+1)
                started=time.perf_counter()
                mesh=display.capture(owned,body,checkpoint)
                capture_ms=(time.perf_counter()-started)*1000
                for axis in range(3):
                    values=mesh.coordinates[axis::3]
                    if abs(min(values)-low[axis])>.005 or abs(max(values)-high[axis])>.005:raise RuntimeError('STL display coordinates or bounds do not match the centimetre CAD source.')
                if owned.rootComponent.bRepBodies.count or owned.timeline.count:raise RuntimeError('Display export leaked model bodies or history.')
                original_frames=None
                if label=='dense' and cycle==0:
                    checkpoint('baseline_draw')
                    group=display.hinge.draw_solid_preview(owned,(('A',body),),{'A':appearance})
                    original_frames=_samples(app,core,0,checkpoint)
                    if group.deleteMe() is False:raise RuntimeError('Baseline graphics cleanup failed.')
                    group=None
                checkpoint('draw_cycle',fixture=label,cycle=cycle+1)
                group=display.draw(owned,body,appearance,mesh)
                if native.CustomGraphicsMesh.cast(group.item(0)) is None:raise RuntimeError('Expected one cached triangle display.')
                frames=_samples(app,core,1.6 if label=='cylinder' else 0,checkpoint)
                if cycle==0:
                    image=output.with_name(output.stem+'-'+label+'.png')
                    if app.activeViewport.saveAsImageFile(str(image),800,800) is False:raise RuntimeError('Could not capture owned display.')
                checkpoint('delete_display',fixture=label,cycle=cycle+1)
                if group.deleteMe() is False:raise RuntimeError('Could not remove owned display graphics.')
                group=None
                item={'fixture':label,'cycle':cycle+1,'triangles':mesh.triangle_count,'capture_ms':capture_ms,'history_restored':True,
                    'camera_refresh_ms':frames,'mean_camera_refresh_ms':sum(frames)/len(frames)}
                if original_frames is not None:item['original_camera_refresh_ms']=original_frames
                report['cycles'].append(item)
        checkpoint('workflow.start')
        deferred[0]=True
        try:_start_workflow(name,owned,box,checkpoint,report,finish,runtime)
        except Exception:
            deferred[0]=False
            raise
    except Exception:
        import traceback
        report['error']=traceback.format_exc()
    finally:
        if not deferred[0]:finish()


def _samples(app,core,center_z,checkpoint):
    import math
    view=app.activeViewport
    camera=view.camera;camera.cameraType=core.CameraTypes.OrthographicCameraType
    camera.isFitView=False;camera.isSmoothTransition=False
    camera.target=core.Point3D.create(0,0,center_z);camera.eye=core.Point3D.create(5,-6,center_z+5)
    camera.upVector=core.Vector3D.create(0,0,1);camera.setExtents(6,6)
    view.camera=camera;view.refresh()
    frames=[]
    for index in range(6):
        checkpoint('camera_refresh',sample=index+1)
        camera=view.camera;camera.isSmoothTransition=False
        angle=.4+index*.15
        camera.eye=core.Point3D.create(7*math.sin(angle),-7*math.cos(angle),center_z+5)
        camera.upVector=core.Vector3D.create(0,0,1)
        started=time.perf_counter();view.camera=camera;view.refresh()
        frames.append((time.perf_counter()-started)*1000)
    return frames


def _start_workflow(package,design,box,checkpoint,report,finish,runtime):
    from dataclasses import replace
    from types import SimpleNamespace as NS
    import traceback
    import adsk.core as core
    import adsk.fusion as native
    app=core.Application.get()
    command=importlib.import_module(package+'.tools.patterns.command')
    adapter=importlib.import_module(package+'.tools.patterns.fusion')
    recipe=importlib.import_module(package+'.tools.patterns.recipe')
    settings=importlib.import_module(package+'.tools.patterns.settings').PatternSettings()
    Runner=importlib.import_module(package+'.tools.patterns.preview').PatternPreviewRunner
    root=design.rootComponent
    feature=root.features.baseFeatures.add()
    # This broad face reproduces a requested size below Balanced's 48-cell
    # spacing floor. The previous small box could not expose that regression.
    feature.startEdit();root.bRepBodies.add(box(0,0,20,16,.3),feature);feature.finishEdit()
    source=feature.bodies.item(0)
    faces=[]
    for i in range(source.faces.count):
        face=source.faces.item(i);ok,normal=face.evaluator.getNormalAtPoint(face.pointOnFace)
        if core.Plane.cast(face.geometry) is not None and ok and normal.z>.99:faces.append(face)
    if len(faces)!=1:raise RuntimeError('The workflow fixture requires one top face.')
    before=(root.bRepBodies.count,design.timeline.count)
    runner=Runner(lambda text:report.setdefault('runtime_logs',[]).append(text))
    runner._command_id='sktech_partelier_export_display_compute_8203b745'
    runner._requested_event_id='sktech_partelier_export_display_compute_event_8203b745'
    runner._event_id=runner._requested_event_id
    event_id='sktech_partelier_export_display_finish_8203b745'
    event=app.registerCustomEvent(event_id)
    runtime.update(runner=runner,event_id=event_id)
    def queue(stage):
        checkpoint('workflow.queue',next=stage)
        app.fireCustomEvent(event_id,stage)
    def compute(session):
        cancelled=runtime.get('cancel_requested')
        if cancelled and cancelled():
            report['cancelled']=True
            raise RuntimeError('Display workflow cancelled.')
        return session.prepare(session.settings)
    def failed(error):
        report['workflow_error']=str(error)+'\n'+traceback.format_exc();queue('finish')
    def draw_checked(prepared):
        recipe.validate_preview_sources(prepared)
        if prepared.display_mesh is None:raise RuntimeError('Rollback result did not retain its plain display arrays.')
        group=adapter.preview_pattern(prepared)
        try:
            if native.CustomGraphicsMesh.cast(group.item(0)) is None:raise RuntimeError('Production preview still used BRep graphics.')
            app.activeViewport.refresh()
        finally:group.deleteMe()
    def record_balanced_size(prepared):
        expected=prepared.settings.pitch_mm-prepared.settings.web_mm
        widths=[max(x for x,y in cell.polygon_mm)-min(x for x,y in cell.polygon_mm)
                for layout in prepared.layouts for cell in layout.cells]
        if not widths or abs(max(widths)-expected)>1e-7:
            raise RuntimeError('Balanced ignored the requested cell size below its density floor.')
        if not 0<prepared.cell_count<=48:raise RuntimeError('Balanced exceeded its soft work budget.')
        report.setdefault('balanced_sizes',[]).append({'requested_size_mm':expected,'actual_size_mm':max(widths),
            'cells':prepared.cell_count,'center_pitch_mm':[layout.effective_pitch_mm for layout in prepared.layouts if layout.cell_count]})
    def created(prepared):
        try:
            checkpoint('workflow.create.after_rollback')
            if (root.bRepBodies.count,design.timeline.count)!=before:raise RuntimeError('Preview display capture failed to roll back its scratch history.')
            draw_checked(prepared)
            record_balanced_size(prepared)
            runtime['anchor']=recipe.create_pattern(design,prepared)
            if root.bRepBodies.count!=before[0] or design.timeline.count!=before[1]+3:raise RuntimeError('Create did not preserve body count and three owned features.')
            runtime['target']=recipe.read_edit_target(design,source)
            if runtime['target'].record.target!=source:raise RuntimeError('Create replaced the original target body.')
            report['prepare_timings']=prepared.timings
            queue('edit')
        except Exception as error:failed(error)
    def rebuilt(prepared):
        try:
            checkpoint('workflow.rebuild.after_rollback')
            draw_checked(prepared)
            record_balanced_size(prepared)
            if recipe.rebuild_pattern(design,runtime['target'],prepared)!=runtime['anchor']:raise RuntimeError('Rebuild replaced its owned anchor.')
            if root.bRepBodies.count!=before[0] or design.timeline.count!=before[1]+3:raise RuntimeError('Rebuild changed body count or owned history.')
            if abs(report['balanced_sizes'][0]['actual_size_mm']-report['balanced_sizes'][1]['actual_size_mm'])<1:
                raise RuntimeError('Rebuild did not change the actual Balanced opening size.')
            report['balanced_size_control_passed']=True
            report['workflow_passed']=True
            report['rollback_export_create_edit_rebuild']=True
            queue('finish')
        except Exception as error:failed(error)
    class Stage(core.CustomEventHandler):
        def notify(self,args):
            try:
                if args.additionalInfo=='edit':
                    checkpoint('workflow.edit.request')
                    session=command._Session(NS(),design,replace(settings,pitch_mm=10),True)
                    session.edit_target=runtime['target']
                    runner.request(session,lambda:compute(session),rebuilt,failed)
                else:finish()
            except Exception as error:failed(error)
    handler=Stage();runtime['handler']=handler
    if event is None or event.add(handler) is False:raise RuntimeError('Could not register the owned workflow stage event.')
    session=command._Session(NS(),design,settings,False);session.faces=tuple(faces)
    checkpoint('workflow.new.request')
    runner.request(session,lambda:compute(session),created,failed)
