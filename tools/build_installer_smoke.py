"""Install, upgrade and uninstall ONLY in an isolated TEMP test folder."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[1]


def main(exe):
    parent=Path(tempfile.gettempdir()).resolve()/'PartelierInstallerTest'/uuid.uuid4().hex
    target=parent/'Partelier'
    parent.mkdir(parents=True)
    assert target.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()/'PartelierInstallerTest')
    output=ROOT/'output'/'installer';output.mkdir(parents=True,exist_ok=True)
    expected=json.loads((output/'payload.json').read_text(encoding='utf8'))
    base=['/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/TESTINSTALL','/DIR='+str(target)]
    process_list=subprocess.run(['tasklist','/FI','IMAGENAME eq Fusion360.exe','/FO','CSV'],capture_output=True,text=True,check=True).stdout
    fusion_guard_checked='fusion360.exe' in process_list.lower()
    if fusion_guard_checked:
        blocked=subprocess.run([str(exe),*base,'/CHECKFUSION','/LOG='+str(output/'fusion-running-refusal.log')],timeout=90)
        assert blocked.returncode!=0 and not target.exists()
        assert 'Save your work and close Autodesk Fusion' in (output/'fusion-running-refusal.log').read_text(encoding='utf-8-sig')
    def invoke(program,args,label):
        result=subprocess.run([str(program),*args,'/LOG='+str(output/(label+'.log'))],timeout=90)
        if result.returncode!=0:raise RuntimeError(f'{label} exit {result.returncode}; see output/installer/{label}.log')
    def verify():
        for name,sha in expected['files'].items():
            path=target/name
            assert path.is_file(),name
            assert hashlib.sha256(path.read_bytes()).hexdigest()==sha,name
        assert not any(p.name in ('__pycache__','.vscode') for p in target.rglob('*'))
    invoke(exe,base,'install');verify()
    sentinel=target/'user-owned-note.txt';sentinel.write_text('Preserve user additions.',encoding='utf8')
    invoke(exe,base,'upgrade');verify();assert sentinel.read_text()=='Preserve user additions.'
    uninstaller=target/'unins000.exe';assert uninstaller.is_file()
    invoke(uninstaller,['/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/TESTINSTALL'],'uninstall')
    assert not (target/'Partelier.py').exists()
    assert not (target/'Partelier.manifest').exists()
    assert not (target/'.partelier-installer').exists()
    assert sentinel.read_text()=='Preserve user additions.'
    # Unowned directories are refused rather than silently taken over.
    result=subprocess.run([str(exe),*base,'/LOG='+str(output/'unowned-refusal.log')],timeout=90)
    assert result.returncode!=0 and not (target/'Partelier.py').exists()
    assert sentinel.read_text()=='Preserve user additions.'
    report={'success':True,'version':expected['version'],'payload_files':len(expected['files']),
        'isolated_target':str(target),'current_fusion_addins_untouched':True,
        'checks':['Install with exact payload hashes','Upgrade preserves user-added files',
                  'Uninstall removes installed runtime','Uninstall preserves user-added files',
                  'Unowned directory refused'],
        'installer_sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}
    report['running_fusion_refusal_tested']=fusion_guard_checked
    (output/'smoke.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('installer',type=Path)
    main(parser.parse_args().installer.resolve())
