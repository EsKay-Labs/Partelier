"""Material-export alignment, real grille separation and louver shear bounds."""

from dataclasses import replace
import itertools
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from Partelier.partelier.tools.patterns import colour_export
from Partelier.partelier.tools.patterns import inlay
from Partelier.partelier.tools.patterns import fusion,grilles,prism,surfaces
from Partelier.partelier.tools.patterns.display_mesh import DisplayMesh
from Partelier.partelier.tools.patterns.planner import build_layout
from Partelier.partelier.tools.patterns.prism import plan_prism
from Partelier.partelier.tools.patterns.settings import PatternSettings
from test_pattern_fit_layout import opening_distance


class GrilleTests(unittest.TestCase):
    def settings(self,**values):
        return PatternSettings(**{'pattern':'grille_parallel','layout_mode':'fill','pitch_mm':7,'web_mm':2,'border_mm':3,**values})

    def test_parallel_bands_and_crossed_ribs_preserve_actual_width_and_border(self):
        for pattern,rotation in itertools.product(('grille_parallel','grille_cross'),(0,30,90)):
            settings=self.settings(pattern=pattern,rotation_deg=rotation)
            layout=build_layout(settings,(0,80,0,60))
            self.assertTrue(layout.cells)
            self.assertLessEqual(layout.cell_count,200)
            for cell in layout.cells:
                for u,v in cell.polygon_mm:
                    self.assertTrue(3-1e-7<=u+cell.center_mm[0]<=77+1e-7)
                    self.assertTrue(3-1e-7<=v+cell.center_mm[1]<=57+1e-7)
            for one,two in itertools.combinations(layout.cells,2):
                self.assertGreaterEqual(opening_distance(one,two),2-1e-7)
            if pattern=='grille_parallel':
                direction=(-math.sin(math.radians(rotation)),math.cos(math.radians(rotation)))
                spans=[max(u*direction[0]+v*direction[1] for u,v in cell.polygon_mm)
                       -min(u*direction[0]+v*direction[1] for u,v in cell.polygon_mm) for cell in layout.cells]
                self.assertTrue(any(abs(span-5)<1e-6 for span in spans))

    def test_count_refusal_is_bounded_before_surface_callbacks(self):
        called=[]
        with self.assertRaises(ValueError):
            build_layout(self.settings(pitch_mm=.1,web_mm=.01),(0,1000,0,1000),accept=lambda c:called.append(c))
        self.assertFalse(called)
        with self.assertRaisesRegex(ValueError,'planar'):
            build_layout(self.settings(),(0,100,0,40),100)

    def test_opening_width_edits_change_the_real_grille_geometry(self):
        small=build_layout(self.settings(),(0,80,0,60))
        large=build_layout(self.settings(pitch_mm=12),(0,80,0,60))
        self.assertLess(large.cell_count,small.cell_count)
        self.assertEqual((small.cell_size_mm,large.cell_size_mm),(5,10))
        shifted=build_layout(self.settings(offset_v_mm=2),(0,80,0,60))
        self.assertNotEqual(small.cells,shifted.cells)

    def test_grille_modes_and_angles_cannot_be_silently_reinterpreted(self):
        for values in ({'mode':'inlay'},{'layout_mode':'auto'},{'louver_angle_deg':46},
                       {'louver_angle_deg':True},{'louver_angle_deg':math.nan}):
            with self.subTest(values=values),self.assertRaises(ValueError):self.settings(**values)
        self.assertEqual(self.settings(louver_angle_deg=0).louver_angle_deg,0)

    def test_louver_shear_preserves_closed_volume_and_exact_front_footprint(self):
        frame=NS(origin_mm=(10,20,30),x_axis=(1,0,0),y_axis=(0,1,0),z_axis=(0,0,1))
        footprint=((-10,-2),(10,-2),(10,2),(-10,2))
        for degrees in (0,20,30,45):
            slope=math.tan(math.radians(degrees))
            plan=plan_prism(frame,footprint,-3,0,shear_xz_per_y=(0,slope))
            self.assertAlmostEqual(plan.volume_mm3,240)
            for front,(x,z) in zip(plan.points_mm[4:],footprint):
                self.assertEqual(front,(10+x,20,30+z))
            for back,front in zip(plan.points_mm[:4],plan.points_mm[4:]):
                self.assertAlmostEqual(back[2]-front[2],-3*slope)
                self.assertEqual(back[1]-front[1],-3)
        for shear in ((math.nan,0),(3,0),(0,)):
            with self.assertRaises(ValueError):plan_prism(frame,footprint,-3,0,shear_xz_per_y=shear)

    def test_louver_cutters_reuse_the_face_context_without_remapping_or_wall_queries(self):
        context=grilles.LouverFace(((-10,-5,0),(10,-5,0),(10,5,0),(-10,5,0)),(0,1,0))
        native=NS(TemporaryBRepManager=NS(get=lambda:object()),BooleanTypes=NS(IntersectionBooleanType='intersection'))
        cell=NS(center=NS(point_mm=(0,0,0),tangent_u=(1,0,0),normal=(0,0,1)),polygon=((-5,-1),(5,-1),(5,1),(-5,1)))
        with patch.object(fusion,'_api',return_value=(None,native)),patch.object(prism,'prism',side_effect=lambda *a,**kw:object()) as make,patch.object(fusion,'_boolean'),patch.object(fusion,'_wall') as wall,patch.object(surfaces,'SurfaceMap') as chart:
            for _ in range(5):grilles.louver_cutter(cell,self.settings(pattern='grille_louver'),3.01,context)
        self.assertEqual(make.call_count,10)
        wall.assert_not_called()
        chart.assert_not_called()


