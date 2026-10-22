"""Independent analytic contour witnesses and read-only host contracts."""

from dataclasses import replace
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from Partelier.partelier.tools.hinge import fusion, roof_finish
from Partelier.partelier.tools.hinge.planner import build_hinge_plan
from Partelier.partelier.tools.hinge.settings import HingeSettings


def dot(one, two):
    return sum(a * b for a, b in zip(one, two))


class Body:
    isValid = isSolid = isTemporary = True
    lumps = SimpleNamespace(count=1)
    volume = 1

    def __init__(self, contains):
        self.contains = contains
        self.calls = []

    def pointContainment(self, point):
        self.calls.append(point)
        return "inside" if self.contains(point) else "outside"


def api():
    # Deliberately no box/cylinder/feature/boolean APIs: validation is read-only.
    return (SimpleNamespace(Point3D=SimpleNamespace(create=lambda *args: args)),
            SimpleNamespace(PointContainment=SimpleNamespace(PointInsidePointContainment="inside",
                PointOutsidePointContainment="outside", PointOnPointContainment="on")))


class AnalyticNeighborhood:
    """An independent local roof/round-cylinder section, before/after cap finish."""
    def __init__(self, frame, web, radius, fillet, shift=0):
        self.frame, self.web, self.radius, self.fillet, self.shift = frame, web, radius, fillet, shift
        # Construct the tangent from the line's outside point and a circle:
        # polar tangent angle = outside-point angle +/- acos(R / distance).
        reach = -web.x_min_mm if web.owner == "A" else web.x_max_mm
        px, pz = -reach, web.z_max_mm - radius
        angle = math.atan2(pz, px) - math.acos(radius / math.hypot(px, pz))
        nx, nz = math.cos(angle), math.sin(angle)
        if web.owner == "B":
            nx = -nx
        self.normal = (nx, nz)
        sign = 1 if web.owner == "A" else -1
        self.along = (sign * nz, -sign * nx)
        self.tangent = (radius * nx, radius * (1 + nz))

    def local(self, point_cm):
        delta = tuple(10 * value - origin for value, origin in zip(point_cm, self.frame.origin_mm))
        x, y, z = (dot(delta, axis) for axis in (self.frame.x_axis, self.frame.y_axis, self.frame.z_axis))
        relative = (x - self.tangent[0], z - self.tangent[1])
        return dot(relative, self.along), y - self.shift, dot(relative, self.normal)

    def contains(self, point_cm, *, finished):
        u, y, v = self.local(point_cm)
        depth = min(y - self.web.y_min_mm, self.web.y_max_mm - y)
        if depth < -1e-10 or v < -self.radius:
            return False
        radius = self.radius
        if finished and depth < self.fillet:
            radius -= self.fillet - math.sqrt(max(0, self.fillet ** 2 - (self.fillet - depth) ** 2))
        if u <= 0:
            return v <= radius - self.radius
        return u * u + (self.radius + v) ** 2 <= radius * radius


