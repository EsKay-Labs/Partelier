"""Opt-in isolated native mechanical-pair smoke test. Never changes caller CAD."""
import importlib, importlib.util, json, sys, time, traceback
from pathlib import Path


def run(context):
    import adsk.core as core
    import adsk.fusion as native
    from dataclasses import replace
    # MCP Python.Run executes script text without defining __file__. Load an
    # isolated package namespace so this fixture never reloads a live UI session.
    root=Path(r'C:\Users\SKTech\Desktop\Programming_Projects\Apps\Fusion360\Partelier')
    package=root/'Partelier'/'partelier';prefix='_partelier_mechanism_validation'
    for name in list(sys.modules):
        if name==prefix or name.startswith(prefix+'.'):del sys.modules[name]
    spec=importlib.util.spec_from_file_location(prefix,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[prefix]=module;spec.loader.exec_module(module)
    settings_module=importlib.import_module(prefix+'.tools.mechanisms.settings')
    MechanismSettings,FAMILIES=settings_module.MechanismSettings,settings_module.FAMILIES
    fusion=importlib.import_module(prefix+'.tools.mechanisms.fusion')
    store=importlib.import_module(prefix+'.tools.mechanisms.store')
    motion=importlib.import_module(prefix+'.tools.mechanisms.motion')
    app=core.Application.get();caller=app.activeDocument;report={'cases':[]};doc=None
    try:
        for family in FAMILIES:
            started=time.perf_counter();entry={'family':family}
            try:
                doc=app.documents.add(core.DocumentTypes.FusionDesignDocumentType)
                design=native.Design.cast(app.activeProduct)
                before=(design.timeline.count,design.rootComponent.bRepBodies.count)
                settings=MechanismSettings(family=family)
                prepared=fusion.prepare(design,settings)
                entry['motion']=motion.validate(prepared)
                assert before==(design.timeline.count,design.rootComponent.bRepBodies.count),'Prepare persisted geometry'
                cached=fusion.cache(prepared);group=fusion.draw(cached)
                assert group.isValid
                group.deleteMe()
                anchor=store.apply(prepared);record=store.read(design,anchor)
                assert record.settings==settings
                count=design.rootComponent.bRepBodies.count
                newer=replace(settings,clearance_mm=.32 if family=='pip_louver' else .4)
                updated=fusion.prepare(design,newer,record)
                assert store.apply(updated)==anchor
                assert design.rootComponent.bRepBodies.count==count
                assert store.read(design,anchor).settings==newer
                entry.update(ok=True,bodies=count,triangles=sum(mesh.triangle_count for mesh in cached.meshes))
            except Exception:
                entry.update(ok=False,error=traceback.format_exc())
            finally:
                entry['seconds']=time.perf_counter()-started
                report['cases'].append(entry)
                if doc is not None:doc.close(False);doc=None
        report['ok']=all(case['ok'] for case in report['cases'])
    finally:
        if doc is not None:doc.close(False)
        if caller is not None and caller.isValid:caller.activate()
        out=root/'output'/'overnight';out.mkdir(parents=True,exist_ok=True)
        (out/'mechanisms-native.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    app.log(json.dumps(report))
