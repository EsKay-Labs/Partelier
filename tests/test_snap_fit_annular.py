"""Annular source and primitive protocols; no claims about native CAD or fit."""

from contextlib import contextmanager
from dataclasses import replace
import math
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.snap_fit import annular, fusion


class Collection:
    def __init__(self, values):
        self.values = list(values)
        self.count = len(self.values)

    def item(self, index):
        return self.values[index]


def xyz(x, y, z):
    return SimpleNamespace(x=x, y=y, z=z)


def body(name, root=None, temporary=False, volume=100):
    return SimpleNamespace(isValid=True, isSolid=True, lumps=SimpleNamespace(count=1),
                           volume=float(volume), name=name, entityToken=name, role=name,
                           assemblyContext=None, isTemporary=temporary, parentComponent=root)


def fixture():
    root = object()
    a, b = body("A", root), body("B", root)
    cyl_a = SimpleNamespace(kind="cylinder", origin=xyz(0, 0, 0), axis=xyz(0, 0, 1), radius=1.0)
    cyl_b = SimpleNamespace(kind="cylinder", origin=xyz(0, 0, -.3), axis=xyz(0, 0, -1), radius=1.03)
    fa = SimpleNamespace(kind="face", isValid=True, assemblyContext=None, body=a, area=6.28,
                         geometry=cyl_a, pointOnFace=xyz(1, 0, -.6),
                         evaluator=SimpleNamespace(getNormalAtPoint=lambda point: (True, xyz(1, 0, 0))))
    fb = SimpleNamespace(kind="face", isValid=True, assemblyContext=None, body=b, area=6.47,
                         geometry=cyl_b, pointOnFace=xyz(1.03, 0, -.6),
                         evaluator=SimpleNamespace(getNormalAtPoint=lambda point: (True, xyz(-1, 0, 0))))
    circle = SimpleNamespace(kind="circle", center=xyz(0, 0, 0), normal=xyz(0, 0, 1), radius=1.0)
    edge = SimpleNamespace(kind="edge", isValid=True, body=a, geometry=circle, length=2 * math.pi)
    fa.edges = Collection([edge])
    fb.edges = Collection([])
    return SimpleNamespace(rootComponent=root), fa, fb, edge


def settings(**values):
    return SimpleNamespace(validate=Mock(), snap_family="annular", snap_count=1,
                           chamfer_edges=False, print_support=values.pop("print_support", True),
                           annular_bead_width_mm=values.pop("annular_bead_width_mm", 2.0),
                           annular_bead_height_mm=values.pop("annular_bead_height_mm", .5),
                           annular_offset_mm=values.pop("annular_offset_mm", 3.0),
                           clearance_mm=values.pop("clearance_mm", .3),
                           attachment_overlap_mm=values.pop("attachment_overlap_mm", .5), **values)


class Manager:
    def __init__(self):
        self.cones = []
        self.operations = []
        self.ratios = {"A": 1.0, "B": 1.0}
        self.fail_operation = None

    def createCylinderOrCone(self, start, radius_a, end, radius_b):
        self.cones.append((start, radius_a, end, radius_b))
        length = math.sqrt(sum((getattr(end, axis) - getattr(start, axis)) ** 2 for axis in "xyz"))
        volume = math.pi * length * (radius_a ** 2 + radius_a * radius_b + radius_b ** 2) / 3
        return body("temporary", temporary=True, volume=volume)

    def copy(self, source):
        return body("copy " + source.name, temporary=True, volume=source.volume)

    def booleanOperation(self, target, tool, operation):
        self.operations.append((target, tool, operation))
        if operation == self.fail_operation:
            return False
        if operation == 1:
            target.volume += tool.volume
        elif operation == 2:
            target.volume -= tool.volume
        elif operation == 3:
            target.volume *= self.ratios.get(tool.role, 1.0)
        return True


@contextmanager
def fake_api():
    cast = lambda kind: SimpleNamespace(cast=lambda value: value if getattr(value, "kind", None) == kind else None)
    core = SimpleNamespace(Cylinder=cast("cylinder"), Circle3D=cast("circle"),
                           Point3D=SimpleNamespace(create=xyz))
    native = SimpleNamespace(BRepFace=cast("face"), BRepEdge=cast("edge"),
                             BooleanTypes=SimpleNamespace(UnionBooleanType=1,
                                                          DifferenceBooleanType=2,
                                                          IntersectionBooleanType=3))
    with patch.object(fusion, "_api", return_value=(core, native)), patch.object(
            fusion.hinge, "_body_signature", side_effect=lambda value: value.entityToken + " signature"):
        yield


