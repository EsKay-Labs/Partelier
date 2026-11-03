"""Render real preset thumbnails and validate lit meshes in a disposable design."""
def run(context):
    import adsk.core as core,adsk.fusion as native
    import importlib,importlib.util,sys,json,types
    from pathlib import Path
    root=Path(r'C:\Users\SKTech\Desktop\Programming_Projects\Apps\Fusion360\Partelier')
    style=(context or {}).get('style')
    if style not in ('axial','wide','slim','ring','prop2','prop3','prop4','blower'):
        raise ValueError('Run one explicit style per invocation; bulk native rendering is disabled.')
    app=core.Application.get();caller=app.activeDocument;design=native.Design.cast(app.activeProduct)
    live=next(m for k,m in tuple(sys.modules.items()) if k.endswith('partelier.addin'))
    assert app.userInterface.activeCommand in ('','SelectCommand'),'Finish the active native command.'
    for name in ('hinge','snap','pattern','detail','mechanism','finishing'):
        live._tool_library._require_idle_other_tool(getattr(live,'_'+name+'_commands',None),name)
    def snapshot():
        return (design.timeline.count,design.timeline.markerPosition,tuple((b,b.name,b.isLightBulbOn) for b in design.rootComponent.bRepBodies))
    session=live._fan_commands._session
    if session:
        assert not live._fan_commands.busy and not live._fan_commands.runner.busy
        saved=types.ModuleType('_partelier_fan_visual_restore')
        saved.design=design;saved.settings=session.settings.to_dict();saved.references=dict(session.references)
        saved.anchor=session.edit_target.anchor if session.edit_target else None
        sys.modules[saved.__name__]=saved
        live._fan_commands.cancel_palette()
    before=snapshot();camera=app.activeViewport.camera;doc=None;report={'cases':[]}
    prefix='_partelier_fan_visual_validation';package=root/'Partelier/partelier'
    for key in list(sys.modules):
        if key==prefix or key.startswith(prefix+'.'):sys.modules.pop(key,None)
    spec=importlib.util.spec_from_file_location(prefix,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[prefix]=module;spec.loader.exec_module(module)
    F=importlib.import_module(prefix+'.tools.fans.fusion');S=importlib.import_module(prefix+'.tools.fans.settings');T=importlib.import_module(prefix+'.tools.fans.store')
    assets=root/'Partelier/partelier/ui/assets/fans';assets.mkdir(parents=True,exist_ok=True)
    out=root/'output/fan-visual';out.mkdir(parents=True,exist_ok=True)
    try:
        for style in (style,):
            assert style in S.STYLES
            doc=app.documents.add(core.DocumentTypes.FusionDesignDocumentType);d=native.Design.cast(app.activeProduct)
            settings=S.preset(style,'prop5030' if style.startswith('prop') else 'pc120')
            prepared=F.cache(F.prepare(d,settings));assert d.rootComponent.bRepBodies.count==0 and d.timeline.count==0
            anchor=T.apply(prepared);bodies=tuple(anchor.bodies)
            d.rootComponent.isOriginFolderLightBulbOn=False
            view=app.activeViewport;view.visualStyle=core.VisualStyles.ShadedWithVisibleEdgesOnlyVisualStyle
            cam=view.camera;cam.isPerspective=False;cam.isSmoothTransition=False
            cam.eye=core.Point3D.create(settings.diameter_mm*.045,-settings.diameter_mm*.065,settings.diameter_mm*.095)
            cam.target=core.Point3D.create(0,0,0);cam.upVector=core.Vector3D.create(0,0,1);view.camera=cam;view.fit()
            cam=view.camera;cam.viewExtents*=.65;view.camera=cam;view.refresh()
            assert view.saveAsImageFile(str(assets/(style+'.png')),640,480)
            history=d.timeline.count;appearance_count=d.appearances.count
            group=F.draw(prepared)
            for body in bodies:body.isLightBulbOn=False
            meshes=[native.CustomGraphicsMesh.cast(group.item(i)) for i in range(group.count)]
            meshes=[m for m in meshes if m]
            assert len(meshes)==len(bodies)
            for mesh in meshes:
                effect=native.CustomGraphicsBasicMaterialColorEffect.cast(mesh.color)
                assert effect is not None and effect.opacity==1 and effect.emissiveColor.red==0
            assert d.timeline.count==history and d.appearances.count==appearance_count
            view.refresh()
            if style=='axial':assert view.saveAsImageFile(str(out/'shaded-preview.png'),640,480)
            meshes.clear();mesh=None;effect=None
            group.deleteMe();group=None;assert d.rootComponent.customGraphicsGroups.count==0
            report['cases'].append({'style':style,'image':style+'.png','lit_opaque_mesh':True,'no_preview_bodies_or_appearances':True,'triangles':prepared.timings['triangles']})
            # Release native child wrappers before their document owner.
            prepared=None;bodies=();body=None;anchor=None;d=None
            doc.close(False);doc=None
    finally:
        if doc and doc.isValid:doc.close(False)
        caller.activate();app.activeViewport.camera=camera
        assert snapshot()==before,'Caller geometry changed.'
    report.update(success=True,caller_unchanged=True,fusion=app.version)
    (out/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');app.log(json.dumps(report))
