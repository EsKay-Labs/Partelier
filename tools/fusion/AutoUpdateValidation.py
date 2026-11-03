"""Disposable upstream-edit/owned-history refresh fixture."""
def run(context):
    import adsk.core as c, adsk.fusion as n
    import importlib,importlib.util,sys,json,traceback
    from pathlib import Path
    root=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier')
    prefix='_partelier_refresh_validation';package=root/'Partelier/partelier'
    for key in tuple(sys.modules):
        if key==prefix or key.startswith(prefix+'.'):del sys.modules[key]
    spec=importlib.util.spec_from_file_location(prefix,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[prefix]=module;spec.loader.exec_module(module)
    mod=lambda suffix:importlib.import_module(prefix+'.'+suffix)
    app=c.Application.get();caller=app.activeDocument;doc=None;report={}
    try:
        doc=app.documents.add(c.DocumentTypes.FusionDesignDocumentType);design=n.Design.cast(app.activeProduct);comp=design.rootComponent
        sketch=comp.sketches.add(comp.xYConstructionPlane);sketch.sketchCurves.sketchLines.addTwoPointRectangle(c.Point3D.create(-5,-4,0),c.Point3D.create(5,4,0))
        ext=comp.features.extrudeFeatures.addSimple(sketch.profiles.item(0),c.ValueInput.createByReal(.4),n.FeatureOperations.NewBodyFeatureOperation)
        body=ext.bodies.item(0);body.name='Caller fixture source';ops=mod('operations');refresh=mod('auto_refresh')
        store=mod('tools.finishing.store');fusion=mod('tools.finishing.fusion');Settings=mod('tools.finishing.settings').FinishingSettings
        anchors=[]
        for index,kind in enumerate(('arrow','scale')):
            face=max((f for f in body.faces if c.Plane.cast(f.geometry) and f.evaluator.getNormalAtPoint(f.pointOnFace)[1].z>.99),key=lambda f:f.area)
            settings=Settings(kind=kind,mode='emboss',offset_x_mm=-20+index*40,offset_y_mm=0,width_mm=10,length_mm=15,depth_mm=1)
            prepared=fusion.prepare(design,(face,),settings);start=design.timeline.count;anchor=store.apply(prepared)
            ops.capture(design,anchor,'finishing',settings.to_dict(),start);anchors.append(anchor)
            assert anchor.attributes.itemByName(refresh.GROUP,'baseline') is not None
        before=design.timeline.count
        assert refresh.refresh(design)==[]
        assert ext.timelineObject.rollTo(True)
        ext.extentOne.distance.value=.7
        design.timeline.moveToEnd()
        updated=refresh.refresh(design)
        assert len(updated)==2,updated
        assert design.timeline.count==before and comp.bRepBodies.count==1 and body.name=='Caller fixture source'
        assert abs(body.boundingBox.maxPoint.z-.8)<1e-5,body.boundingBox.maxPoint.z
        assert refresh.refresh(design)==[]
        report={'success':True,'updated':updated,'same_body':True,'history_count_preserved':True,'no_change_no_rebuild':True}
    except Exception:report={'success':False,'error':traceback.format_exc()}
    finally:
        if doc:doc.close(False)
        if caller and caller.isValid:caller.activate()
    (root/'output/overnight/auto-update.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
