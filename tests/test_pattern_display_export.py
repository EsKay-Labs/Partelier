"""Exporter ownership, cleanup and a guard against the failed native API path."""

import ast
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock,patch
import weakref

from Partelier.partelier.tools.patterns import display_export as display
from tests.test_pattern_display_mesh import binary_stl


class ExportDisplayTests(unittest.TestCase):
    def fixture(self,fail=False):
        timeline=NS(count=0,markerPosition=0);bodies=NS(count=0);state=NS(options=None,path=None)
        class Managed:
            isTemporary=False
            @property
            def meshManager(self):raise AssertionError('Failed native meshing path accessed')
        managed=Managed()
        feature=NS(isValid=True,startEdit=lambda:True,finishEdit=lambda:True,bodies=NS(count=1,item=lambda i:managed))
        def delete():
            self.assertIsNone(state.options(), 'Release export options before removing their native body')
            feature.isValid=False;timeline.count=0;timeline.markerPosition=0;bodies.count=0;return True
        feature.deleteMe=Mock(side_effect=delete)
        def add_feature():timeline.count=1;timeline.markerPosition=1;return feature
        def add_body(source,owner):bodies.count=1;return managed
        bodies.add=add_body
        class Options:pass
        def create(geometry,filename):
            self.assertIs(geometry,managed);option=Options();option.filename=filename
            state.options=weakref.ref(option);state.path=Path(filename);return option
        def execute(option):
            self.assertEqual(option.unitType,'cm');self.assertFalse(option.sendToPrintUtility)
            if fail:raise ValueError('export failed')
            state.path.write_bytes(binary_stl([((0,0,0),(1,0,0),(0,1,0))]));return True
        design=NS(timeline=timeline,rootComponent=NS(bRepBodies=bodies,features=NS(baseFeatures=NS(add=add_feature))),
            exportManager=NS(createSTLExportOptions=create,execute=execute))
        native=NS(DistanceUnits=NS(CentimeterDistanceUnits='cm'),MeshRefinementSettings=NS(MeshRefinementMedium='medium'))
        return design,feature,state,native

    def test_export_copy_and_file_are_removed_and_options_released_before_body(self):
        design,feature,state,native=self.fixture()
        with patch.object(display.hinge,'_api',return_value=(None,native)):
            mesh=display.capture(design,object())
        self.assertEqual(mesh.triangle_count,1)
        self.assertFalse(state.path.parent.exists())
        feature.deleteMe.assert_called_once_with()
        self.assertEqual((design.timeline.count,design.rootComponent.bRepBodies.count),(0,0))

    def test_export_failure_removes_owned_geometry_and_temporary_files(self):
        design,feature,state,native=self.fixture(fail=True)
        with patch.object(display.hinge,'_api',return_value=(None,native)):
            with self.assertRaisesRegex(ValueError,'export failed'):display.capture(design,object())
        feature.deleteMe.assert_called_once_with()
        self.assertFalse(state.path.parent.exists())

    def test_export_route_cannot_access_the_failed_mesh_calculator_api(self):
        root=Path(__file__).parents[1]
        for relative in ('Partelier/partelier/tools/patterns/display_export.py',
                         'tools/fusion/PatternDisplayProbe/PatternDisplayProbe.py'):
            tree=ast.parse((root/relative).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node,ast.Attribute):
                    self.assertNotIn(node.attr,{'meshManager','createMeshCalculator'},relative)


if __name__=='__main__':unittest.main()
