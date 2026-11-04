"""Stage runtime-only payload and build the Windows installer with Inno Setup 6+."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {'.git', '.vscode', '__pycache__', '.pytest_cache'}
EXTENSIONS = {'.py', '.manifest', '.html', '.css', '.js', '.json', '.svg', '.png', '.ico', '.jpg', '.jpeg', '.woff', '.woff2'}


def payload_files(source):
    """Only the self-contained add-in; never package caches or local editor files."""
    for file in sorted(source.rglob('*')):
        relative = file.relative_to(source)
        if file.is_file() and not any(p in EXCLUDED_DIRS for p in relative.parts) and file.suffix.lower() in EXTENSIONS:
            if file.is_symlink():
                raise ValueError('Do not package symbolic links: ' + str(file))
            yield file, relative


def build(compiler):
    source = ROOT / 'Partelier'
    manifest = json.loads((source / 'Partelier.manifest').read_text(encoding='utf8'))
    version = manifest['version']
    if not manifest['runOnStartup']:
        raise ValueError('Release must register its launcher at Fusion startup.')
    out = ROOT / 'dist'
    out.mkdir(exist_ok=True)
    work = ROOT / 'output' / 'installer'
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='payload-', dir=work) as temp:
        payload = Path(temp) / 'Partelier'
        payload.mkdir()
        for file, relative in payload_files(source):
            destination = payload / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, destination)
        shutil.copy2(source / 'partelier' / 'resources' / 'launcher' / 'Partelier.ico', payload / 'Partelier.ico')
        (payload / '.partelier-installer').write_text('Partelier installer owns this directory. Version ' + version + '\n', encoding='utf8')
        (payload / 'INSTALLATION.txt').write_text((ROOT / 'installer' / 'finished.txt').read_text(), encoding='utf8')
        inventory = {str(p.relative_to(payload)).replace('\\','/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(payload.rglob('*')) if p.is_file()}
        (work / 'payload.json').write_text(json.dumps({'version': version, 'files': inventory}, indent=2), encoding='utf8')
        archive = out / f'Partelier-{version}-Windows.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
            for path in sorted(payload.rglob('*')):
                if path.is_file():
                    zipped.write(path, Path('Partelier') / path.relative_to(payload))
        subprocess.run([str(compiler), '/Q', '/DAppVersion='+version, '/DPayloadDir='+str(payload), '/O'+str(out), str(ROOT/'installer'/'Partelier.iss')], check=True)
    exe = out / f'Partelier-{version}-Windows-Setup.exe'
    checksums = out / f'Partelier-{version}-SHA256SUMS.txt'
    checksums.write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n' for path in (exe, archive)), encoding='ascii')
    print(json.dumps({'version': version, 'installer': str(exe), 'zip': str(archive), 'sha256sums': str(checksums)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iscc', default=os.environ.get('ISCC', shutil.which('ISCC.exe')), help='Path to the Inno Setup compiler')
    args = parser.parse_args()
    if not args.iscc or not Path(args.iscc).is_file():
        parser.error('Install Inno Setup 6 or later and provide --iscc or ISCC.')
    build(Path(args.iscc).resolve())