class ColourPackageTests(unittest.TestCase):
    def mesh(self,x):
        return DisplayMesh((x,0.,0.,x+1,0.,0.,x,1.,0.),(0.,0.,1.)*3)

    def test_two_parts_share_coordinates_units_and_one_assembly_without_recentering(self):
        ns={'m':colour_export.NS}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'parts.3mf'
            colour_export.write(path,(self.mesh(10),self.mesh(11)))
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(set(archive.namelist()),{'[Content_Types].xml','_rels/.rels','3D/3dmodel.model','Metadata/model_settings.config'})
                root=ET.fromstring(archive.read('3D/3dmodel.model'))
            self.assertEqual(root.attrib['unit'],'millimeter')
            objects=root.findall('m:resources/m:object',ns)
            self.assertEqual([o.attrib['name'] for o in objects],['Base','Pattern colour','Partelier flat colour'])
            self.assertEqual(len(root.findall('.//m:mesh',ns)),2)
            self.assertEqual(len(root.findall('.//m:component',ns)),2)
            self.assertEqual(root.find('m:build/m:item',ns).attrib,{'objectid':'3'})
            self.assertEqual([o.find('m:mesh/m:vertices/m:vertex',ns).attrib['x'] for o in objects[:2]],['100','110'])
            self.assertFalse(list(Path(folder).glob('*.tmp')))

    def test_refused_package_keeps_an_existing_destination_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'parts.3mf';path.write_bytes(b'original')
            with self.assertRaises(ValueError):colour_export.write(path,(self.mesh(0),))
            self.assertEqual(path.read_bytes(),b'original')
            self.assertEqual(list(Path(folder).iterdir()),[path])


class MaterialPartitionTests(unittest.TestCase):
    """An independent finite-volume model checks ownership and complement laws."""
    class Body:
        isValid=True
        isSolid=True
        isTemporary=True

        def __init__(self,voxels):self.voxels=set(voxels)

        @property
        def volume(self):return len(self.voxels)*.01

        @property
        def lumps(self):
            remaining=set(self.voxels);count=0
            while remaining:
                count+=1;pending=[remaining.pop()]
                while pending:
                    point=pending.pop()
                    for axis,delta in itertools.product(range(3),(-1,1)):
                        adjacent=tuple(value+(delta if i==axis else 0) for i,value in enumerate(point))
                        if adjacent in remaining:remaining.remove(adjacent);pending.append(adjacent)
            return NS(count=count)

        @property
        def boundingBox(self):
            low=[min(p[i] for p in self.voxels) for i in range(3)]
            high=[max(p[i]+1 for p in self.voxels) for i in range(3)]
            return NS(minPoint=NS(**dict(zip('xyz',low))),maxPoint=NS(**dict(zip('xyz',high))))

    class Manager:
        def copy(self,body):return MaterialPartitionTests.Body(body.voxels)

        def booleanOperation(self,target,tool,operation):
            if operation=='union':target.voxels|=tool.voxels
            else:target.voxels-=tool.voxels
            return True

    def test_overlapping_same_colour_fragments_form_one_exact_nonoverlapping_partition(self):
        source=self.Body(itertools.product(range(5),range(5),range(3)))
        pieces=(self.Body(((1,1,2),(2,1,2))),self.Body(((2,1,2),(3,1,2))))
        originals=[set(body.voxels) for body in (source,)+pieces]
        base,colour=inlay.partition(self.Manager(),source,pieces,NS(UnionBooleanType='union',DifferenceBooleanType='difference'))
        self.assertEqual(base.voxels|colour.voxels,source.voxels)
        self.assertFalse(base.voxels&colour.voxels)
        self.assertEqual(len(colour.voxels),3)
        self.assertEqual([body.voxels for body in (source,)+pieces],originals)

    def test_exterior_material_and_split_base_are_refused_without_mutating_inputs(self):
        source=self.Body(itertools.product(range(5),range(2),range(3)))
        for points in (((8,0,2),),tuple(itertools.product((2,),range(2),range(3)))):
            piece=self.Body(points);before=set(source.voxels)
            with self.assertRaises(ValueError):
                inlay.partition(self.Manager(),source,(piece,),NS(UnionBooleanType='union',DifferenceBooleanType='difference'))
            self.assertEqual(source.voxels,before)
            self.assertEqual(piece.voxels,set(points))

    def test_partial_native_union_failure_only_mutates_discardable_copies(self):
        class Failed(self.Manager):
            def booleanOperation(self,target,tool,operation):target.voxels.clear();return False
        source=self.Body(itertools.product(range(5),range(5),range(3)))
        pieces=(self.Body(((1,1,2),)),self.Body(((3,1,2),)))
        before=[set(body.voxels) for body in (source,)+pieces]
        with self.assertRaises(ValueError):
            inlay.partition(Failed(),source,pieces,NS(UnionBooleanType='union',DifferenceBooleanType='difference'))
        self.assertEqual([body.voxels for body in (source,)+pieces],before)


if __name__=='__main__':unittest.main()
