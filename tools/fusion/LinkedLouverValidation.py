"""Temporary BRep linked louver tests; no caller geometry changes."""
def run(context):
 import adsk.core as c,adsk.fusion as n,sys,importlib,json,traceback
 from pathlib import Path
 from dataclasses import replace
 app=c.Application.get();assert app.userInterface.activeCommand in ('','SelectCommand')
 prefix=next(k.rsplit('.',1)[0] for k in sys.modules if k.endswith('partelier.addin'))
 for name in ('linked_louver','settings'):
  key=prefix+'.tools.mechanisms.'+name
  if key in sys.modules:importlib.reload(sys.modules[key])
 module=importlib.import_module(prefix+'.tools.mechanisms.linked_louver');settings=importlib.import_module(prefix+'.tools.mechanisms.settings')
 report={'ok':False,'fusion_version':app.version}
 try:
  s=settings.MechanismSettings(family='linked_louver',length_mm=80,width_mm=100,height_mm=18,wall_mm=2,clearance_mm=.3,pin_diameter_mm=3,count=5,angle_deg=30,assembly_layout='assembled')
  manager=n.TemporaryBRepManager.get();bodies,names=module.build(s,c,n,manager)
  assert len(bodies)==8 and all(b.isTemporary and b.isSolid and b.lumps.count==1 for b in bodies)
  report['bodies']=list(names);report['motion']=module.motion(s,c,n,manager);report['print_layout']=module.print_check(s,c,n,manager);report['ok']=True
 except Exception:report['error']=traceback.format_exc()
 path=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier/output/linked-louver-native.json');path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
