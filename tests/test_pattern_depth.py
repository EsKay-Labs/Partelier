"""Identical wall rays are reused without losing curved/local depth refusals."""

from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

from Partelier.partelier.tools.patterns import fusion
from Partelier.partelier.tools.patterns.settings import PatternSettings


class PatternDepthTests(unittest.TestCase):
    def cell(self,normals):
        samples=tuple(N(point_mm=(index,0,0),normal=normal) for index,normal in enumerate(normals))
        return N(center=samples[0],samples=samples)

    def test_identical_planar_engrave_rays_are_only_measured_once(self):
        cell=self.cell(((0,0,1),)*3)
        with patch.object(fusion,'_wall',return_value=(3,float('inf'))) as wall:
            depth,center=fusion._cell_depth(None,None,cell,PatternSettings(mode='engrave'))
        self.assertEqual(wall.call_count,3)
        self.assertGreater(depth,3)
        self.assertEqual(center,(3,float('inf')))

    def test_differing_curved_normals_keep_their_local_wall_measurement(self):
        cell=self.cell(((0,0,1),(0,0,1),(.1,0,.994987437)))
        with patch.object(fusion,'_wall',return_value=(3,float('inf'))) as wall:
            fusion._cell_depth(None,None,cell,PatternSettings(mode='engrave'))
        self.assertEqual(wall.call_count,4)
        self.assertEqual(wall.call_args.args[-1],cell.samples[-1].normal)

    def test_curved_local_thin_wall_still_refuses_engraving(self):
        cell=self.cell(((0,0,1),(.1,0,.994987437)))
        with patch.object(fusion,'_wall',side_effect=((3,float('inf')),(3,float('inf')),(.5,float('inf')))):
            with self.assertRaisesRegex(ValueError,'first wall exit'):
                fusion._cell_depth(None,None,cell,PatternSettings(mode='engrave',depth_mm=1))

    def test_through_mode_still_measures_every_original_witness(self):
        cell=self.cell(((0,0,1),)*3)
        with patch.object(fusion,'_wall',return_value=(3,float('inf'))) as wall:
            fusion._cell_depth(None,None,cell,PatternSettings())
        self.assertEqual(wall.call_count,3)

    def test_louver_thickness_checks_reuse_the_original_wall_witnesses(self):
        cell=self.cell(((0,0,1),)*3)
        settings=PatternSettings(pattern='grille_louver',layout_mode='fill')
        with patch.object(fusion,'_wall',side_effect=((3,float('inf')),(3.01,float('inf')),(3,float('inf')))) as wall:
            depth,_=fusion._cell_depth(None,None,cell,settings)
        self.assertEqual(wall.call_count,len(cell.samples))
        self.assertGreater(depth,3.01)

    def test_louver_variable_thickness_and_second_wall_are_still_refused(self):
        cell=self.cell(((0,0,1),)*3)
        settings=PatternSettings(pattern='grille_louver',layout_mode='fill')
        with patch.object(fusion,'_wall',side_effect=((3,float('inf')),(3.021,float('inf')),(3,float('inf')))):
            with self.assertRaisesRegex(ValueError,'constant-thickness'):
                fusion._cell_depth(None,None,cell,settings)
        with patch.object(fusion,'_wall',return_value=(3,3.005)):
            with self.assertRaisesRegex(ValueError,'another wall'):
                fusion._cell_depth(None,None,cell,settings)


if __name__=='__main__':unittest.main()