class ContourGuardTests(unittest.TestCase):
    def setUp(self):
        self.frame = fusion.HingeFrame((10, -7, 32), (0, 0, -1), (1, 0, 0), (0, -1, 0))
        patcher = patch.object(fusion, "_api", return_value=api())
        patcher.start()
        self.addCleanup(patcher.stop)

    def scenario(self, *, mode="attached", role="A", size=.6, count=1, layout=None):
        settings = HingeSettings(output_mode=mode, fillet_edges=True, fillet_radius_mm=size,
                                 include_pin=False, hinge_count=count)
        plan = build_hinge_plan(settings)
        shifts = roof_finish._placement_shifts(settings, role, layout)
        neighborhoods = tuple(AnalyticNeighborhood(self.frame, web, plan.barrel_radius_mm, size, shift)
                              for shift in shifts for web in plan.webs if web.owner == role.split("_", 1)[0])
        raw = Body(lambda p: any(n.contains(p, finished=False) for n in neighborhoods))
        finished = Body(lambda p: any(n.contains(p, finished=True) for n in neighborhoods))
        return settings, plan, raw, finished, neighborhoods

    def validate(self, settings, plan, raw, finished, *, role="A", layout=None):
        return roof_finish.validate_tangent_roofs(self.frame, settings, role, raw, finished,
                                                 plan=plan, layout=layout)

    def test_exact_joined_profiles_pass_both_roles_modes_and_rotated_world_without_mutation(self):
        for mode in ("attached", "separate"):
            for role in ("A", "B"):
                with self.subTest(mode=mode, role=role):
                    settings, plan, raw, finished, _ = self.scenario(mode=mode, role=role,
                                                                    size=.6 if mode == "attached" else .2)
                    raw_contains, finished_contains = raw.contains, finished.contains
                    self.assertIs(self.validate(settings, plan, raw, finished, role=role), finished)
                    self.assertIs(raw.contains, raw_contains)
                    self.assertIs(finished.contains, finished_contains)
                    self.assertEqual((raw.volume, finished.volume), (1, 1))
                    self.assertGreater(len(raw.calls), 0)
                    self.assertGreater(len(finished.calls), 0)

    def test_removed_band_constraint_does_not_reject_otherwise_valid_large_attached_radius(self):
        settings, plan, raw, finished, _ = self.scenario(size=.9)
        self.assertGreater(3 * settings.fillet_radius_mm, plan.barrel_radius_mm - plan.bore_radius_mm)
        self.assertIs(self.validate(settings, plan, raw, finished), finished)

    def test_roof_valley_cylinder_valley_and_added_cap_material_are_explicit_refusals(self):
        for defect in ("roof", "cylinder", "extra"):
            settings, plan, raw, finished, neighborhoods = self.scenario()
            correct = finished.contains
            def contains(point):
                for n in neighborhoods:
                    u, y, v = n.local(point)
                    depth = min(y - n.web.y_min_mm, n.web.y_max_mm - y)
                    if 0 < depth < n.fillet and abs(u) < n.fillet:
                        if defect == "roof" and -.4 < u < -.001:
                            return False
                        if defect == "cylinder" and .001 < u < .4:
                            return False
                        if defect == "extra" and -.4 < u < -.001:
                            return n.contains(point, finished=False)
                return correct(point)
            finished.contains = contains
            with self.subTest(defect=defect), self.assertRaisesRegex(ValueError, "discontinuous.*cap contour"):
                self.validate(settings, plan, raw, finished)
            self.assertEqual(finished.volume, 1)

    def test_unrelated_raw_root_surface_is_not_mistaken_for_the_analytic_roof(self):
        settings, plan, raw, finished, neighborhoods = self.scenario()
        correct_raw, correct_finished = raw.contains, finished.contains
        def unrelated(point):
            return any(n.local(point)[0] < -.8 * settings.fillet_radius_mm for n in neighborhoods)
        raw.contains = lambda point: True if unrelated(point) else correct_raw(point)
        finished.contains = lambda point: False if unrelated(point) else correct_finished(point)
        self.assertIs(self.validate(settings, plan, raw, finished), finished)

    def test_unverifiable_raw_surface_and_unknown_native_containment_fail_closed(self):
        settings, plan, raw, finished, _ = self.scenario()
        raw.contains = lambda p: True
        with self.assertRaisesRegex(ValueError, "could not be verified"):
            self.validate(settings, plan, raw, finished)
        settings, plan, raw, finished, _ = self.scenario()
        finished.pointContainment = lambda point: "unknown"
        with self.assertRaisesRegex(ValueError, "could not classify"):
            self.validate(settings, plan, raw, finished)

    def test_all_matching_units_and_knuckles_are_checked_with_separate_role_mapping(self):
        layout = SimpleNamespace(placements=tuple(SimpleNamespace(index=i, center_mm=c)
                     for i, c in enumerate((-70, 0, 70))))
        for mode, role, expected_webs in (("attached", "A", 9), ("separate", "B_3", 2)):
            settings, plan, raw, finished, _ = self.scenario(mode=mode, role=role, count=3,
                                                            size=.2, layout=layout)
            original = roof_finish.plan_tangent_contour_witnesses
            with patch.object(roof_finish, "plan_tangent_contour_witnesses", wraps=original) as planner:
                self.assertIs(self.validate(settings, plan, raw, finished, role=role, layout=layout), finished)
            self.assertEqual(planner.call_count, expected_webs)
            if mode == "separate":
                self.assertTrue(all(call.kwargs["shift_mm"] == 70 for call in planner.call_args_list))

    def test_other_styles_and_pins_bypass_the_round_tangent_fillet_guard(self):
        settings, plan, raw, finished, _ = self.scenario()
        variants = ((replace(settings, fillet_edges=False, chamfer_edges=True), "A"),
                    (replace(settings, web_profile="flat"), "A"),
                    (replace(settings, knuckle_profile="square", fillet_radius_mm=.2), "A"),
                    (settings, "pin_2"))
        for variant, role in variants:
            self.assertIs(self.validate(variant, plan, raw, finished, role=role), finished)
        self.assertEqual(raw.calls, [])
        self.assertEqual(finished.calls, [])

    def test_invalid_temporary_solid_is_rejected_without_any_geometry_write(self):
        settings, plan, raw, finished, _ = self.scenario()
        for body, name, value in ((raw, "isTemporary", False), (finished, "volume", math.nan)):
            original = getattr(body, name)
            setattr(body, name, value)
            with self.assertRaisesRegex(ValueError, "temporary solid"):
                self.validate(settings, plan, raw, finished)
            setattr(body, name, original)


