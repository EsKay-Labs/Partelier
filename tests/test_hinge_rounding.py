"""Analytic construction contracts; these are not native Fusion kernel tests."""

from dataclasses import replace
import math
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from Partelier.partelier.tools.hinge import fusion, rounding
from Partelier.partelier.tools.hinge.planner import WebBounds


def dot(one, two):
    return sum(a * b for a, b in zip(one, two))


def delta(one, two):
    return tuple(a - b for a, b in zip(one, two))


def cross(one, two):
    return (one[1] * two[2] - one[2] * two[1],
            one[2] * two[0] - one[0] * two[2],
            one[0] * two[1] - one[1] * two[0])


class Body:
    """Independent analytic set; volume is only an adapter-failure sentinel."""
    isValid = True
    isSolid = True
    isTemporary = True
    lumps = SimpleNamespace(count=1)

    def __init__(self, contains=lambda point: True):
        self.contains = contains
        self.volume = 100.0


class AnalyticManager:
    """Interpret the documented primitive/boolean inputs, without any adsk."""
    def __init__(self):
        self.calls = []
        self.operations = []
        self.fail_primitive = None
        self.fail_boolean = False
        self.split_boolean = False
        self.remove_volume = True

    def _primitive(self, name, args, contains):
        self.calls.append((name, args))
        return None if self.fail_primitive == name else Body(contains)

    def createBox(self, bounds):
        center, x_axis, y_axis, length, width, height = bounds
        z_axis = cross(x_axis, y_axis)
        def contains(point):
            displacement = delta(point, center)
            return all(abs(dot(displacement, axis)) <= dimension / 2 + 1e-14
                       for axis, dimension in zip((x_axis, y_axis, z_axis),
                                                  (length, width, height)))
        return self._primitive("box", (bounds,), contains)

    def createCylinderOrCone(self, start, radius, end, last_radius):
        if radius != last_radius:
            raise AssertionError("Round geometry must use circular cylinders, not cones.")
        direction = delta(end, start)
        length = math.sqrt(dot(direction, direction))
        direction = tuple(value / length for value in direction)
        def contains(point):
            displacement = delta(point, start)
            along = dot(displacement, direction)
            radial_squared = max(0, dot(displacement, displacement) - along * along)
            return -1e-14 <= along <= length + 1e-14 and radial_squared <= radius * radius + 1e-14
        return self._primitive("cylinder", (start, radius, end, last_radius), contains)

    def createSphere(self, center, radius):
        def contains(point):
            displacement = delta(point, center)
            return dot(displacement, displacement) <= radius * radius + 1e-14
        return self._primitive("sphere", (center, radius), contains)

    def createTorus(self, center, axis, major, minor):
        def contains(point):
            displacement = delta(point, center)
            along = dot(displacement, axis)
            radial = math.sqrt(max(0, dot(displacement, displacement) - along * along))
            return (radial - major) ** 2 + along ** 2 <= minor ** 2 + 1e-14
        return self._primitive("torus", (center, axis, major, minor), contains)

    def booleanOperation(self, target, tool, operation):
        self.operations.append((target, tool, operation))
        if self.fail_boolean:
            return False
        first, second = target.contains, tool.contains
        if operation == "union":
            target.contains = lambda point: first(point) or second(point)
            target.volume += .1
        elif operation == "difference":
            target.contains = lambda point: first(point) and not second(point)
            if self.remove_volume:
                target.volume -= .1
        else:
            raise AssertionError("Unexpected operation.")
        if self.split_boolean:
            target.lumps = SimpleNamespace(count=2)
        return True


