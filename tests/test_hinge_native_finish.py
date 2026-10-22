"""Native finish classification and bounded ownership cleanup; no kernel claims."""

import math
from types import SimpleNamespace
import copy
import unittest
from unittest.mock import patch

from Partelier.partelier.tools.hinge import fusion, native_finish
from Partelier.partelier.tools.hinge.settings import HingeSettings
from Partelier.partelier.tools.hinge.planner import build_hinge_plan


class Items:
    def __init__(self, values=()):
        self.values = list(values)

    @property
    def count(self):
        return len(self.values)

    def item(self, index):
        return self.values[index]

    def add(self, item):
        self.values.append(item)
        return True


class Point:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


class AnalyticCurve:
    def __init__(self, kind="line", *, center=(0, 0, 0), normal=(0, 0, 1), radius=1):
        self.kind = kind
        self.center = Point(*center)
        self.normal = Point(*normal)
        self.radius = radius

    def copy(self):
        return copy.deepcopy(self)

    def getParameterAtPoint(self, point):
        raise AssertionError("Routine curve rejection must never call the native nearest-parameter API.")


def analytic_types():
    return {name: SimpleNamespace(cast=lambda geometry, kind=kind:
                geometry if getattr(geometry, "kind", None) == kind else None)
            for name, kind in (("Line3D", "line"), ("Circle3D", "circle"), ("Arc3D", "arc"))}


class Edge:
    isDegenerate = False

    @property
    def tangentiallyConnectedEdges(self):
        return Items(getattr(self, "connected_edges", (self,)))

    def __init__(self, normals=((1, 0, 0), (0, 0, 1))):
        self.faces = Items(SimpleNamespace(evaluator=SimpleNamespace(
            getNormalAtPoint=lambda point, normal=normal: (True, Point(*normal))),
            isParamReversed=True) for normal in normals)
        self.coEdges = Items((None, None))
        self.geometry = AnalyticCurve()
        self.evaluator = SimpleNamespace(getParameterExtents=lambda: (True, -.1, .1),
                                         getPointAtParameter=lambda value: (True, Point(0, value, 0)))


class Body:
    isValid = True
    isSolid = True
    lumps = SimpleNamespace(count=1)

    def __init__(self, temporary=True, volume=1):
        self.isTemporary = temporary
        self.volume = volume
        self.name = "original"
        self.edges = Items((Edge(),))
        self.edges.item(0).body = self
        self.owner = None

    def pointContainment(self, point):
        return "inside" if point.x < 0 and point.z < 0 else "outside"

    def deleteMe(self):
        self.owner.values.remove(self)
        self.isValid = False
        return True


class Bodies(Items):
    def add(self, raw, base=None):
        copied = Body(False, raw.volume)
        copied.owner = self
        self.values.append(copied)
        if base is not None:
            base.bodies.values.append(copied)
        return copied

    def itemByName(self, name):
        return next((body for body in self.values if body.name == name), None)


class Feature:
    isValid = True
    healthState = "healthy"
    errorOrWarningMessage = "native failure"

    def __init__(self, host, body):
        self.host = host
        self.bodies = Items((body,))
        body.volume -= .1
        self.fail_delete = False

    def deleteMe(self):
        if self.fail_delete:
            return False
        self.bodies.item(0).volume += .1
        self.host.records.remove(self)
        self.isValid = False
        return True


class Base:
    isValid = True

    def __init__(self, host):
        self.host = host
        self.bodies = Items()

    def startEdit(self):
        return True

    def finishEdit(self):
        if getattr(self.host, "reverse_base", False):
            self.bodies.values.reverse()
        return True

    def deleteMe(self):
        for body in tuple(self.bodies.values):
            body.deleteMe()
        self.host.records.remove(self)
        self.isValid = False
        return True


class NativeCollection:
    def __init__(self, host):
        self.host = host
        self.calls = []
        self.feature_inputs = []
        self.fail_on = None
        self.warning = False
        self.fail_cleanup = False

    def createInput(self):
        def edge_set(edges, radius, tangent):
            self.calls.append((tuple(edges.values), radius, tangent))
            self.edges = edges
            return SimpleNamespace()
        return SimpleNamespace(edgeSetInputs=SimpleNamespace(addConstantRadiusEdgeSet=edge_set))

    def createInput2(self):
        result = self.createInput()
        return SimpleNamespace(chamferEdgeSets=SimpleNamespace(
            addEqualDistanceChamferEdgeSet=lambda *args: bool(result.edgeSetInputs.addConstantRadiusEdgeSet(*args))))

    def add(self, feature_input):
        self.feature_inputs.append(feature_input)
        if len(self.calls) == self.fail_on:
            raise RuntimeError("kernel failure")
        feature = Feature(self.host, self.edges.item(0).body)
        self.host.completed += 1
        if self.warning:
            feature.healthState = "warning"
        feature.fail_delete = self.fail_cleanup
        self.host.records.append(feature)
        return feature