class ContourPlanningTests(unittest.TestCase):
    def test_every_cap_depth_includes_both_analytic_sides_and_exact_in_out_pairs(self):
        settings = HingeSettings(fillet_edges=True)
        plan = build_hinge_plan(settings)
        for web in plan.webs[:2]:
            witnesses = roof_finish.plan_tangent_contour_witnesses(web, 4, .6, attached=True, shift_mm=19)
            self.assertEqual(len(witnesses), 48)
            groups = {}
            for witness in witnesses:
                groups.setdefault((witness.cap, witness.depth_mm), set()).add(witness.side)
                self.assertAlmostEqual(math.dist(witness.inside_point_mm, witness.outside_point_mm), .01)
                self.assertAlmostEqual(math.dist(witness.raw_inside_point_mm, witness.raw_outside_point_mm), .01)
                expected_y = (web.y_min_mm + witness.depth_mm if witness.cap == "start"
                              else web.y_max_mm - witness.depth_mm) + 19
                self.assertAlmostEqual(witness.inside_point_mm[1], expected_y)
            self.assertEqual(len(groups), 6)
            self.assertTrue(all(sides == {"roof", "cylinder"} for sides in groups.values()))

    def test_mirrored_sample_coordinates_follow_the_same_cap_positions_and_radius(self):
        settings = HingeSettings(fillet_edges=True)
        plan = build_hinge_plan(settings)
        a = plan.webs[0]
        b = replace(a, owner="B", x_min_mm=-a.x_max_mm, x_max_mm=-a.x_min_mm)
        aa = roof_finish.plan_tangent_contour_witnesses(a, 4, .6, attached=True)
        bb = roof_finish.plan_tangent_contour_witnesses(b, 4, .6, attached=True)
        for one, two in zip(aa, bb):
            for field in ("raw_inside_point_mm", "raw_outside_point_mm", "inside_point_mm", "outside_point_mm"):
                x, y, z = getattr(one, field)
                self.assertEqual(getattr(two, field), (-x, y, z))

    def test_invalid_numbers_and_existing_span_constraints_are_explicit(self):
        web = build_hinge_plan(HingeSettings()).webs[0]
        for size in (0, -1, True, math.inf, math.nan):
            with self.subTest(size=size), self.assertRaises(ValueError):
                roof_finish.plan_tangent_contour_witnesses(web, 4, size, attached=True)
        with self.assertRaisesRegex(ValueError, "half the knuckle length"):
            roof_finish.plan_tangent_contour_witnesses(replace(web, y_max_mm=web.y_min_mm + 1),
                                                       4, .6, attached=True)

    def test_role_placement_indices_remain_strict(self):
        layout = SimpleNamespace(placements=tuple(SimpleNamespace(index=i, center_mm=c)
                     for i, c in enumerate((-50, 0, 50))))
        settings = HingeSettings(output_mode="separate", hinge_count=3)
        self.assertEqual(roof_finish._placement_shifts(settings, "B_3", layout), (50,))
        for role in ("A", "A_4", "B_bad"):
            with self.subTest(role=role), self.assertRaises(ValueError):
                roof_finish._placement_shifts(settings, role, layout)


if __name__ == "__main__":
    unittest.main()