class RoundingTests(unittest.TestCase):
    def setUp(self):
        self.frame = fusion.HingeFrame((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
        self.rotated = fusion.HingeFrame((10, 20, 30), (0, 1, 0), (0, 0, 1), (1, 0, 0))
        self.bounds = WebBounds("A", -8, 2, -12, 12, 0, 4)
        self.manager = AnalyticManager()
        self.api = (SimpleNamespace(
            Point3D=SimpleNamespace(create=lambda *values: values),
            Vector3D=SimpleNamespace(create=lambda *values: values),
            OrientedBoundingBox3D=SimpleNamespace(create=lambda *values: values)),
            SimpleNamespace(BooleanTypes=SimpleNamespace(
                UnionBooleanType="union", DifferenceBooleanType="difference")))
        self.api_patch = patch.object(fusion, "_api", return_value=self.api)
        self.api_patch.start()
        self.addCleanup(self.api_patch.stop)

    def point(self, *coordinates, frame=None):
        return tuple(value / 10 for value in (frame or self.frame).point_mm(*coordinates))

    def rounded_box(self, frame=None):
        return rounding.rounded_box(self.manager, frame or self.frame, self.bounds, .6)

    def test_box_matches_exact_inset_box_distance_field_in_rotated_frame(self):
        target = self.rounded_box(self.rotated)
        low, high = (-7.4, -11.4, .6), (1.4, 11.4, 3.4)
        generator = random.Random(812)
        for _ in range(1500):
            point = tuple(generator.uniform(a, b) for a, b in ((-9, 3), (-13, 13), (-1, 5)))
            squared = sum(max(a - value, 0, value - b) ** 2
                          for value, a, b in zip(point, low, high))
            self.assertEqual(target.contains(self.point(*point, frame=self.rotated)), squared <= .6 ** 2,
                             msg=f"Inset-box distance mismatch at {point}.")

    def test_box_keeps_all_six_nominal_extents_and_rounds_corners_spherically(self):
        target = self.rounded_box()
        center = [-3, 0, 2]
        for axis, extremes in enumerate(((-8, 2), (-12, 12), (0, 4))):
            for extreme in extremes:
                point = center.copy()
                point[axis] = extreme
                self.assertTrue(target.contains(self.point(*point)))
                point[axis] += -.01 if extreme == extremes[0] else .01
                self.assertFalse(target.contains(self.point(*point)))
        center = (-7.4, -11.4, .6)
        for fraction, expected in ((.99, True), (1.01, False)):
            point = tuple(value - .6 * fraction / math.sqrt(3) for value in center)
            self.assertEqual(target.contains(self.point(*point)), expected)
        self.assertFalse(target.contains(self.point(-7.95, -11.95, .05)))

    def test_box_uses_true_spheres_at_corner_centers_in_cm(self):
        self.rounded_box(self.rotated)
        spheres = [args for kind, args in self.manager.calls if kind == "sphere"]
        self.assertEqual(len(spheres), 8)
        centers = {tuple(round(value, 8) for value in args[0]) for args in spheres}
        expected = {tuple(round(value, 8) for value in self.point(x, y, z, frame=self.rotated))
                    for x in (-7.4, 1.4) for y in (-11.4, 11.4) for z in (.6, 3.4)}
        self.assertEqual(centers, expected)
        self.assertTrue(all(abs(args[1] - .06) < 1e-12 for args in spheres))
        self.assertEqual(sum(kind == "box" for kind, _ in self.manager.calls), 3)
        self.assertEqual(sum(kind == "cylinder" for kind, _ in self.manager.calls), 12)
        self.assertTrue(all(operation == "union" for _, _, operation in self.manager.operations))

    def test_box_rejects_nonpositive_or_consuming_radius_before_geometry_calls(self):
        for radius in (0, -.1, 2, 3, float("nan"), float("inf"), True, ".3"):
            with self.subTest(radius=radius), self.assertRaises(fusion.HingeGeometryError):
                rounding.rounded_box(self.manager, self.frame, self.bounds, radius)
        self.assertEqual(self.manager.calls, [])
        with self.assertRaises(fusion.HingeGeometryError):
            rounding.rounded_box(self.manager, self.frame, replace(self.bounds, x_min_mm=20), .3)

    def test_primitive_failures_and_split_union_are_refused(self):
        for kind in ("box", "cylinder", "sphere"):
            manager = AnalyticManager()
            manager.fail_primitive = kind
            with self.subTest(kind=kind), self.assertRaises(fusion.HingeGeometryError):
                rounding.rounded_box(manager, self.frame, self.bounds, .3)
        self.manager.split_boolean = True
        with self.assertRaisesRegex(fusion.HingeGeometryError, "one solid"):
            self.rounded_box()

    def test_cylinder_round_has_exact_quarter_circle_profile_and_nominal_fit(self):
        target = rounding.rounded_axis_body(self.manager, self.frame, -10, 10, 3, 4, .6)
        for end, sign in ((-10, 1), (10, -1)):
            for depth in (0, .1, .3, .59, .6, 1, 5):
                radial = (2.4 + math.sqrt(.6 ** 2 - (depth - .6) ** 2)
                          if depth < .6 else 3)
                along = end + sign * depth
                self.assertTrue(target.contains(self.point(radial - .001, along, 4)))
                self.assertFalse(target.contains(self.point(radial + .001, along, 4)))
            self.assertFalse(target.contains(self.point(0, end - sign * .001, 4)))
        self.assertTrue(target.contains(self.point(2.999, 0, 4)))
        self.assertFalse(target.contains(self.point(3.001, 0, 4)))

    def test_cylinder_round_tori_are_oriented_translated_and_converted_once(self):
        target = rounding.rounded_axis_body(self.manager, self.rotated, -10, 10, 3, 4, .6)
        tori = [args for kind, args in self.manager.calls if kind == "torus"]
        self.assertEqual(len(tori), 2)
        for args, position in zip(tori, (-9.4, 9.4)):
            for actual, expected in zip(args[0], self.point(0, position, 4, frame=self.rotated)):
                self.assertAlmostEqual(actual, expected)
            self.assertEqual(args[1], self.rotated.y_axis)
            self.assertAlmostEqual(args[2], .24)
            self.assertAlmostEqual(args[3], .06)
        self.assertTrue(target.contains(self.point(2.999, 0, 4, frame=self.rotated)))

    def test_cylinder_round_surface_meets_flat_face_and_middle_tangentially(self):
        target = rounding.rounded_axis_body(self.manager, self.frame, -10, 10, 3, 4, .6)
        def radial_limit(y):
            low, high = 0, 3.1
            for _ in range(45):
                middle = (low + high) / 2
                if target.contains(self.point(middle, y, 4)):
                    low = middle
                else:
                    high = middle
            return (low + high) / 2
        # The slope approaches zero where the circular round joins the side.
        epsilon = .001
        self.assertLess(abs((radial_limit(-9.4) - radial_limit(-9.4 - epsilon)) / epsilon), .002)
        self.assertAlmostEqual(radial_limit(-10), 2.4, places=5)
        self.assertAlmostEqual(radial_limit(0), 3, places=5)

    def test_cylinder_rejects_horn_torus_collapsed_middle_or_nonfinite_coordinates(self):
        for args in ((-10, 10, 1.2, 4, .6), (-.6, .6, 3, 4, .6),
                     (-10, 10, 3, 4, 0), (-10, 10, 3, float("nan"), .3)):
            with self.subTest(args=args), self.assertRaises(fusion.HingeGeometryError):
                rounding.rounded_axis_body(self.manager, self.frame, *args)
        self.assertEqual(self.manager.calls, [])

    def test_cylinder_torus_creation_or_boolean_failure_is_actionable(self):
        self.manager.fail_primitive = "torus"
        with self.assertRaisesRegex(fusion.HingeGeometryError, "torus"):
            rounding.rounded_axis_body(self.manager, self.frame, -10, 10, 3, 4, .6)
        self.manager = AnalyticManager()
        self.manager.fail_boolean = True
        with self.assertRaisesRegex(fusion.HingeGeometryError, "join"):
            rounding.rounded_axis_body(self.manager, self.frame, -10, 10, 3, 4, .6)

    def _bore(self, axis, sign, frame=None):
        frame = frame or self.frame
        target = Body()
        before = target.volume
        rounding.round_bore_entry(self.manager, frame, target, 1.5, 2, sign, 4, .3,
                                  axis=axis, x=6, y=7)
        self.assertLess(target.volume, before)
        cutter = self.manager.operations[-1][1]
        return target, cutter

    def test_bore_cutter_has_concave_circle_mouth_for_both_axis_directions(self):
        for axis in ("y", "z"):
            for sign in (-1, 1):
                with self.subTest(axis=axis, sign=sign):
                    self.manager = AnalyticManager()
                    _, cutter = self._bore(axis, sign)
                    for depth in (0, .01, .15, .29):
                        mouth = 1.8 - math.sqrt(max(0, .3 ** 2 - (depth - .3) ** 2))
                        along = 2 + sign * depth
                        def point(radius):
                            return self.point(radius, along, 4) if axis == "y" else self.point(6 + radius, 7, along)
                        self.assertTrue(cutter.contains(point(mouth - .001)))
                        self.assertFalse(cutter.contains(point(mouth + .001)))
                    self.assertFalse(cutter.contains(
                        self.point(0, 2 + sign * .301, 4) if axis == "y"
                        else self.point(6, 7, 2 + sign * .301)))
                    self.assertTrue(all(kind != "sphere" for kind, _ in self.manager.calls))

    def test_bore_tool_needs_positive_removal_and_only_mutates_supplied_temporary(self):
        source = Body()
        source.isTemporary = False
        with self.assertRaisesRegex(fusion.HingeGeometryError, "temporary"):
            rounding.round_bore_entry(self.manager, self.frame, source, 1.5, 2, 1, 4, .3)
        self.assertEqual(self.manager.calls, [])
        self.assertEqual(source.volume, 100)
        self.manager.remove_volume = False
        with self.assertRaisesRegex(fusion.HingeGeometryError, "positive material"):
            rounding.round_bore_entry(self.manager, self.frame, Body(), 1.5, 2, 1, 4, .3)

    def test_bore_placement_preserves_rotated_y_and_z_units(self):
        for axis in ("y", "z"):
            self.manager = AnalyticManager()
            self._bore(axis, -1, self.rotated)
            cylinder = next(args for kind, args in self.manager.calls if kind == "cylinder")
            torus = next(args for kind, args in self.manager.calls if kind == "torus")
            expected = ((0, 1.7, 4) if axis == "y" else (6, 7, 1.7))
            for actual, wanted in zip(torus[0], self.point(*expected, frame=self.rotated)):
                self.assertAlmostEqual(actual, wanted)
            self.assertEqual(torus[1], self.rotated.y_axis if axis == "y" else self.rotated.z_axis)
            self.assertAlmostEqual(torus[2], .18)
            self.assertAlmostEqual(torus[3], .03)
            self.assertAlmostEqual(cylinder[1], .18)

    def test_bore_bad_axis_direction_and_dimensions_fail_before_any_cut(self):
        for changes in ({"axis": "x"}, {"inward_sign": 0}, {"inward_sign": True},
                        {"bore_radius": 0}, {"fillet": 0}, {"x": float("inf")}):
            arguments = dict(bore_radius=1.5, position=2, inward_sign=1, height=4, fillet=.3)
            arguments.update(changes)
            with self.subTest(changes=changes), self.assertRaises(fusion.HingeGeometryError):
                rounding.round_bore_entry(self.manager, self.frame, Body(), **arguments)
        self.assertEqual(self.manager.calls, [])

    def test_bore_failed_difference_or_split_body_is_refused(self):
        for flag in ("fail_boolean", "split_boolean"):
            self.manager = AnalyticManager()
            setattr(self.manager, flag, True)
            with self.subTest(flag=flag), self.assertRaises(fusion.HingeGeometryError):
                rounding.round_bore_entry(self.manager, self.frame, Body(), 1.5, 2, 1, 4, .3)

    def test_derived_overflow_or_erased_round_is_rejected_before_api_calls(self):
        bad_bounds = replace(self.bounds, x_min_mm=-1e308, x_max_mm=1e308)
        with self.assertRaises(ValueError):
            rounding.rounded_box(self.manager, self.frame, bad_bounds, .6)
        with self.assertRaises(ValueError):
            rounding.rounded_axis_body(self.manager, self.frame, -1e308, 1e308, 4, 4, .6)
        with self.assertRaises(ValueError):
            rounding.rounded_axis_body(self.manager, self.frame, 1e20, 1e20+1e6, 4, 4, .6)
        with self.assertRaises(ValueError):
            rounding.round_bore_entry(self.manager, self.frame, Body(), 1.65, 1e20, 1, 4, .6)
        self.assertFalse(self.manager.calls)

    def test_nonunit_nonorthogonal_or_left_handed_frame_is_rejected(self):
        for frame in (replace(self.frame, x_axis=(2, 0, 0)),
                      replace(self.frame, y_axis=(1, 0, 0)),
                      replace(self.frame, z_axis=(0, 0, -1)),
                      replace(self.frame, origin_mm=(0, float("nan"), 0))):
            with self.subTest(frame=frame), self.assertRaises(fusion.HingeGeometryError):
                self.rounded_box(frame)
        self.assertEqual(self.manager.calls, [])

    def test_every_primitive_must_be_a_temporary_solid(self):
        with patch.object(self.manager, "createBox", return_value=SimpleNamespace(
                isValid=True, isSolid=True, isTemporary=False, lumps=SimpleNamespace(count=1))):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "temporary"):
                self.rounded_box()


if __name__ == "__main__":
    unittest.main()