class AnnularSelectionTests(unittest.TestCase):
    def test_complete_rim_and_opposed_coaxial_cylinders_produce_right_handed_frame(self):
        design, fa, fb, edge = fixture()
        with fake_api():
            result = annular.selection(design, fa, fb, edge)
        self.assertEqual(result[:3], (fa, fb, edge))
        frame = result[3]
        self.assertEqual(frame.origin_mm, (0, 0, 0))
        self.assertEqual(frame.x_axis, (1, 0, 0))
        self.assertEqual(frame.y_axis, (0, 1, 0))
        self.assertEqual(frame.z_axis, (0, 0, 1))
        self.assertAlmostEqual(result[5], 20 * math.pi)
        self.assertLess(frame.point_mm(0, 0, -3)[2], 0)

    def test_circle_normal_and_cylinder_axis_signs_do_not_flip_the_neck(self):
        design, fa, fb, edge = fixture()
        fa.geometry.axis = xyz(0, 0, -1)
        edge.geometry.normal = xyz(0, 0, -1)
        with fake_api():
            frame = annular.selection(design, fa, fb, edge)[3]
        self.assertEqual(frame.z_axis, (0, 0, 1))

    def test_rotated_and_translated_cylinders_keep_local_mm_coordinates(self):
        design, fa, fb, edge = fixture()
        for face, radius, normal in ((fa, 1.0, xyz(0, 1, 0)), (fb, 1.03, xyz(0, -1, 0))):
            face.geometry.origin = xyz(2, 3, 4)
            face.geometry.axis = xyz(1, 0, 0)
            face.pointOnFace = xyz(1.4, 3 + radius, 4)
            face.evaluator.getNormalAtPoint = lambda point, value=normal: (True, value)
        edge.geometry.center = xyz(2, 3, 4)
        edge.geometry.normal = xyz(1, 0, 0)
        with fake_api():
            frame = annular.selection(design, fa, fb, edge)[3]
        self.assertEqual(frame.origin_mm, (20, 30, 40))
        self.assertEqual(frame.z_axis, (1, 0, 0))
        self.assertEqual(frame.x_axis, (0, 1, 0))
        self.assertEqual(frame.point_mm(0, 0, -3), (17, 30, 40))

    def test_wrong_normals_axes_radii_and_reference_types_are_refused(self):
        mutations = (
            lambda fa, fb, edge: setattr(fa.geometry, "kind", "plane"),
            lambda fa, fb, edge: setattr(fb.geometry, "axis", xyz(0, 1, 0)),
            lambda fa, fb, edge: setattr(fb.geometry, "origin", xyz(.1, 0, 0)),
            lambda fa, fb, edge: setattr(fb.geometry, "radius", .99),
            lambda fa, fb, edge: setattr(fb.geometry, "radius", 1.0),
            lambda fa, fb, edge: setattr(fa.evaluator, "getNormalAtPoint", lambda point: (True, xyz(-1, 0, 0))),
            lambda fa, fb, edge: setattr(fb.evaluator, "getNormalAtPoint", lambda point: (True, xyz(1, 0, 0))),
            lambda fa, fb, edge: setattr(edge.geometry, "kind", "arc"),
            lambda fa, fb, edge: setattr(edge.geometry, "radius", .9),
            lambda fa, fb, edge: setattr(edge.geometry, "radius", float("nan")),
            lambda fa, fb, edge: setattr(edge.geometry, "center", xyz(.01, 0, 0)),
            lambda fa, fb, edge: setattr(edge, "length", math.pi),
            lambda fa, fb, edge: setattr(edge, "body", fb.body),
            lambda fa, fb, edge: setattr(fa, "edges", Collection([])),
            lambda fa, fb, edge: setattr(fb, "body", fa.body),
            lambda fa, fb, edge: setattr(fa, "assemblyContext", object()),
            lambda fa, fb, edge: setattr(fa.body, "isTemporary", True),
            lambda fa, fb, edge: setattr(fa.body, "parentComponent", object()),
        )
        for index, mutate in enumerate(mutations):
            design, fa, fb, edge = fixture()
            mutate(fa, fb, edge)
            with self.subTest(index=index), fake_api(), self.assertRaises(ValueError):
                annular.selection(design, fa, fb, edge)