class Features:
    def __init__(self, root):
        self.root = root
        self.records = []
        self.pending = []
        self.completed = 0
        self.filletFeatures = NativeCollection(self)
        self.chamferFeatures = NativeCollection(self)
        self.baseFeatures = SimpleNamespace(add=self.add_base)

    @property
    def count(self):
        return len(self.records)

    def add_base(self):
        base = Base(self)
        self.records.append(base)
        return base


class Timeline:
    def __init__(self, features):
        self.features = features

    @property
    def count(self):
        return self.features.count

    @property
    def markerPosition(self):
        return self.count


class Host:
    def __init__(self, parametric=True, roles=("A",)):
        self.root = SimpleNamespace(bRepBodies=Bodies((Body(False),)))
        self.original = self.root.bRepBodies.item(0)
        self.root.features = Features(self.root)
        self.root.features.pending = roles
        self.design = SimpleNamespace(rootComponent=self.root, timeline=Timeline(self.root.features),
                                      designType="parametric" if parametric else "direct")
        self.manager = SimpleNamespace(copy=lambda body: Body(True, body.volume))
        self.inputs = tuple((role, Body()) for role in roles)
        self.frame = fusion.HingeFrame((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
        self.core = SimpleNamespace(Point3D=SimpleNamespace(create=Point),
                                    ObjectCollection=SimpleNamespace(create=Items),
                                    ValueInput=SimpleNamespace(createByReal=lambda value: value),
                                    **analytic_types())
        self.api = SimpleNamespace(DesignTypes=SimpleNamespace(ParametricDesignType="parametric"),
                                   PointContainment=SimpleNamespace(PointInsidePointContainment="inside",
                                       PointOutsidePointContainment="outside", PointOnPointContainment="on"),
                                   FeatureHealthStates=SimpleNamespace(HealthyFeatureHealthState="healthy"),
                                   ChamferCornerTypes=SimpleNamespace(MiterCornerType="miter"))

    def run(self, *, fillet=True):
        settings = HingeSettings(output_mode="separate", web_profile="flat", fillet_edges=fillet, chamfer_edges=not fillet)
        with patch.object(fusion, "_api", return_value=(self.core, self.api)):
            return native_finish.finish_native_results(self.design, self.manager, self.frame,
                                                       settings, self.inputs)


class ClassifierTests(unittest.TestCase):
    def test_convex_concave_and_bore_mouth_are_distinguished(self):
        normals = ((1, 0, 0), (0, 0, 1))
        corner = lambda p: "inside" if p[0] <= 0 and p[2] <= 0 else "outside"
        recess = lambda p: "inside" if p[0] <= 0 or p[2] <= 0 else "outside"
        self.assertEqual(native_finish.classify_edge_point((0, 0, 0), *normals, corner, .001), "convex")
        self.assertEqual(native_finish.classify_edge_point((0, 0, 0), *normals, recess, .001), "concave")
        drilled = lambda p: "inside" if p[2] <= 0 and math.hypot(p[0], p[1]) >= 1 else "outside"
        self.assertEqual(native_finish.classify_edge_point((1, 0, 0), (0, 0, 1), (-1, 0, 0), drilled, .001), "convex")

    def test_rotation_reflection_and_nonright_convex_corners(self):
        for angle in (.2, .6, 1.3, 2.4):
            for sign in (-1, 1):
                one = (math.cos(angle), sign * math.sin(angle), 0)
                two = (math.cos(angle + .7), sign * math.sin(angle + .7), 0)
                point = (4, -7, 3)
                def contains(p):
                    d = tuple(a - b for a, b in zip(p, point))
                    return "inside" if sum(a*b for a,b in zip(d,one)) <= 0 and sum(a*b for a,b in zip(d,two)) <= 0 else "outside"
                self.assertEqual(native_finish.classify_edge_point(point, one, two, contains, .001), "convex")

    def test_tangency_does_not_probe_and_face_order_is_irrelevant(self):
        def must_not_probe(point):
            self.fail("A smooth seam must not be probed or finished.")
        self.assertEqual(native_finish.classify_edge_point((0, 0, 0), (1, 0, 0), (3, 0, 0), must_not_probe, .001), "tangent")
        for normals in (((1, 0, 0), (0, 0, 1)), ((0, 0, 1), (1, 0, 0))):
            self.assertEqual(native_finish.classify_edge_point((0, 0, 0), *normals, lambda p: "outside", .001), "convex")

    def test_tolerance_probes_retry_but_ambiguous_invalid_inputs_fail(self):
        calls = []
        def tolerant(point):
            calls.append(point)
            return "on" if max(abs(value) for value in point) < .002 else "outside"
        self.assertEqual(native_finish.classify_edge_point((0, 0, 0), (1, 0, 0), (0, 0, 1), tolerant, .001), "convex")
        self.assertEqual(len(calls), 4)
        for contains in (lambda p: "unknown", lambda p: "inside" if p[0] > 0 else "outside"):
            with self.assertRaisesRegex(ValueError, "classify"):
                native_finish.classify_edge_point((0, 0, 0), (1, 0, 0), (0, 0, 1), contains, .001)
        for epsilon in (0, -1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                native_finish.classify_edge_point((0, 0, 0), (1, 0, 0), (0, 0, 1), tolerant, epsilon)

    def test_face_evaluator_normals_are_not_flipped_by_surface_orientation(self):
        host = Host()
        edge = host.inputs[0][1].edges.item(0)
        self.assertEqual(native_finish.classify_edge(edge, host.inputs[0][1], host.core, host.api, .6), "convex")
        edge.faces = Items((edge.faces.item(0),))
        self.assertEqual(native_finish.classify_edge(edge, host.inputs[0][1], host.core, host.api, .6), "tangent")

    def test_attached_source_plane_and_generated_bounds_are_respected(self):
        host = Host()
        settings = HingeSettings(fillet_edges=True)
        edge = Edge()
        self.assertFalse(native_finish._eligible(edge, "A", host.frame, settings, None, None))
        edge.evaluator.getPointAtParameter = lambda p: (True, Point(-.1, p, p + .1))
        self.assertTrue(native_finish._eligible(edge, "A", host.frame, settings, None, None))
        edge.evaluator.getPointAtParameter = lambda p: (True, Point(-.1, p, p))
        self.assertFalse(native_finish._eligible(edge, "A", host.frame, settings, None, None))
        edge.evaluator.getPointAtParameter = lambda p: (True, Point(-10, p, .1))
        self.assertFalse(native_finish._eligible(edge, "A", host.frame, settings, None, None))
        self.assertTrue(native_finish._eligible(edge, "pin", host.frame, settings, None, None))


class CurveOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.core = SimpleNamespace(**analytic_types())

    def line(self, start, end):
        edge = Edge()
        edge.evaluator.getParameterExtents = lambda: (True, 0, 1)
        edge.evaluator.getPointAtParameter = lambda fraction: (
            True, Point(*(one * (1 - fraction) + two * fraction for one, two in zip(start, end))))
        return edge

    def arc(self, start_angle, sweep, *, full_circle=False, reflected=False):
        edge = Edge()
        normal = (0, 0, -1) if reflected else (0, 0, 1)
        edge.geometry = AnalyticCurve("circle" if full_circle else "arc",
                                      center=(3, -2, 4), normal=normal, radius=.4)
        edge.evaluator.getParameterExtents = lambda: (True, 0, 1)
        def point(fraction):
            angle = start_angle + sweep * fraction
            return True, Point(3 + (-1 if reflected else 1) * .4 * math.cos(angle),
                               -2 + .4 * math.sin(angle), 4)
        edge.evaluator.getPointAtParameter = point
        return edge

    def test_original_line_snapshot_tracks_trimmed_splits_and_rejects_shifted_or_extended_borders(self):
        for start, end in (((0, -.1, 0), (0, .1, 0)), ((7, -3, 2), (4, 9, -6))):
            edge = self.line(start, end)
            support = native_finish._freeze_curve_support(edge, self.core)
            self.assertIsNot(support.curve, edge.geometry)
            edge.geometry.kind = "ellipse"
            middle = tuple((one + two) / 2 for one, two in zip(start, end))
            for first, second in ((start, middle), (middle, end), (end, middle)):
                self.assertTrue(native_finish._edge_on_support(self.line(first, second), support))
            shifted = tuple(value + .001 for value in middle)
            self.assertFalse(native_finish._edge_on_support(self.line(start, shifted), support))
            extended = tuple(two + (two - one) * .01 for one, two in zip(start, end))
            self.assertFalse(native_finish._edge_on_support(self.line(middle, extended), support))

    def test_all_five_samples_must_match_including_interior_of_new_curved_border(self):
        edge = self.line((0, -.1, 0), (0, .1, 0))
        support = native_finish._freeze_curve_support(edge, self.core)
        curved = self.line((0, -.1, 0), (0, .1, 0))
        curved.evaluator.getPointAtParameter = lambda t: (True, Point(.01 * math.sin(math.pi * t), -.1 + .2 * t, 0))
        self.assertFalse(native_finish._edge_on_support(curved, support))

    def test_arc_trim_handles_wrapped_signed_and_reflected_coordinates_without_native_parameter_queries(self):
        for sweep in (1.2, -1.2, 5.3, -5.3):
            for reflected in (False, True):
                with self.subTest(sweep=sweep, reflected=reflected):
                    edge = self.arc(5.9, sweep, reflected=reflected)
                    support = native_finish._freeze_curve_support(edge, self.core)
                    self.assertTrue(native_finish._edge_on_support(
                        self.arc(5.9 + sweep * .2, sweep * .6, reflected=reflected), support))
                    self.assertFalse(native_finish._edge_on_support(
                        self.arc(5.9 + sweep * .9, sweep * .3, reflected=reflected), support))
                    point = edge.evaluator.getPointAtParameter(.5)[1]
                    self.assertFalse(native_finish._point_on_support((point.x, point.y, point.z + .001), support))
                    radial = (point.x - 3, point.y + 2, 0)
                    off_radius = tuple(origin + value * 1.01 for origin, value in zip((3, -2, 4), radial))
                    self.assertFalse(native_finish._point_on_support(off_radius, support))

    def test_full_circle_membership_uses_plane_and_radius_independent_of_seam(self):
        for sweep in (math.tau, -math.tau):
            support = native_finish._freeze_curve_support(self.arc(.7, sweep, full_circle=True), self.core)
            self.assertTrue(native_finish._edge_on_support(self.arc(4.2, 1.1), support))
            self.assertFalse(native_finish._point_on_support((3, -2, 4), support))

    def test_unsupported_or_inconsistent_original_geometry_refuses_before_finishing(self):
        edge = self.line((0, 0, 0), (0, 1, 0))
        edge.geometry.kind = "ellipse"
        with self.assertRaisesRegex(ValueError, "supported line, circle or arc"):
            native_finish._freeze_curve_support(edge, self.core)
        edge = self.arc(0, 1)
        edge.geometry.radius = .3
        with self.assertRaisesRegex(ValueError, "inconsistent geometry"):
            native_finish._freeze_curve_support(edge, self.core)


class OwnershipTests(unittest.TestCase):
    def assert_clean(self, host):
        self.assertEqual(host.root.bRepBodies.values, [host.original])
        self.assertEqual(host.root.features.count, 0)
        self.assertTrue(host.original.isValid)
        self.assertEqual(host.original.volume, 1)
        self.assertTrue(all(body.isTemporary and body.volume == 1 for _, body in host.inputs))

    def test_both_modes_and_finishes_copy_results_then_restore_owned_model_objects(self):
        for parametric in (False, True):
            for fillet in (False, True):
                with self.subTest(parametric=parametric, fillet=fillet):
                    host = Host(parametric, ("A", "B", "pin"))
                    outputs = host.run(fillet=fillet)
                    self.assertEqual(tuple(role for role, _ in outputs), ("A", "B", "pin"))
                    self.assertTrue(all(body.isTemporary and body.isValid and abs(body.volume - .9) < 1e-12 for _, body in outputs))
                    collection = host.root.features.filletFeatures if fillet else host.root.features.chamferFeatures
                    self.assertEqual(len(collection.calls), 3)
                    self.assertTrue(all(radius == (.06 if fillet else .03) and tangent is False for _, radius, tangent in collection.calls))
                    self.assert_clean(host)

    def test_roof_validation_receives_detached_results_before_final_volume_validation(self):
        host = Host(True, ("A", "B", "pin"))
        calls = []
        def complete(frame, settings, role, raw, finished, **kwargs):
            self.assertTrue(finished.isTemporary)
            self.assertIsNot(finished, raw)
            self.assertAlmostEqual(finished.volume, .9)
            calls.append((role, raw, kwargs["plan"]))
            finished.volume = .95
            return finished
        with patch.object(native_finish, "validate_tangent_roofs", side_effect=complete):
            outputs = host.run()
        self.assertEqual([role for role, _, _ in calls], ["A", "B", "pin"])
        self.assertTrue(all(body.volume == .95 for _, body in outputs))
        self.assert_clean(host)
        host = Host()
        def invalid_complete(frame, settings, role, raw, finished, **kwargs):
            finished.volume = raw.volume + .1
            return finished
        with patch.object(native_finish, "validate_tangent_roofs", side_effect=invalid_complete):
            with self.assertRaisesRegex(ValueError, "unexpected material"):
                host.run()
        self.assert_clean(host)

    def test_base_result_order_is_resolved_by_owned_names(self):
        host = Host(True, ("A", "B", "pin"))
        host.root.features.reverse_base = True
        for index, (_, body) in enumerate(host.inputs):
            body.volume = index + 1
        outputs = host.run()
        self.assertEqual(tuple(role for role, _ in outputs), ("A", "B", "pin"))
        self.assertEqual(tuple(round(body.volume, 8) for _, body in outputs), (.9, 1.9, 2.9))
        self.assertEqual(host.root.features.count, 0)
        self.assertEqual(host.root.bRepBodies.values, [host.original])

    def test_kernel_failure_after_an_earlier_result_cleans_all_owned_objects(self):
        for parametric in (False, True):
            host = Host(parametric, ("A", "B"))
            host.root.features.filletFeatures.fail_on = 2
            with self.assertRaisesRegex(ValueError, "kernel failure"):
                host.run()
            self.assert_clean(host)

    def test_feature_warning_and_bad_transient_copy_refuse_with_cleanup(self):
        host = Host()
        host.root.features.filletFeatures.warning = True
        with self.assertRaisesRegex(ValueError, "native failure"):
            host.run()
        self.assert_clean(host)
        host = Host()
        host.manager.copy = lambda body: Body(True, math.nan)
        with self.assertRaisesRegex(ValueError, "valid solid"):
            host.run()
        self.assert_clean(host)

    def test_cleanup_failure_is_actionable_and_original_body_is_not_deleted(self):
        host = Host(False)
        host.root.features.filletFeatures.fail_cleanup = True
        with self.assertRaisesRegex(ValueError, "abort this command transaction"):
            host.run()
        self.assertTrue(host.original.isValid)
        self.assertEqual(host.original.volume, 1)

    def test_no_eligible_edges_refuses_the_finish_and_cleans_up(self):
        host = Host()
        host.inputs[0][1].edges.item(0).faces.item(1).evaluator.getNormalAtPoint = lambda p: (True, Point(1, 0, 0))
        # Persisted copies receive the same smooth edge for this failure case.
        original_add = host.root.bRepBodies.add
        def add(raw, base=None):
            copied = original_add(raw, base)
            copied.edges = raw.edges
            return copied
        host.root.bRepBodies.add = add
        with self.assertRaisesRegex(ValueError, "No convex generated edges"):
            host.run()
        self.assert_clean(host)

    def test_input_validation_precedes_model_writes(self):
        host = Host()
        host.inputs[0][1].volume = 0
        with self.assertRaisesRegex(ValueError, "valid solid"):
            host.run()
        self.assertEqual(host.root.features.count, 0)
        self.assertEqual(host.root.bRepBodies.count, 1)



class StagedCategoryTests(unittest.TestCase):
    def fixture(self, *, screws=False, rotated=False):
        settings = HingeSettings(output_mode="separate", screw_holes=screws, fillet_edges=True)
        frame = (fusion.HingeFrame((17, -9, 31), (0, 0, -1), (1, 0, 0), (0, -1, 0))
                 if rotated else fusion.HingeFrame((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)))
        plan = build_hinge_plan(settings)
        core = SimpleNamespace(Circle3D=SimpleNamespace(
            cast=lambda geometry: geometry if getattr(geometry, "kind", None) == "circle" else None))
        return settings, frame, plan, core

    def circle(self, frame, radius, center, normal):
        center_world = Point(*(value / 10 for value in frame.point_mm(*center)))
        return SimpleNamespace(kind="circle", radius=radius / 10, center=center_world,
                               normal=Point(*normal))

    def cap(self, frame):
        edge = Edge()
        edge.geometry = None
        edge.evaluator.getPointAtParameter = lambda value: (
            True, Point(*(coordinate / 10 for coordinate in frame.point_mm(value, -20, 2))))
        return edge

    def test_cavity_category_requires_actual_circle_radius_axis_and_planned_center(self):
        for rotated in (False, True):
            settings, frame, plan, core = self.fixture(rotated=rotated)
            edge = self.cap(frame)
            center = (0, plan.knuckles[0].start_mm, plan.barrel_radius_mm)
            edge.geometry = self.circle(frame, plan.bore_radius_mm, center, frame.y_axis)
            category = lambda: native_finish._edge_category(edge, "A", frame, settings, plan, None, core)
            self.assertEqual(category(), "bores")
            for change in ("radius", "axis", "center", "curve_type"):
                with self.subTest(rotated=rotated, change=change):
                    edge.geometry = self.circle(frame, plan.bore_radius_mm, center, frame.y_axis)
                    if change == "radius":
                        edge.geometry.radius = plan.barrel_radius_mm / 10
                    elif change == "axis":
                        edge.geometry.normal = Point(*frame.z_axis)
                    elif change == "center":
                        edge.geometry = self.circle(frame, plan.bore_radius_mm, (1, center[1], center[2]), frame.y_axis)
                    else:
                        edge.geometry.kind = "arc"
                    self.assertEqual(category(), "caps")

    def test_mounting_holes_owner_placement_and_pin_exclusion(self):
        settings, frame, plan, core = self.fixture(screws=True, rotated=True)
        hole = plan.mounting_holes[0]
        edge = self.cap(frame)
        edge.geometry = self.circle(frame, hole.diameter_mm / 2,
                                    (hole.x_mm, hole.y_mm + 99, settings.leaf_thickness_mm), frame.z_axis)
        layout = SimpleNamespace(placements=(SimpleNamespace(center_mm=99),))
        category = lambda role, placement: native_finish._edge_category(
            edge, role, frame, settings, plan, placement, core)
        self.assertEqual(category("A_1", layout), "bores")
        self.assertEqual(category("B_1", layout), "caps")
        self.assertEqual(category("A_1", None), "caps")
        self.assertEqual(category("pin_1", layout), "caps")

    def test_planar_longitudinal_and_cap_directions_use_local_frame(self):
        for rotated in (False, True):
            settings, frame, plan, core = self.fixture(rotated=rotated)
            edge = self.cap(frame)
            self.assertEqual(native_finish._edge_category(edge, "A", frame, settings, plan, None, core), "caps")
            edge.evaluator.getPointAtParameter = lambda value: (
                True, Point(*(coordinate / 10 for coordinate in frame.point_mm(-12, value, 2))))
            self.assertEqual(native_finish._edge_category(edge, "A", frame, settings, plan, None, core), "longitudinal")

    def staged_host(self, *, fillet=True):
        host = Host(True)
        settings = HingeSettings(output_mode="separate", web_profile="flat", fillet_edges=fillet, chamfer_edges=not fillet)
        plan = build_hinge_plan(settings)
        core_circle = SimpleNamespace(cast=lambda geometry: geometry if getattr(geometry, "kind", None) == "circle" else None)
        host.core.Circle3D = core_circle
        long_edge = Edge()
        long_edge.label = "original-long"
        cap_edge = self.cap(host.frame)
        cap_edge.label = "original-cap"
        bore_edge = self.cap(host.frame)
        bore_edge.label = "original-bore"
        bore_edge.geometry = self.circle(host.frame, plan.bore_radius_mm,
                                         (0, plan.knuckles[0].start_mm, plan.barrel_radius_mm), host.frame.y_axis)
        host.inputs[0][1].edges = Items((long_edge, cap_edge, bore_edge))
        original_add = host.root.bRepBodies.add
        def add(raw, base=None):
            body = original_add(raw, base)
            body.edges = Items(copy.copy(edge) for edge in raw.edges.values)
            for edge in body.edges.values:
                edge.body = body
            return body
        host.root.bRepBodies.add = add
        return host, settings, plan

    def run_staged(self, host, settings, plan):
        with patch.object(fusion, "_api", return_value=(host.core, host.api)), patch.object(
                native_finish, "classify_edge", return_value="convex"):
            return native_finish.finish_native_results(host.design, host.manager, host.frame,
                                                       settings, host.inputs, plan=plan)

    def test_each_original_category_finishes_once_at_user_size_without_refinishing_borders(self):
        for fillet in (False, True):
            host, settings, plan = self.staged_host(fillet=fillet)
            collection = host.root.features.filletFeatures if fillet else host.root.features.chamferFeatures
            original_add = collection.add
            def add(feature_input):
                feature = original_add(feature_input)
                body = feature.bodies.item(0)
                # Finishing introduces sharp chamfer borders in the completed
                # direction. They must not be picked again in later stages.
                for edge in collection.edges.values:
                    border = copy.copy(edge)
                    border.label = "finished-border"
                    body.edges.values.append(border)
                return feature
            collection.add = add
            outputs = self.run_staged(host, settings, plan)
            labels = [tuple(edge.label for edge in edges) for edges, radius, tangent in collection.calls]
            self.assertEqual(labels, [("original-cap",), ("original-long",), ("original-bore",)])
            expected_size = settings.fillet_radius_mm if fillet else settings.chamfer_size_mm
            self.assertTrue(all(radius == expected_size / 10
                                for edges, radius, tangent in collection.calls))
            self.assertEqual([tangent for edges, radius, tangent in collection.calls], [False, False, False])
            self.assertAlmostEqual(outputs[0][1].volume, .7)
            self.assertEqual(host.root.bRepBodies.values, [host.original])
            self.assertEqual(host.root.features.count, 0)

    def test_new_nonplanar_cap_borders_are_rejected_before_classifying_while_trimmed_original_sides_finish(self):
        for fillet in (False, True):
            host, settings, plan = self.staged_host(fillet=fillet)
            collection = host.root.features.filletFeatures if fillet else host.root.features.chamferFeatures
            original_add = collection.add
            def add(feature_input):
                feature = original_add(feature_input)
                if collection.edges.item(0).label == "original-cap":
                    body = feature.bodies.item(0)
                    original = next(edge for edge in body.edges.values if edge.label == "original-long")
                    original.evaluator = SimpleNamespace(getParameterExtents=lambda: (True, -.06, .06),
                        getPointAtParameter=lambda value: (True, Point(0, value, 0)))
                    border = Edge()
                    border.body, border.label = body, "new-nonplanar-border"
                    border.evaluator.getPointAtParameter = lambda value: (True, Point(.01, value, .01 + value / 10))
                    body.edges.values.append(border)
                return feature
            collection.add = add
            def classify(edge, *args):
                self.assertNotEqual(getattr(edge, "label", None), "new-nonplanar-border",
                                    "A new cap border was incorrectly classified for longitudinal finishing.")
                return "convex"
            with patch.object(fusion, "_api", return_value=(host.core, host.api)), patch.object(
                    native_finish, "classify_edge", side_effect=classify):
                native_finish.finish_native_results(host.design, host.manager, host.frame,
                                                    settings, host.inputs, plan=plan)
            self.assertEqual([tuple(edge.label for edge in edges) for edges, _, _ in collection.calls],
                             [("original-cap",), ("original-long",), ("original-bore",)])
            self.assertEqual(host.root.features.count, 0)
            self.assertEqual(host.root.bRepBodies.values, [host.original])

    def test_healthy_caps_may_consume_one_original_side_while_every_survivor_finishes(self):
        host, settings, plan = self.staged_host()
        second = Edge()
        second.label = "second-long"
        second.evaluator.getPointAtParameter = lambda value: (True, Point(.2, value, 0))
        host.inputs[0][1].edges.values.append(second)
        collection = host.root.features.filletFeatures
        original_add = collection.add
        def add(feature_input):
            feature = original_add(feature_input)
            if collection.edges.item(0).label == "original-cap":
                body = feature.bodies.item(0)
                body.edges.values[:] = [edge for edge in body.edges.values if edge.label != "original-long"]
            return feature
        collection.add = add
        outputs = self.run_staged(host, settings, plan)
        self.assertEqual([tuple(edge.label for edge in edges) for edges, _, _ in collection.calls],
                         [("original-cap",), ("second-long",), ("original-bore",)])
        self.assertTrue(all(size == settings.fillet_radius_mm / 10 for _, size, _ in collection.calls))
        self.assertAlmostEqual(outputs[0][1].volume, .7)
        self.assertEqual(host.root.features.count, 0)
        self.assertEqual(host.root.bRepBodies.values, [host.original])

    def test_bounded_cap_set_never_expands_into_g1_connected_other_stage_edges(self):
        for fillet in (False, True):
            host = Host(True)
            settings = HingeSettings(output_mode="separate", web_profile="flat",
                                     fillet_edges=fillet, chamfer_edges=not fillet)
            body = host.root.bRepBodies.add(host.inputs[0][1])
            roof, barrel, reflex, outside_stage = Edge(), Edge(), Edge(), Edge()
            for edge in (roof, barrel, reflex, outside_stage):
                edge.body = body
            roof.connected_edges = (roof, barrel, outside_stage)
            barrel.connected_edges = (barrel, roof, outside_stage)
            owned = []
            finished = native_finish._apply_stage(host.root, body, (roof, barrel, reflex),
                "A", "caps@y=0mm", settings, host.core, host.api, owned)
            collection = host.root.features.filletFeatures if fillet else host.root.features.chamferFeatures
            self.assertIs(finished, body)
            self.assertEqual(len(collection.feature_inputs), 1)
            self.assertEqual(len(collection.calls), 1)
            edges, radius, tangent = collection.calls[0]
            self.assertEqual(edges, (roof, barrel, reflex))
            self.assertNotIn(outside_stage, edges)
            self.assertIs(tangent, False)
            self.assertEqual(radius, (settings.fillet_radius_mm if fillet else settings.chamfer_size_mm) / 10)
            owned[0].deleteMe()
            body.deleteMe()
            self.assertEqual(host.root.bRepBodies.values, [host.original])
            self.assertEqual(host.root.features.count, 0)

    def test_only_caps_use_explicit_rolling_ball_or_miter_corner_policy(self):
        for fillet in (False, True):
            host, settings, plan = self.staged_host(fillet=fillet)
            collection = host.root.features.filletFeatures if fillet else host.root.features.chamferFeatures
            self.run_staged(host, settings, plan)
            self.assertEqual(len(collection.feature_inputs), 3)
            cap, before, after = collection.feature_inputs
            if fillet:
                self.assertIs(cap.isRollingBallCorner, True)
                self.assertFalse(hasattr(before, "isRollingBallCorner"))
                self.assertFalse(hasattr(after, "isRollingBallCorner"))
            else:
                self.assertEqual(cap.cornerType, "miter")
                self.assertFalse(hasattr(before, "cornerType"))
                self.assertFalse(hasattr(after, "cornerType"))

    def test_each_original_cap_plane_is_finished_once_with_fresh_edges(self):
        for fillet in (False, True):
            host, settings, plan = self.staged_host(fillet=fillet)
            second_cap = self.cap(host.frame)
            second_cap.label = "second-cap"
            second_cap.evaluator.getPointAtParameter = lambda value: (
                True, Point(*(coordinate / 10 for coordinate in host.frame.point_mm(value, -10, 2))))
            host.inputs[0][1].edges.values.append(second_cap)
            collection = host.root.features.filletFeatures if fillet else host.root.features.chamferFeatures
            original_add = collection.add
            def add(feature_input):
                selected = tuple(collection.edges.values)
                body = selected[0].body
                self.assertTrue(all(edge in body.edges.values for edge in selected),
                                "A later native feature reused obsolete BRep references.")
                feature = original_add(feature_input)
                if any(edge.label == "original-cap" for edge in selected):
                    # Replace all topology wrappers after the first cap and add
                    # a sharp parallel chamfer border at a NEW Y coordinate.
                    body.edges.values[:] = [copy.copy(edge) for edge in body.edges.values]
                    border = self.cap(host.frame)
                    border.label = "new-parallel-border"
                    border.body = body
                    border.evaluator.getPointAtParameter = lambda value: (
                        True, Point(*(coordinate / 10 for coordinate in host.frame.point_mm(value, -19.7, 2))))
                    body.edges.values.append(border)
                return feature
            collection.add = add
            outputs = self.run_staged(host, settings, plan)
            labels = [tuple(edge.label for edge in edges) for edges, radius, tangent in collection.calls]
            self.assertEqual(labels, [("original-cap",), ("second-cap",), ("original-long",), ("original-bore",)])
            self.assertAlmostEqual(outputs[0][1].volume, .6)
            self.assertEqual(host.root.features.count, 0)
            self.assertEqual(host.root.bRepBodies.values, [host.original])

    def test_completed_cap_planes_are_filtered_before_normal_or_containment_probes(self):
        host, settings, plan = self.staged_host()
        body = host.inputs[0][1]
        current = self.cap(host.frame)
        current.label = "current-plane"
        current.evaluator.getPointAtParameter = lambda value: (
            True, Point(*(coordinate / 10 for coordinate in host.frame.point_mm(value, -10, 2))))
        body.edges.values.append(current)
        def classify(edge, *args):
            self.assertIs(edge, current, "A completed or shifted parallel cap border was reclassified.")
            return "convex"
        with patch.object(native_finish, "classify_edge", side_effect=classify) as classifier:
            selected = native_finish._candidate_edges(body, "A", host.frame, settings, plan, None,
                                                        host.core, host.api, .6,
                                                        "caps", cap_plane=-10)
        self.assertEqual(selected, (("caps", current),))
        classifier.assert_called_once()

    def test_cap_plane_grouping_is_tolerant_in_rotated_local_coordinates(self):
        settings, frame, plan, core = self.fixture(rotated=True)
        edges = []
        for y in (-20, -20.00005, -10):
            edge = self.cap(frame)
            edge.evaluator.getPointAtParameter = lambda value, y=y: (
                True, Point(*(coordinate / 10 for coordinate in frame.point_mm(value, y, 2))))
            edges.append(edge)
        groups = native_finish._cap_groups(tuple(reversed(edges)), frame)
        self.assertEqual([len(group) for plane, group in groups], [2, 1])
        self.assertAlmostEqual(groups[0][0], -20.00005)
        self.assertAlmostEqual(groups[1][0], -10)

    def test_later_stage_kernel_failure_cleans_earlier_stage_features(self):
        host, settings, plan = self.staged_host()
        host.root.features.filletFeatures.fail_on = 2
        with self.assertRaisesRegex(ValueError, r"A/longitudinal.*kernel failure"):
            self.run_staged(host, settings, plan)
        self.assertEqual(host.root.bRepBodies.values, [host.original])
        self.assertEqual(host.root.features.count, 0)

    def test_healthy_caps_may_consume_all_original_sides_without_finishing_new_borders(self):
        host, settings, plan = self.staged_host()
        collection = host.root.features.filletFeatures
        original_add = collection.add
        def add(feature_input):
            feature = original_add(feature_input)
            body = feature.bodies.item(0)
            body.edges.values[:] = [edge for edge in body.edges.values if edge.label != "original-long"]
            if collection.edges.item(0).label == "original-cap":
                border = Edge()
                border.body, border.label = body, "new-side-border"
                border.evaluator.getPointAtParameter = lambda value: (True, Point(.01, value, .01))
                body.edges.values.append(border)
            return feature
        collection.add = add
        outputs = self.run_staged(host, settings, plan)
        self.assertEqual([tuple(edge.label for edge in edges) for edges, _, _ in collection.calls],
                         [("original-cap",), ("original-bore",)])
        self.assertTrue(all(size == settings.fillet_radius_mm / 10 for _, size, _ in collection.calls))
        self.assertAlmostEqual(outputs[0][1].volume, .8)
        self.assertEqual(host.root.features.count, 0)
        self.assertEqual(host.root.bRepBodies.values, [host.original])


if __name__ == "__main__":
    unittest.main()
