"""Opposed and four-way fixed grille apertures, spacing and supported profiles."""

from dataclasses import replace
import itertools
import math
from types import SimpleNamespace as N
import unittest

from Partelier.partelier.tools.patterns import clipping,profile_loft
from Partelier.partelier.tools.patterns.grille_styles import flow_uv,NEW_STYLES
from Partelier.partelier.tools.patterns.planner import build_layout
from Partelier.partelier.tools.patterns.settings import PatternSettings
from test_pattern_fit_layout import opening_distance


class FixedGrilleStyleTests(unittest.TestCase):
    def settings(self,pattern='grille_diffuser',**values):
        return PatternSettings(pattern=pattern,layout_mode='fill',pitch_mm=7,web_mm=2,border_mm=7,**values)

    def test_real_spacing_symmetry_convexity_and_all_four_directions(self):
        for pattern,bounds in itertools.product(NEW_STYLES,((-40,40,-30,30),(10,70,20,100))):
            settings=self.settings(pattern);layout=build_layout(settings,bounds)
            self.assertTrue(layout.cells);self.assertLessEqual(layout.cell_count,200)
            if pattern=='grille_diffuser':
                self.assertEqual(layout.cell_count%4,0)
                self.assertEqual({flow_uv(settings,c.center_mm,bounds) for c in layout.cells},{(1,0),(-1,0),(0,1),(0,-1)})
            else:self.assertEqual({flow_uv(settings,c.center_mm,bounds) for c in layout.cells},{(0,1),(0,-1)})
            for cell in layout.cells:
                polygon=cell.polygon_mm
                for a,b,c in zip(polygon,polygon[1:]+polygon[:1],polygon[2:]+polygon[:2]):
                    self.assertGreater((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]),0)
                for u,v in polygon:
                    self.assertTrue(bounds[0]+7-1e-7<=u+cell.center_mm[0]<=bounds[1]-7+1e-7)
                    self.assertTrue(bounds[2]+7-1e-7<=v+cell.center_mm[1]<=bounds[3]-7+1e-7)
            for a,b in itertools.combinations(layout.cells,2):self.assertGreaterEqual(opening_distance(a,b),2-1e-7)

    def test_rotated_opposed_banks_keep_a_full_centre_rib(self):
        for angle in (0,30,90,180):
            settings=self.settings('grille_deflection',rotation_deg=angle)
            layout=build_layout(settings,(-40,40,-30,30));across=(-math.sin(math.radians(angle)),math.cos(math.radians(angle)))
            for cell in layout.cells:
                distances=[(u+cell.center_mm[0])*across[0]+(v+cell.center_mm[1])*across[1] for u,v in cell.polygon_mm]
                self.assertTrue(min(distances)>=1-1e-7 or max(distances)<=-1+1e-7)

    def test_diffuser_is_centred_and_not_an_ignored_rotation_or_offset(self):
        for values in ({'rotation_deg':30},{'offset_u_mm':1},{'offset_v_mm':1}):
            with self.assertRaisesRegex(ValueError,'centred'):self.settings(**values)

    def test_density_refuses_before_any_accept_callback(self):
        seen=[]
        with self.assertRaisesRegex(ValueError,'dense'):
            build_layout(self.settings(),(0,10000,0,10000),accept=lambda c:seen.append(c))
        self.assertFalse(seen)

    def test_raised_four_way_and_opposed_sections_prove_45_degree_sides(self):
        frame=N(origin_mm=(0.,0.,0.),x_axis=(1.,0.,0.),y_axis=(0.,0.,1.),z_axis=(0.,-1.,0.))
        # UV coordinates become frame X/Z directly; the y axis is print height.
        outer=((-40,-30),(40,-30),(40,30),(-40,30))
        for pattern,angle in itertools.product(NEW_STYLES,(0,20,45)):
            settings=self.settings(pattern,louver_angle_deg=angle);layout=build_layout(settings,(-40,40,-30,30))
            holes=tuple(tuple((u+c.center_mm[0],v+c.center_mm[1]) for u,v in c.polygon_mm) for c in layout.cells)
            slopes=[flow_uv(settings,c.center_mm,(-40,40,-30,30)) for c in layout.cells]
            shear=math.tan(math.radians(angle));height=2
            tops=tuple(tuple((u+height*shear*axis[0],v+height*shear*axis[1]) for u,v in loop) for loop,axis in zip(holes,slopes))
            plan=profile_loft.plan(frame,outer,holes,outer,tops,0,height)
            self.assertGreater(plan.volume_mm3,0)
            if angle==45:
                excessive=tuple(tuple((u+4*axis[0],v+4*axis[1]) for u,v in loop) for loop,axis in zip(holes,slopes))
                with self.assertRaisesRegex(ValueError,'45 degrees'):
                    profile_loft.plan(frame,outer,holes,outer,excessive,0,height)