class AnnularGeometryTests(unittest.TestCase):
    def setUp(self):
        self.design, self.fa, self.fb, self.edge = fixture()
        self.manager = Manager()
        self.scope = fake_api()
        self.scope.__enter__()
        self.addCleanup(lambda: self.scope.__exit__(None, None, None))
        self.frame = annular.selection(self.design, self.fa, self.fb, self.edge)[3]
        self.overlap = patch.object(fusion, "_no_positive_overlap")
        self.guard = self.overlap.start()
        self.addCleanup(self.overlap.stop)

    def prepare(self, config=None):
        return annular.prepare_geometry(self.manager, self.frame, self.fa, self.fb, config or settings())

    def test_triangular_bead_two_frustums_and_45_degree_roof_use_correct_mm_boundary(self):
        plan, results = self.prepare()
        self.assertEqual(tuple(role for role, _ in results), ("A", "B"))
        self.assertEqual((self.fa.body.volume, self.fb.body.volume), (100, 100))
        self.assertTrue(all(value.isTemporary and value.isSolid for _, value in results))
        self.assertEqual((plan.radius_a_mm, plan.radius_b_mm), (10, 10.3))
        self.assertAlmostEqual(plan.radial_gap_mm, .3)
        self.assertAlmostEqual(plan.bead_inner_radius_mm, 9.5)
        self.assertAlmostEqual(plan.bead_peak_radius_mm, 10.5)
        self.assertAlmostEqual(plan.groove_radius_mm, 10.8)
        self.assertAlmostEqual(plan.roof_end_z_mm - plan.groove_end_z_mm,
                               plan.groove_radius_mm - plan.groove_inner_radius_mm)
        unequal = [(round(start.z, 5), round(ra, 5), round(end.z, 5), round(rb, 5))
                   for start, ra, end, rb in self.manager.cones if ra != rb]
        self.assertEqual(unequal, [(-.4, 1.0, -.3, 1.05), (-.3, 1.05, -.2, 1.0),
                                   (-.17, 1.08, -.09, 1.0)])
        self.assertEqual(self.guard.call_count, 2)
        self.assertEqual(self.guard.call_args_list[0].args, (self.manager, self.fa.body, self.fb.body))
        self.assertEqual(self.guard.call_args_list[1].args, (self.manager, results[0][1], results[1][1]))
        self.assertFalse(any(target is source for target, _, _ in self.manager.operations
                             for source in (self.fa.body, self.fb.body)))

    def test_attachment_overlap_does_not_change_the_exposed_bead_profile(self):
        self.prepare(settings(attachment_overlap_mm=.2))
        profile = [(start.z, ra, end.z, rb) for start, ra, end, rb in self.manager.cones if ra != rb]
        self.manager.cones.clear()
        self.prepare(settings(attachment_overlap_mm=.7))
        second = [(start.z, ra, end.z, rb) for start, ra, end, rb in self.manager.cones if ra != rb]
        self.assertEqual(profile, second)

    def test_support_off_keeps_flat_groove_and_omits_the_roof_cone(self):
        plan, _ = self.prepare(settings(print_support=False))
        self.assertEqual(plan.roof_end_z_mm, plan.groove_end_z_mm)
        self.assertEqual(sum(ra != rb for _, ra, _, rb in self.manager.cones), 2)

    def test_full_annular_root_and_socket_coverage_are_required_before_source_copies(self):
        for role in ("A", "B"):
            manager = Manager()
            manager.ratios[role] = .98
            with self.subTest(role=role), patch.object(manager, "copy", wraps=manager.copy) as copying:
                with self.assertRaisesRegex(ValueError, "entire ring"):
                    annular.prepare_geometry(manager, self.frame, self.fa, self.fb, settings())
                copying.assert_not_called()
                self.assertEqual((self.fa.body.volume, self.fb.body.volume), (100, 100))

    def test_socket_coverage_preserves_radial_wall_and_both_axial_lands(self):
        self.prepare()
        witnesses = [(start, ra, end, rb) for start, ra, end, rb in self.manager.cones
                     if abs(ra - 1.11) < 1e-9 and abs(rb - 1.11) < 1e-9]
        self.assertEqual(len(witnesses), 1)
        start, _, end, _ = witnesses[0]
        self.assertAlmostEqual(start.z, -.46)
        self.assertAlmostEqual(end.z, -.06)

    def test_invalid_dimensions_count_finish_and_gap_do_not_create_geometry(self):
        changes = ({"snap_count": 2}, {"snap_count": True}, {"chamfer_edges": True},
                   {"snap_family": "hook"}, {"annular_bead_height_mm": .3},
                   {"annular_bead_width_mm": 0}, {"attachment_overlap_mm": 10},
                   {"clearance_mm": float("nan")}, {"annular_offset_mm": float("inf")})
        for values in changes:
            config = settings()
            config.__dict__.update(values)
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.prepare(config)
            self.assertEqual(self.manager.cones, [])

    def test_failed_intersection_or_primitive_never_mutates_sources(self):
        self.manager.fail_operation = 3
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual((self.fa.body.volume, self.fb.body.volume), (100, 100))
        with patch.object(self.manager, "createCylinderOrCone", return_value=None):
            with self.assertRaises(ValueError):
                self.prepare()

    def test_mismatched_frame_is_refused_before_geometry_creation(self):
        frame = replace(self.frame, origin_mm=(1, 0, 0))
        with self.assertRaisesRegex(ValueError, "frame"):
            annular.prepare_geometry(self.manager, frame, self.fa, self.fb, settings())
        self.assertEqual(self.manager.cones, [])


if __name__ == "__main__":
    unittest.main()
