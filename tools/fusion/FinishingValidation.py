"""Isolated short native matrix. Run through MCP; never modifies caller document."""
def run(context):
 import adsk.core as c,adsk.fusion as n,sys,importlib,json,traceback
 from pathlib import Path
 from dataclasses import replace
 app=c.Application.get();caller=app.activeDocument
 assert app.userInterface.activeCommand in ('','SelectCommand'), 'Fusion has an active command.'
 prefix=next(k.rsplit('.',1)[0] for k in sys.modules if k.endswith('partelier.addin'))
 for name in ('settings','planner','fusion','store'):
  full=prefix+'.tools.finishing.'+name
  if full in sys.modules:importlib.reload(sys.modules[full])
 settings=importlib.import_module(prefix+'.tools.finishing.settings');a=importlib.import_module(prefix+'.tools.finishing.fusion');store=importlib.import_module(prefix+'.tools.finishing.store')
 report=[]
 for kind in settings.KINDS:
  doc=None
  try:
   doc=app.documents.add(c.DocumentTypes.FusionDesignDocumentType);design=n.Design.cast(app.activeProduct);root=design.rootComponent
   sketch=root.sketches.add(root.xYConstructionPlane);sketch.sketchCurves.sketchLines.addTwoPointRectangle(c.Point3D.create(-5,-4,0),c.Point3D.create(5,4,0))
   ext=root.features.extrudeFeatures.addSimple(sketch.profiles.item(0),c.ValueInput.createByReal(.4),n.FeatureOperations.NewBodyFeatureOperation)
   body=ext.bodies.item(0);face=max(tuple(body.faces),key=lambda f:f.pointOnFace.z)
   s=settings.FinishingSettings(kind=kind,text='TEST',depth_mm=1,width_mm=12,length_mm=20)
   before=(root.bRepBodies.count,design.timeline.count)
   if kind=='notch':
    for side in ('top','bottom','left','right'):
     candidate=a.prepare(design,(face,),replace(s,edge_side=side));assert candidate.results[0].isSolid and candidate.results[0].volume<body.volume
   p=a.prepare(design,(face,),s)
   assert (root.bRepBodies.count,design.timeline.count)==before
   assert p.results[0].isSolid and p.results[0].lumps.count==1
   anchor=store.apply(p);assert root.bRepBodies.count==before[0]
   record=store.read(design,anchor,kind);edited=store.prepare_edit(design,record,replace(s,depth_mm=1.2));store.apply(edited)
   assert root.bRepBodies.count==before[0]
   if kind in ('text','arrow','scale'):
    record=store.read(design,anchor,kind);changed=store.prepare_edit(design,record,replace(record.settings,mode='emboss'));store.apply(changed)
    assert root.bRepBodies.count==before[0]
   report.append({'kind':kind,'ok':True,'volume':body.volume})
  except Exception:report.append({'kind':kind,'ok':False,'error':traceback.format_exc()})
  finally:
   if doc:doc.close(False)
   if caller and caller.isValid:caller.activate()
 path=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier/output/finishing-native.json');path.write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report))
