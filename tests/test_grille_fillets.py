"""Exact dense apertures and bounded shared loft/shear fillet contours."""

from dataclasses import replace
import math
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

from Partelier.partelier.tools.patterns import dense_grid,raised_grilles,grilles,fillet
from Partelier.partelier.tools.patterns import fusion,prism,perforated_prism,rounded_prism,profile_loft,clipping
from Partelier.partelier.tools.patterns.flat_plate import Plate
from Partelier.partelier.tools.patterns.planner import Cell,Layout
from Partelier.partelier.tools.patterns.settings import PatternSettings


FRAME=N(origin_mm=(0.,0.,0.),x_axis=(1.,0.,0.),y_axis=(0.,1.,0.),z_axis=(0.,0.,1.))


class Chart:
    def __init__(self,bounds=(-20,20,-15,15)):self.bounds=bounds
    def sample(self,u,v):return N(point_mm=(u,0.,v),normal=FRAME.y_axis,tangent_u=FRAME.x_axis,tangent_v=FRAME.z_axis)


class GrilleFilletTests(unittest.TestCase):
    def settings(self,**values):
        return PatternSettings(**{'pattern':'grille_cross','layout_mode':'fill','pitch_mm':7,'web_mm':2,
            'border_mm':7,'pattern_fillet_mm':.25,**values})

    def test_dense_plan_uses_exact_rounded_area_and_keeps_opening_count_and_phase(self):
        settings=self.settings()
        plain=dense_grid.plan(replace(settings,pattern_fillet_mm=0),(-10,10,-10,10))
        rounded=dense_grid.plan(settings,(-10,10,-10,10))
        self.assertEqual(rounded.layout,plain.layout)
        self.assertLess(rounded.opening_area_mm2,plain.opening_area_mm2)
        expected=math.fsum(fillet.profile(cell.polygon_mm,.25).area_mm2 for cell in plain.layout.cells)
        self.assertAlmostEqual(rounded.opening_area_mm2,expected)
        with self.assertRaisesRegex(ValueError,'too large'):
            dense_grid.plan(self.settings(pattern_fillet_mm=2),(-10,10,-10,10))

    def test_dense_fillet_preflight_precedes_native_source_copy_and_wall_queries(self):
        chart=Chart((-10,10,-10,10));native=N(TemporaryBRepManager=N(get=lambda:object()))
        with patch.object(fusion,'_api',return_value=(None,native)),patch.object(grilles,'prepare_louver_face'),\
                patch.object(fusion,'SurfaceMap',return_value=chart),patch.object(fusion,'_copy') as copy,patch.object(fusion,'_wall') as wall:
            with self.assertRaisesRegex(ValueError,'too large'):
                dense_grid.prepare(None,(object(),),self.settings(pattern_fillet_mm=2),None,(),{},0)
        copy.assert_not_called();wall.assert_not_called()

    def test_dense_dispatches_one_exact_body_for_all_rounded_windows(self):
        chart=Chart((-10,10,-10,10));source=N(volume=1.2,kind='source')
        def solid(volume,kind):return N(volume=volume,kind=kind,isValid=True,isSolid=True,lumps=N(count=1))
        def copy(manager,body):return solid(body.volume,'result' if body is source else body.kind)
        def polygon(frame,points,low,high):return solid(clipping.area(points)*(high-low)/1000,'air' if high<0 else 'mask')
        def rounded(frame,outer,profiles,low,high):
            return solid((clipping.area(outer)-sum(item.area_mm2 for item in profiles))*(high-low)/1000,'grid')
        def boolean(target,tool,operation):
            if operation=='union':target.volume+=tool.volume
            elif operation=='difference' and target.kind!='air':target.volume-=tool.volume
            return True
        manager=N(booleanOperation=boolean)
        native=N(TemporaryBRepManager=N(get=lambda:manager),BooleanTypes=N(UnionBooleanType='union',DifferenceBooleanType='difference',IntersectionBooleanType='intersection'))
        with patch.object(fusion,'_api',return_value=(None,native)),patch.object(grilles,'prepare_louver_face'),\
                patch.object(fusion,'SurfaceMap',return_value=chart),patch.object(fusion,'_copy',side_effect=copy),\
                patch.object(fusion,'_wall',return_value=(3,None)) as walls,patch.object(prism,'prism',side_effect=polygon),\
                patch.object(rounded_prism,'create',side_effect=rounded) as exact,patch.object(perforated_prism,'create') as sharp,\
                patch.object(fusion,'validate_sources'),patch.object(fusion,'_trace_geometry'):
            prepared=dense_grid.prepare(None,(object(),),self.settings(),source,(),{},0)
        self.assertEqual(exact.call_count,1);sharp.assert_not_called();self.assertEqual(walls.call_count,9)
        profiles=exact.call_args.args[2]
        self.assertEqual(len(profiles),prepared.cell_count)
        self.assertTrue(all(item.radius_mm==.25 for item in profiles))
        self.assertAlmostEqual(prepared.result_body.volume,source.volume-sum(p.area_mm2 for p in profiles)*3/1000)
        self.assertEqual(source.volume,1.2);self.assertEqual(prepared.timings['grid_body_creations'],1)

    def prepare_raised(self,profile='raised',pattern='grille_cross',radius=.4,created=None,angle=20,chamfer=0,height=2,mounted=False):
        source=N(volume=3.6);chart=Chart((-50,50,-40,40)) if mounted else Chart();face=object()
        left,right,bottom,top=chart.bounds
        plate=Plate(face,source,chart,FRAME,((left,bottom),(right,bottom),(right,top),(left,top)),3,(0,0,1))
        hole=((-4,-2),(4,-2),(4,2),(-4,2));cell=Cell((0.,0.),hole)
        layout=Layout((cell,),7,7,'fill',5)
        native=N(TemporaryBRepManager=N(get=lambda:object()),BooleanTypes=N(UnionBooleanType='union'))
        captures=[];plans=[]
        def base(frame,outer,holes,low,high):
            if created is not None:created.append('base')
            captures.append(holes)
            return N(volume=(clipping.area(outer)-sum(clipping.area(h) for h in holes))*(high-low)/1000)
        original_plan=profile_loft.plan
        def plan(*args):plans.append(args);return original_plan(*args)
        def union(manager,target,tool,operation,message):target.volume+=tool.volume
        settings=self.settings(pattern=pattern,grille_profile=profile,grille_height_mm=height,louver_angle_deg=angle,pattern_fillet_mm=radius,grille_chamfer_mm=chamfer)
        if mounted:
            from Partelier.partelier.tools.patterns import mounting
            settings=replace(settings,mount_mode='countersink')
            settings=replace(settings,border_mm=mounting.border_for_screw(settings))
        with patch.object(fusion,'_api',return_value=(None,native)),patch.object(raised_grilles,'build_layout',return_value=layout),\
                patch.object(perforated_prism,'create',side_effect=base) as create,\
                patch.object(perforated_prism,'create_plan',side_effect=lambda plan:N(volume=plan.volume_mm3/1000)),\
                patch.object(profile_loft,'plan',side_effect=plan),patch.object(fusion,'_boolean',side_effect=union),\
                patch.object(fusion,'validate_sources'):
            result=raised_grilles.prepare(None,(face,),settings,source,(),{},0,plate=plate)
        return result,hole,captures,plans

    def test_all_top_bevel_planes_are_45_degrees_independent_of_slat_tilt(self):
        for shape in ('grille_parallel','grille_cross','grille_louver','grille_deflection','grille_diffuser'):
            for tilt in (0,20,45):
                for size in (.2,.65):
                    with self.subTest(shape=shape,tilt=tilt,size=size):
                        result,_,_,args=self.prepare_raised('chamfer',shape,angle=tilt,chamfer=size)
                        bevel=profile_loft.plan(*args[-1])
                        self.assertAlmostEqual(args[-1][-1]-args[-1][-2],size)
                        self.assertEqual(result.timings['chamfer_size_mm'],size)
                        for face in bevel.faces[2:]:
                            a,b,c=(bevel.points_mm[i] for i in face[0][:3])
                            normal=prism._cross(prism._sub(b,a),prism._sub(c,a))
                            vertical=abs(normal[1]);horizontal=math.hypot(normal[0],normal[2])
                            self.assertAlmostEqual(vertical/horizontal,1,places=7)
                        self.assertEqual(result.timings['raised_body_creations'],3)

    def test_external_frame_slopes_from_root_to_top_with_no_vertical_step(self):
        for shape in ('grille_parallel','grille_cross','grille_louver','grille_deflection','grille_diffuser'):
            for height in (.8,3,5):
                result,_,_,segments=self.prepare_raised('chamfer',shape,height=height,angle=45)
                start=result.timings['frame_base_inset_mm']
                self.assertGreaterEqual(start,0)
                self.assertAlmostEqual(result.timings['frame_top_inset_mm']-start,height)
                for args in segments:
                    lower,upper=args[1],args[3];low,high=args[-2:]
                    for i in (0,1):
                        left=min(p[i] for p in lower);right=max(p[i] for p in lower)
                        self.assertAlmostEqual(min(p[i] for p in upper)-left,high-low)
                        self.assertAlmostEqual(right-max(p[i] for p in upper),high-low)
                    self.assertEqual(lower,clipping.offset_convex(((-20,-15),(20,-15),(20,15),(-20,15)),start+low) if start+low else ((-20,-15),(20,-15),(20,15),(-20,15)))
                _,_,_,plain=self.prepare_raised('raised',shape,height=height)
                self.assertEqual(plain[0][1],plain[0][3])

    def test_screw_envelope_is_completely_outside_the_raised_frame_at_every_level(self):
        from Partelier.partelier.tools.patterns import mounting
        for profile in ('raised','chamfer'):
            result,_,_,segments=self.prepare_raised(profile,'grille_louver',mounted=True)
            band=mounting.frame_inset(result.settings)
            for args in segments:
                for contour in (args[1],args[3]):
                    self.assertGreaterEqual(min(p[0] for p in contour),-50+band-1e-8)
                    self.assertLessEqual(max(p[0] for p in contour),50-band+1e-8)
                    self.assertGreaterEqual(min(p[1] for p in contour),-40+band-1e-8)
                    self.assertLessEqual(max(p[1] for p in contour),40-band+1e-8)

    def test_chamfer_size_never_silently_shrinks_or_creates_shapes_before_refusal(self):
        for size in (1,1.5,2):
            created=[]
            with self.subTest(size=size),self.assertRaisesRegex(ValueError,'Rib top bevel'):
                self.prepare_raised('chamfer',chamfer=size,created=created)
            self.assertEqual(created,[])
        settings=self.settings(grille_profile='chamfer',grille_height_mm=2)
        self.assertEqual(raised_grilles.chamfer_size(settings),.5)
        self.assertEqual(raised_grilles.chamfer_size(replace(settings,grille_chamfer_mm=.7)),.7)
        self.assertEqual(raised_grilles.chamfer_size(replace(settings,grille_profile='flat')),0)
        for value in (-.1,21,True,float('nan'),float('inf')):
            with self.subTest(value=value),self.assertRaises(ValueError):replace(settings,grille_chamfer_mm=value)

    def test_raised_chamfer_and_louver_reuse_one_bounded_stroke_for_every_section(self):
        for mode,pattern in (('raised','grille_cross'),('chamfer','grille_cross'),('raised','grille_louver'),('chamfer','grille_louver')):
            with self.subTest(mode=mode,pattern=pattern):
                result,hole,bases,plans=self.prepare_raised(mode,pattern)
                contour=fillet.stroke(fillet.profile(hole,.4),tolerance_mm=.01,max_points=128)
                self.assertEqual(bases,[(contour,)])
                self.assertGreater(len(contour),4);self.assertLessEqual(len(contour),128)
                self.assertEqual(plans[0][2],(contour,))
                for args in plans:
                    low=args[-2];shift=math.tan(math.radians(20))*low if pattern=='grille_louver' else 0
                    for actual,original in zip(args[2][0],contour):
                        self.assertAlmostEqual(actual[0],original[0]);self.assertAlmostEqual(actual[1],original[1]+shift)
                self.assertEqual(result.cell_count,1)

    def test_raised_zero_radius_keeps_original_sharp_contour(self):
        result,hole,bases,plans=self.prepare_raised(radius=0)
        self.assertEqual(bases,[(hole,)]);self.assertEqual(plans[0][2],(hole,))

    def test_raised_invalid_radius_refuses_before_any_native_body_creation(self):
        created=[]
        with self.assertRaisesRegex(ValueError,'too large'):self.prepare_raised(radius=3,created=created)
        self.assertEqual(created,[])

    def test_flat_louver_strokes_before_shear_and_keeps_border_mask_sharp(self):
        context=grilles.LouverFace(((-10,0,-5),(10,0,-5),(10,0,5),(-10,0,5)),(0,0,1))
        native=N(TemporaryBRepManager=N(get=lambda:object()),BooleanTypes=N(IntersectionBooleanType='intersection'))
        hole=((-5,-1),(5,-1),(5,1),(-5,1));cell=N(center=N(point_mm=(0,0,0),tangent_u=FRAME.x_axis,normal=FRAME.y_axis),polygon=hole)
        settings=self.settings(pattern='grille_louver',pattern_fillet_mm=.4)
        with patch.object(fusion,'_api',return_value=(None,native)),patch.object(prism,'prism',return_value=object()) as create,patch.object(fusion,'_boolean'):
            grilles.louver_cutter(cell,settings,3.01,context)
        contour=fillet.stroke(fillet.profile(hole,.4),tolerance_mm=.01,max_points=128)
        self.assertEqual(create.call_count,2)
        self.assertEqual(create.call_args_list[0].args[1],contour)
        shear=create.call_args_list[0].kwargs['shear_xz_per_y']
        self.assertAlmostEqual(shear[0],0);self.assertAlmostEqual(shear[1],-1)
        self.assertEqual(create.call_args_list[1].args[1],((-10.,-5.),(10.,-5.),(10.,5.),(-10.,5.)))
        self.assertFalse(create.call_args_list[1].kwargs)


if __name__=='__main__':unittest.main()
