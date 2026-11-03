"""Inject one pArea display failure; exercise real native replacement/Close.

Requires an idle loaded Partelier. Does not change model geometry.
"""
def run(context):
    import adsk.core as core, adsk.fusion as native
    import json,sys
    from pathlib import Path
    app=core.Application.get();design=native.Design.cast(app.activeProduct)
    addin=next(m for k,m in tuple(sys.modules.items()) if k.endswith('partelier.addin'))
    library=addin._tool_library
    assert app.userInterface.activeCommand in ('','SelectCommand')
    for name in ('hinge','snap','pattern','detail','fan','mechanism','finishing'):
        library._require_idle_other_tool(getattr(addin,'_'+name+'_commands',None),name)
    def snapshot():
        return (app.activeDocument,app.documents.count,design.timeline.count,design.timeline.markerPosition,
                tuple((body,body.name,body.isLightBulbOn) for body in design.rootComponent.bRepBodies))
    before=snapshot();original=library._new_palette;made=[]
    class FirstDisplayFailure:
        def __getattr__(self,name):return getattr(made[0],name)
        @property
        def isVisible(self):return made[0].isVisible
        @isVisible.setter
        def isVisible(self,value):raise RuntimeError('2 : InternalValidationError : pArea')
    def create(*args,**kwargs):
        palette=original(*args,**kwargs);made.append(palette)
        return FirstDisplayFailure() if len(made)==1 else palette
    try:
        library.close();library._new_palette=create;library.show()
        assert len(made)==2 and not made[0].isValid
        replacement=library._palette
        assert replacement.isValid and replacement.isVisible and '_recovery_' in replacement.id
        assert replacement.dockingState==core.PaletteDockingStates.PaletteDockStateFloating
        assert library._html_handler is not None and library._close_handler is not None
        assert snapshot()==before
        library._new_palette=original
        library.close();assert not replacement.isValid
        library.show();assert library._palette.isVisible and library._palette.isValid
        assert snapshot()==before
        report={'success':True,'injected_error':'pArea on visibility','native_replacement':True,
                'floating':True,'old_palette_deleted':True,'close_reopen':True,'caller_unchanged':True,'fusion':app.version}
        path=Path(r'C:\Users\SKTech\Desktop\Programming_Projects\Apps\Fusion360\Partelier\output\overnight\palette-recovery.json')
        path.write_text(json.dumps(report,indent=2),encoding='utf-8');app.log(json.dumps(report))
    finally:
        library._new_palette=original
