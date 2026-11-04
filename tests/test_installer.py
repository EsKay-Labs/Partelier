"""Distribution excludes development and generated Python state."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('partelier_installer',Path(__file__).resolve().parents[1]/'tools/build_installer.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class InstallerPayloadTests(unittest.TestCase):
    def test_runtime_whitelist_excludes_editor_cache_and_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)
            names=['Partelier.py','Partelier.manifest','partelier/ui/palette.html','partelier/resources/32x32.png',
                   '__pycache__/Partelier.pyc','.vscode/settings.json','.env','notes.log','partelier/private.key']
            for name in names:
                p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('test')
            included={str(relative).replace('\\','/') for _,relative in builder.payload_files(source)}
            self.assertEqual(included,set(names[:4]))

    def test_real_payload_has_no_developer_absolute_paths_in_manifest(self):
        source=builder.ROOT/'Partelier';files=list(builder.payload_files(source))
        self.assertTrue(any(relative==Path('Partelier.py') for _,relative in files))
        self.assertTrue(any(relative==Path('Partelier.manifest') for _,relative in files))
        self.assertTrue(all('__pycache__' not in relative.parts for _,relative in files))
