"""Geometric/adapter contracts for tangent wedges; no native kernel claims."""

from dataclasses import replace
import itertools
import math
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from Partelier.partelier.tools.hinge import fusion, support
from Partelier.partelier.tools.hinge.planner import WebBounds, build_hinge_plan
from Partelier.partelier.tools.hinge.settings import HingeSettings


def dot(one, two):
    return sum(a * b for a, b in zip(one, two))


def delta(one, two):
    return tuple(a - b for a, b in zip(one, two))


def cross(one, two):
    return (one[1] * two[2] - one[2] * two[1],
            one[2] * two[0] - one[0] * two[2],
            one[0] * two[1] - one[1] * two[0])


def inside_polygon(point, polygon):
    return all((two[0] - one[0]) * (point[1] - one[1])
               - (two[1] - one[1]) * (point[0] - one[0]) >= -1e-11
               for one, two in zip(polygon, polygon[1:] + polygon[:1]))


def segment_distance_squared(point, one, two):
    direction = delta(two, one)
    fraction = max(0, min(1, dot(delta(point, one), direction) / dot(direction, direction)))
    closest = tuple(a + fraction * change for a, change in zip(one, direction))
    displacement = delta(point, closest)
    return dot(displacement, displacement)


def inset_polygon_reference(polygon, radius):
    """Independent adjacent-line intersections, rather than polygon clipping."""
    lines = []
    for one, two in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dz = two[0] - one[0], two[1] - one[1]
        length = math.hypot(dx, dz)
        a, b = dz / length, -dx / length
        lines.append((a, b, a * one[0] + b * one[1] - radius))
    vertices = []
    for (a, b, c), (d, e, f) in zip(lines, lines[1:] + lines[:1]):
        determinant = a * e - b * d
        vertices.append(((c * e - b * f) / determinant, (a * f - c * d) / determinant))
    return tuple(vertices)


class Body:
    isValid = True
    isSolid = True
    isTemporary = True
    lumps = SimpleNamespace(count=1)

    def __init__(self, contains):
        self.contains = contains
        self.volume = 100.0  # Failure sentinel, not a numerical volume oracle.


class Manager:
    """Interpret documented primitives/booleans as independent analytic sets."""
    def __init__(self):
        self.calls = []
        self.operations = []
        self.fail_primitive = None
        self.fail_boolean = False
        self.split_boolean = False
        self.persistent_primitive = False
        self.remove_volume = True

    def primitive(self, kind, arguments, contains):
        self.calls.append((kind, arguments))
        if self.fail_primitive == kind:
            return None
        body = Body(contains)
        if self.persistent_primitive:
            body.isTemporary = False
        return body

    def createBox(self, box):
        center, first, second, *dimensions = box
        third = cross(first, second)
        def contains(point):
            relative = delta(point, center)
            return all(abs(dot(relative, axis)) <= size / 2 + 1e-13
                       for axis, size in zip((first, second, third), dimensions))
        return self.primitive("box", (box,), contains)

    def createCylinderOrCone(self, start, radius, end, last_radius):
        if radius != last_radius:
            raise AssertionError("Fillets must use circular cylinders.")
        direction = delta(end, start)
        length = math.sqrt(dot(direction, direction))
        unit = tuple(value / length for value in direction)
        def contains(point):
            relative = delta(point, start)
            along = dot(relative, unit)
            radial_squared = max(0, dot(relative, relative) - along * along)
            return -1e-13 <= along <= length + 1e-13 and radial_squared <= radius ** 2 + 1e-13
        return self.primitive("cylinder", (start, radius, end, last_radius), contains)

    def createSphere(self, center, radius):
        def contains(point):
            relative = delta(point, center)
            return dot(relative, relative) <= radius ** 2 + 1e-13
        return self.primitive("sphere", (center, radius), contains)

    def booleanOperation(self, target, tool, operation):
        self.operations.append(operation)
        if self.fail_boolean:
            return False
        one, two = target.contains, tool.contains
        if operation == "difference":
            target.contains = lambda point: one(point) and not two(point)
            if self.remove_volume:
                target.volume -= .1
        elif operation == "union":
            target.contains = lambda point: one(point) or two(point)
            target.volume += .1
        else:
            raise AssertionError("No persistent features or undocumented intersection API required.")
        if self.split_boolean:
            target.lumps = SimpleNamespace(count=2)
        return True


class TangentPlanTests(unittest.TestCase):
    def setUp(self):
        self.web = WebBounds("A", -12, -2, -3.88, 3.88, -.5, 2)

    def test_plane_matches_corrected_reference_and_is_exactly_tangent(self):
        plan = support.plan_tangent_support(self.web, 4)
        self.assertAlmostEqual(plan.source_intercept_x_mm, -15.659416862, places=8)
        self.assertLess(abs(plan.source_intercept_x_mm - -15.660458), .002)
        tx, tz = plan.tangent_xz_mm
        self.assertAlmostEqual(tx, -1.9183310969, places=8)
        self.assertAlmostEqual(tz, 7.5099865815, places=8)
        self.assertAlmostEqual(tx * tx + (tz - 4) ** 2, 16, places=10)
        along_plane = (tx + 12, tz - 2)
        self.assertAlmostEqual(dot((tx, tz - 4), along_plane), 0, places=10)
        self.assertAlmostEqual((2 - 0) / (-12 - plan.source_intercept_x_mm),
                               (tz - 2) / (tx + 12), places=12)
        self.assertGreater(plan.area_mm2, 0)
        self.assertGreater(plan.slope_angle_deg, 0)
        self.assertLess(plan.slope_angle_deg, 90)

    def test_b_is_the_exact_reflection_and_both_polygons_remain_ccw(self):
        a = support.plan_tangent_support(self.web, 4)
        b = support.plan_tangent_support(replace(self.web, owner="B", x_min_mm=2, x_max_mm=12), 4)
        self.assertEqual(b.polygon_xz_mm, tuple((-x, z) for x, z in reversed(a.polygon_xz_mm)))
        self.assertEqual(b.tangent_xz_mm, (-a.tangent_xz_mm[0], a.tangent_xz_mm[1]))
        self.assertEqual(b.area_mm2, a.area_mm2)
        self.assertEqual(b.source_intercept_x_mm, -a.source_intercept_x_mm)
        self.assertEqual((b.y_min_mm, b.y_max_mm), (-3.88, 3.88))
        for plan in (a, b):
            center = tuple(sum(point[index] for point in plan.polygon_xz_mm) / 3 for index in (0, 1))
            self.assertTrue(inside_polygon(center, plan.polygon_xz_mm))

    def test_wedge_has_positive_source_and_barrel_overlap_and_stays_on_its_side(self):
        plan = support.plan_tangent_support(self.web, 4)
        self.assertEqual(plan.source_overlap_mm, .5)
        self.assertEqual(min(z for _, z in plan.polygon_xz_mm), -.5)
        self.assertLess(plan.bottom_intercept_x_mm, plan.source_intercept_x_mm)
        self.assertTrue(inside_polygon((-9, -.25), plan.polygon_xz_mm))
        tx, _ = plan.tangent_xz_mm
        point = (tx - .1, 4)
        self.assertTrue(inside_polygon(point, plan.polygon_xz_mm))
        self.assertLess(point[0] ** 2 + (point[1] - 4) ** 2, 16)
        self.assertTrue(all(x < 0 for x, _ in plan.polygon_xz_mm))

    def test_tangency_and_positive_intercepts_hold_across_radii_reaches_and_thicknesses(self):
        for radius, multiplier, fraction in itertools.product((1, 4, 30), (1.1, 3, 8), (.15, .5, .8)):
            reach, thickness = radius * multiplier, radius * fraction
            web = WebBounds("A", -reach, -radius / 2, -2 * radius, 2 * radius, -radius / 8, thickness)
            plan = support.plan_tangent_support(web, radius)
            tx, tz = plan.tangent_xz_mm
            self.assertAlmostEqual(math.hypot(tx, tz - radius), radius, places=9)
            self.assertAlmostEqual(dot((tx, tz - radius), (tx + reach, tz - thickness)), 0, places=8)
            self.assertLess(plan.source_intercept_x_mm, -reach)
            self.assertGreater(plan.area_mm2, 0)

    def test_invalid_bounds_and_nonfinite_values_are_rejected(self):
        changes = ({"owner": "C"}, {"x_min_mm": -2}, {"x_max_mm": 0},
                   {"x_max_mm": -5}, {"x_min_mm": -3}, {"y_max_mm": -3.88},
                   {"z_min_mm": 0}, {"z_min_mm": .5}, {"z_max_mm": .1},
                   {"z_max_mm": 4}, {"z_max_mm": float("nan")},
                   {"x_min_mm": float("inf")}, {"y_min_mm": True}, {"y_min_mm": "0"})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                support.plan_tangent_support(replace(self.web, **change), 4)
        for radius in (0, -4, True, "4", float("nan"), float("inf")):
            with self.subTest(radius=radius), self.assertRaises(ValueError):
                support.plan_tangent_support(self.web, radius)
        with self.assertRaises(ValueError):
            support.plan_tangent_support(SimpleNamespace(), 4)


    def test_all_mode_profile_sections_are_convex_mirrored_and_meet_the_upper_housing(self):
        expected_vertices = {("attached", "round"): 3, ("attached", "square"): 4,
                             ("separate", "round"): 4, ("separate", "square"): 5}
        for mode, profile in itertools.product(("attached", "separate"), ("round", "square")):
            settings = HingeSettings(output_mode=mode, knuckle_profile=profile)
            webs = build_hinge_plan(settings).webs
            a_web, b_web = webs[0], webs[1]
            a = support.plan_tangent_support(a_web, 4, knuckle_profile=profile, attached=mode == "attached")
            b = support.plan_tangent_support(b_web, 4, knuckle_profile=profile, attached=mode == "attached")
            self.assertEqual(len(a.polygon_xz_mm), expected_vertices[(mode, profile)])
            self.assertEqual(b.polygon_xz_mm, tuple((-x, z) for x, z in reversed(a.polygon_xz_mm)))
            self.assertEqual(a.knuckle_profile, profile)
            self.assertEqual(a.attached, mode == "attached")
            for i, vertex in enumerate(a.polygon_xz_mm):
                before, after = a.polygon_xz_mm[i - 1], a.polygon_xz_mm[(i + 1) % len(a.polygon_xz_mm)]
                self.assertGreater((vertex[0] - before[0]) * (after[1] - vertex[1])
                                   - (vertex[1] - before[1]) * (after[0] - vertex[0]), 0)
            tx, tz = a.tangent_xz_mm
            slope = (tz - a_web.z_max_mm) / (tx - a_web.x_min_mm)
            self.assertAlmostEqual(math.degrees(math.atan(slope)), a.slope_angle_deg)
            if profile == "square":
                half = 4 / math.sqrt(2)
                self.assertEqual((tx, tz), (-half, 4 + half))
                self.assertEqual(max(x for x, _ in a.polygon_xz_mm), 0)
                self.assertTrue(inside_polygon((-1, 4), a.polygon_xz_mm))
                self.assertLess(abs(-1), half)  # Positive, rather than corner-only overlap.
            else:
                self.assertAlmostEqual(tx * tx + (tz - 4) ** 2, 16)
                self.assertAlmostEqual(dot((tx, tz - 4), (tx - a_web.x_min_mm, tz - a_web.z_max_mm)), 0)

    def test_separate_supports_stop_at_the_web_outer_corner_and_never_extend_past_the_plate(self):
        for profile, reach in itertools.product(("round", "square"), (8.5, 12, 20)):
            settings = HingeSettings(output_mode="separate", knuckle_profile=profile, leaf_reach_mm=reach)
            web = build_hinge_plan(settings).webs[0]
            plan = support.plan_tangent_support(web, 4, knuckle_profile=profile, attached=False)
            self.assertEqual(min(x for x, _ in plan.polygon_xz_mm), web.x_min_mm)
            self.assertGreaterEqual(web.x_min_mm, -reach)
            self.assertEqual(min(z for _, z in plan.polygon_xz_mm), 0)
            self.assertEqual(plan.source_overlap_mm, 0)
            self.assertIn((web.x_min_mm, web.z_max_mm), plan.polygon_xz_mm)
            self.assertTrue(inside_polygon((web.x_min_mm + .1, 1), plan.polygon_xz_mm))
            self.assertFalse(inside_polygon((web.x_min_mm - .001, 2.001), plan.polygon_xz_mm))
            self.assertFalse(inside_polygon((web.x_min_mm, 2.001), plan.polygon_xz_mm))
            self.assertLess(plan.source_intercept_x_mm, web.x_min_mm)

    def test_mode_profile_and_floor_mismatch_are_rejected(self):
        for options in ({"knuckle_profile": "triangle"}, {"attached": "separate"},
                        {"attached": 1}, {"attached": False}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                support.plan_tangent_support(self.web, 4, **options)
        separate = replace(self.web, z_min_mm=0)
        with self.assertRaises(ValueError):
            support.plan_tangent_support(separate, 4, attached=True)
        with self.assertRaises(ValueError):
            support.plan_tangent_support(replace(separate, z_max_mm=.8), 4,
                                         knuckle_profile="square", attached=False)


class TangentAdapterTests(unittest.TestCase):
    def setUp(self):
        self.web = WebBounds("A", -12, -2, -3.88, 3.88, -.5, 2)
        self.frame = fusion.HingeFrame((10, 20, 30), (0, 1, 0), (0, 0, 1), (1, 0, 0))
        self.settings = HingeSettings()
        self.manager = Manager()
        api = (SimpleNamespace(Point3D=SimpleNamespace(create=lambda *args: args),
                               Vector3D=SimpleNamespace(create=lambda *args: args),
                               OrientedBoundingBox3D=SimpleNamespace(create=lambda *args: args)),
               SimpleNamespace(BooleanTypes=SimpleNamespace(DifferenceBooleanType="difference", UnionBooleanType="union")))
        api_patch = patch.object(fusion, "_api", return_value=api)
        api_patch.start()
        self.addCleanup(api_patch.stop)

    def point(self, x, y, z):
        return tuple(value / 10 for value in self.frame.point_mm(x, y, z))

    def build(self, settings=None, web=None):
        return support.make_tangent_support(self.manager, self.frame, web or self.web, settings or self.settings)

    def test_sharp_prism_matches_convex_section_in_rotated_translated_frame(self):
        target = self.build()
        plan = support.plan_tangent_support(self.web, 4)
        generator = random.Random(918)
        for _ in range(900):
            point = (generator.uniform(-18, 0), generator.uniform(-5, 5), generator.uniform(-1, 9))
            expected = (-3.88 <= point[1] <= 3.88
                        and inside_polygon((point[0], point[2]), plan.polygon_xz_mm))
            self.assertEqual(target.contains(self.point(*point)), expected, msg=str(point))
        self.assertTrue(target.isTemporary)
        self.assertEqual(target.lumps.count, 1)
        self.assertEqual(len(self.manager.calls), 2)  # One bounding box and one slope cut.

    def test_rounded_prism_matches_independent_exact_distance_field(self):
        radius = .6
        target = self.build(replace(self.settings, fillet_edges=True, fillet_radius_mm=radius))
        plan = support.plan_tangent_support(self.web, 4)
        inner = inset_polygon_reference(plan.polygon_xz_mm, radius)
        generator = random.Random(1294)
        for _ in range(1800):
            x, y, z = (generator.uniform(-18, 0), generator.uniform(-5, 5), generator.uniform(-1, 9))
            xz = (x, z)
            distance_xz = (0 if inside_polygon(xz, inner) else min(
                segment_distance_squared(xz, one, two) for one, two in zip(inner, inner[1:] + inner[:1])))
            distance_y = max((-3.88 + radius) - y, 0, y - (3.88 - radius))
            expected = distance_xz + distance_y ** 2 <= radius ** 2
            self.assertEqual(target.contains(self.point(x, y, z)), expected, msg=str((x, y, z)))
        spheres = [args for kind, args in self.manager.calls if kind == "sphere"]
        cylinders = [args for kind, args in self.manager.calls if kind == "cylinder"]
        self.assertEqual(len(spheres), 6)
        self.assertEqual(len(cylinders), 9)
        self.assertTrue(all(abs(args[1] - .06) < 1e-12 for args in spheres + cylinders))
        actual = {tuple(round(v, 8) for v in args[0]) for args in spheres}
        expected = {tuple(round(v, 8) for v in self.point(x, y, z))
                    for x, z in inner for y in (-3.28, 3.28)}
        self.assertEqual(actual, expected)

    def test_chamfer_has_equal_along_face_setbacks_on_cap_edges(self):
        target = self.build(replace(self.settings, chamfer_edges=True, chamfer_size_mm=.3))
        plan = support.plan_tangent_support(self.web, 4)
        for one, two in zip(plan.polygon_xz_mm, plan.polygon_xz_mm[1:] + plan.polygon_xz_mm[:1]):
            dx, dz = two[0] - one[0], two[1] - one[1]
            length = math.hypot(dx, dz)
            normal = (dz / length, -dx / length)
            middle = ((one[0] + two[0]) / 2, (one[1] + two[1]) / 2)
            for y in (-3.86, 3.86):
                for distance, expected in ((.2, False), (.4, True)):
                    x, z = (middle[0] - distance * normal[0], middle[1] - distance * normal[1])
                    self.assertEqual(target.contains(self.point(x, y, z)), expected)
        self.assertGreater(len(self.manager.operations), 9)
        self.assertTrue(all(kind == "box" for kind, _ in self.manager.calls))

    def test_chamfer_has_equal_setbacks_at_every_sloping_and_vertical_corner(self):
        target = self.build(replace(self.settings, chamfer_edges=True, chamfer_size_mm=.3))
        polygon = support.plan_tangent_support(self.web, 4).polygon_xz_mm
        for index, corner in enumerate(polygon):
            for neighbor in (polygon[index - 1], polygon[(index + 1) % len(polygon)]):
                dx, dz = neighbor[0] - corner[0], neighbor[1] - corner[1]
                length = math.hypot(dx, dz)
                for setback, expected in ((.29, False), (.31, True)):
                    x, z = corner[0] + setback * dx / length, corner[1] + setback * dz / length
                    # Nudge toward the centroid to avoid sampling an open
                    # boundary in this analytic difference-set interpreter.
                    center = tuple(sum(point[axis] for point in polygon) / 3 for axis in (0, 1))
                    x += (center[0] - x) * 1e-7
                    z += (center[1] - z) * 1e-7
                    self.assertEqual(target.contains(self.point(x, 0, z)), expected,
                                     msg=str((corner, neighbor, setback)))

    def test_each_finished_mirrored_adapter_matches_a_side_by_point_sampling(self):
        generator = random.Random(537)
        for finish in ({}, {"chamfer_edges": True}, {"fillet_edges": True}):
            a = self.build(replace(self.settings, **finish))
            self.manager = Manager()
            b = self.build(replace(self.settings, **finish),
                           replace(self.web, owner="B", x_min_mm=2, x_max_mm=12))
            for _ in range(450):
                x, y, z = generator.uniform(-18, 0), generator.uniform(-5, 5), generator.uniform(-1, 9)
                self.assertEqual(a.contains(self.point(x, y, z)), b.contains(self.point(-x, y, z)))
            self.manager = Manager()

    def test_all_finishes_retain_positive_source_and_barrel_connection(self):
        for finish in ({}, {"chamfer_edges": True}, {"fillet_edges": True}):
            for owner in ("A", "B"):
                self.manager = Manager()
                web = self.web if owner == "A" else replace(self.web, owner="B", x_min_mm=2, x_max_mm=12)
                target = self.build(replace(self.settings, **finish), web)
                sign = -1 if owner == "A" else 1
                self.assertTrue(target.contains(self.point(sign * 9, 0, -.2)))
                self.assertTrue(target.contains(self.point(sign * 2.2, 0, 4)))
                self.assertFalse(target.contains(self.point(-sign * .01, 0, 4)))

    def test_every_generated_coordinate_and_dimension_is_finite_and_positive(self):
        self.build(replace(self.settings, fillet_edges=True))
        for kind, arguments in self.manager.calls:
            if kind == "box":
                center, first, second, *dimensions = arguments[0]
                self.assertTrue(all(math.isfinite(v) for v in center + first + second + tuple(dimensions)))
                self.assertTrue(all(v > 0 for v in dimensions))
                self.assertAlmostEqual(dot(first, first), 1)
                self.assertAlmostEqual(dot(second, second), 1)
                self.assertAlmostEqual(dot(first, second), 0)
            elif kind == "cylinder":
                start, radius, end, last = arguments
                self.assertTrue(all(math.isfinite(v) for v in start + end + (radius, last)))
                self.assertGreater(radius, 0)
                self.assertGreater(math.dist(start, end), 0)
            else:
                center, radius = arguments
                self.assertTrue(all(math.isfinite(v) for v in center + (radius,)))
                self.assertGreater(radius, 0)

    def test_invalid_scope_bad_frames_and_collapsed_finishes_fail_before_geometry(self):
        with self.assertRaisesRegex(fusion.HingeGeometryError, "tangent web profile"):
            self.build(replace(self.settings, web_profile="flat"))
        with self.assertRaisesRegex(fusion.HingeGeometryError, "separate floor at Z=0"):
            self.build(replace(self.settings, output_mode="separate"))
        for frame in (replace(self.frame, x_axis=(2, 0, 0)),
                      replace(self.frame, z_axis=(0, 0, 1)),
                      replace(self.frame, origin_mm=(float("nan"), 0, 0))):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "orthonormal"):
                support.make_tangent_support(self.manager, frame, self.web, self.settings)
        # A deliberately short independently supplied web is not accepted even
        # when the settings' own original span would permit the radius.
        with self.assertRaisesRegex(fusion.HingeGeometryError, "half the support length"):
            self.build(replace(self.settings, fillet_edges=True), replace(self.web, y_min_mm=0, y_max_mm=1))
        with self.assertRaisesRegex(ValueError, "consumes|collapses"):
            support._inset_polygon(((-1, 0), (1, 0), (0, .1)), .2)
        self.assertEqual(self.manager.calls, [])

    def test_all_available_modes_profiles_and_finishes_keep_positive_connections(self):
        for mode, profile, finish, count in itertools.product(
                ("attached", "separate"), ("round", "square"), ("sharp", "chamfer", "fillet"), (3, 5, 11)):
            settings = HingeSettings(output_mode=mode, knuckle_profile=profile, knuckle_count=count,
                                     chamfer_edges=finish == "chamfer", fillet_edges=finish == "fillet",
                                     fillet_radius_mm=.4)
            webs = build_hinge_plan(settings).webs
            for web in webs[:2]:
                with self.subTest(mode=mode, profile=profile, finish=finish, count=count, owner=web.owner):
                    self.manager = Manager()
                    target = self.build(settings, web)
                    plan = support.plan_tangent_support(web, 4, knuckle_profile=profile, attached=mode == "attached")
                    y = (web.y_min_mm + web.y_max_mm) / 2
                    sign = -1 if web.owner == "A" else 1
                    if mode == "attached":
                        self.assertTrue(target.contains(self.point(sign * 9, y, -.2)))
                    else:
                        reach = -web.x_min_mm if web.owner == "A" else web.x_max_mm
                        self.assertTrue(target.contains(self.point(sign * (reach - .8), y, 1)))
                        self.assertFalse(target.contains(self.point(sign * (reach + .01), y, 2.01)))
                        self.assertFalse(target.contains(self.point(sign * (reach - .8), y, -.001)))
                    housing_x = sign * 1.5 if profile == "square" else plan.tangent_xz_mm[0] + sign * .15
                    self.assertTrue(target.contains(self.point(housing_x, y, 4)))
                    self.assertTrue(target.isTemporary)
                    self.assertEqual(target.lumps.count, 1)
                    if finish == "sharp":
                        self.assertEqual(len(self.manager.calls), 2)

    def test_all_quadrilateral_and_pentagon_fillets_match_the_exact_distance_field(self):
        generator = random.Random(7412)
        for mode, profile in itertools.product(("attached", "separate"), ("round", "square")):
            settings = HingeSettings(output_mode=mode, knuckle_profile=profile, fillet_edges=True,
                                     fillet_radius_mm=.4)
            webs = build_hinge_plan(settings).webs
            for web in webs[:2]:
                self.manager = Manager()
                target = self.build(settings, web)
                plan = support.plan_tangent_support(web, 4, knuckle_profile=profile, attached=mode == "attached")
                inner = inset_polygon_reference(plan.polygon_xz_mm, .4)
                for _ in range(600):
                    x, y, z = generator.uniform(-18, 18), generator.uniform(-21, -3), generator.uniform(-1, 9)
                    distance_xz = 0 if inside_polygon((x, z), inner) else min(
                        segment_distance_squared((x, z), one, two)
                        for one, two in zip(inner, inner[1:] + inner[:1]))
                    distance_y = max(web.y_min_mm + .4 - y, 0, y - (web.y_max_mm - .4))
                    expected = distance_xz + distance_y ** 2 <= .4 ** 2
                    self.assertEqual(target.contains(self.point(x, y, z)), expected,
                                     msg=str((mode, profile, web.owner, x, y, z)))
                self.assertEqual(sum(kind == "sphere" for kind, _ in self.manager.calls), 2 * len(inner))
                self.assertEqual(sum(kind == "cylinder" for kind, _ in self.manager.calls), 3 * len(inner))

    def test_all_sections_chamfer_each_original_prism_edge_at_equal_face_distance(self):
        for mode, profile in itertools.product(("attached", "separate"), ("round", "square")):
            settings = HingeSettings(output_mode=mode, knuckle_profile=profile, chamfer_edges=True)
            for web in build_hinge_plan(settings).webs[:2]:
                self.manager = Manager()
                target = self.build(settings, web)
                polygon = support.plan_tangent_support(web, 4, knuckle_profile=profile,
                                                       attached=mode == "attached").polygon_xz_mm
                ymid = (web.y_min_mm + web.y_max_mm) / 2
                center = tuple(sum(p[axis] for p in polygon) / len(polygon) for axis in (0, 1))
                for i, corner in enumerate(polygon):
                    for neighbor in (polygon[i - 1], polygon[(i + 1) % len(polygon)]):
                        dx, dz = neighbor[0] - corner[0], neighbor[1] - corner[1]
                        length = math.hypot(dx, dz)
                        for setback, expected in ((.29, False), (.31, True)):
                            x, z = corner[0] + setback * dx / length, corner[1] + setback * dz / length
                            x += (center[0] - x) * 1e-7
                            z += (center[1] - z) * 1e-7
                            self.assertEqual(target.contains(self.point(x, ymid, z)), expected,
                                             msg=str((mode, profile, web.owner, corner, neighbor, setback)))
                for one, two in zip(polygon, polygon[1:] + polygon[:1]):
                    dx, dz = two[0] - one[0], two[1] - one[1]
                    length = math.hypot(dx, dz)
                    normal = (dz / length, -dx / length)
                    middle = ((one[0] + two[0]) / 2, (one[1] + two[1]) / 2)
                    for y in (web.y_min_mm + .02, web.y_max_mm - .02):
                        for inset, expected in ((.2, False), (.4, True)):
                            x, z = middle[0] - inset * normal[0], middle[1] - inset * normal[1]
                            self.assertEqual(target.contains(self.point(x, y, z)), expected,
                                             msg=str((mode, profile, web.owner, one, two, y, inset)))

    def test_nonpositive_nonfinite_and_malformed_temporary_volumes_are_refused(self):
        for volume in (0, -1, float("nan"), float("inf"), None, "invalid"):
            self.manager = Manager()
            original = self.manager.primitive
            def malformed(kind, arguments, contains):
                body = original(kind, arguments, contains)
                body.volume = volume
                return body
            with self.subTest(volume=volume), patch.object(self.manager, "primitive", side_effect=malformed):
                with self.assertRaisesRegex(fusion.HingeGeometryError, "finite, positive temporary solid volume"):
                    self.build()
        for volume in (0, -1, float("nan"), float("inf")):
            self.manager = Manager()
            original = self.manager.booleanOperation
            def malformed_boolean(target, tool, operation):
                result = original(target, tool, operation)
                target.volume = volume
                return result
            with self.subTest(boolean_volume=volume), patch.object(self.manager, "booleanOperation", side_effect=malformed_boolean):
                with self.assertRaisesRegex(fusion.HingeGeometryError, "finite, positive temporary solid volume"):
                    self.build()

    def test_nonfinite_box_midpoint_is_rejected_before_any_primitive(self):
        # A finite interval and finite span do not guarantee a finite midpoint
        # when the primitive adapter computes (minimum + maximum) / 2.
        web = replace(self.web, y_min_mm=1e308, y_max_mm=1.1e308)
        self.assertTrue(math.isfinite(web.y_max_mm - web.y_min_mm))
        with self.assertRaisesRegex(fusion.HingeGeometryError, "finite numbers"):
            self.build(web=web)
        self.assertEqual(self.manager.calls, [])

    def test_primitive_failures_split_boolean_and_persistent_bodies_are_refused(self):
        for kind in ("box", "cylinder", "sphere"):
            self.manager = Manager()
            self.manager.fail_primitive = kind
            with self.subTest(kind=kind), self.assertRaises(fusion.HingeGeometryError):
                self.build(replace(self.settings, fillet_edges=True))
        for flag in ("fail_boolean", "split_boolean", "persistent_primitive"):
            self.manager = Manager()
            setattr(self.manager, flag, True)
            with self.subTest(flag=flag), self.assertRaises(fusion.HingeGeometryError):
                self.build()
        self.manager = Manager()
        self.manager.remove_volume = False
        with self.assertRaisesRegex(fusion.HingeGeometryError, "positive material"):
            self.build(replace(self.settings, chamfer_edges=True))


if __name__ == "__main__":
    unittest.main()
