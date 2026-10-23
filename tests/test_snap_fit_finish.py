"""Joined-topology outer finishing, continuous paths and protected surfaces."""

from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.snap_fit import finish
from Partelier.partelier.tools.snap_fit.planner import build_snap_fit_plan
from Partelier.partelier.tools.snap_fit.settings import SnapFitSettings
from Partelier.partelier.tools.hinge import fusion as hinge


class Collection:
    def __init__(self, values):
        self.values = tuple(values)
        self.count = len(self.values)

    def item(self, index):
        return self.values[index]


def edge(start, end, one, two):
    return SimpleNamespace(isDegenerate=False, start=start, end=end,
                           faces=Collection((SimpleNamespace(normal=one, geometry="plane"), SimpleNamespace(normal=two, geometry="plane"))))


def _polygon_contains(polygon, x, z, strict=False):
    values = [(b[0] - a[0]) * (z - a[1]) - (b[1] - a[1]) * (x - a[0])
              for a, b in zip(polygon, polygon[1:] + polygon[:1])]
    return all(value > 1e-9 if strict else value >= -1e-9 for value in values)


def body_for(unit, edges):
    polygons = [(((unit.root.x_min_mm, unit.root.z_min_mm),
                  (unit.root.x_max_mm, unit.root.z_min_mm),
                  (unit.root.x_max_mm, unit.root.z_max_mm),
                  (unit.root.x_min_mm, unit.root.z_max_mm)), unit.root.y_min_mm, unit.root.y_max_mm)]
    for arm in unit.arms:
        polygons.extend((prism.points_xz_mm, prism.y_min_mm, prism.y_max_mm)
                        for prism in (arm.beam, arm.hook))
    if unit.root_support is not None:
        polygons.append((unit.root_support.points_xz_mm, unit.root_support.y_min_mm, unit.root_support.y_max_mm))
    def containment(point):
        x, y, z = point
        on = False
        for polygon, low, high in polygons:
            if low < y < high and _polygon_contains(polygon, x, z, strict=True):
                return 1
            if low - 1e-9 <= y <= high + 1e-9 and _polygon_contains(polygon, x, z):
                on = True
        return 2 if on else 0
    return SimpleNamespace(edges=Collection(edges), pointContainment=Mock(side_effect=containment))


@contextmanager
def native_edges():
    enums = SimpleNamespace(PointOutsidePointContainment=0, PointInsidePointContainment=1,
                            PointOnPointContainment=2)
    core = SimpleNamespace(Plane=SimpleNamespace(cast=lambda geometry: geometry if geometry == "plane" else None))
    with patch.object(hinge, "_api", return_value=(core, SimpleNamespace(PointContainment=enums))), patch.object(
            hinge, "_straight_endpoints", side_effect=lambda edge: tuple(tuple(v / 10 for v in p) for p in (edge.start, edge.end))), patch.object(
            hinge, "_plane_normal", side_effect=lambda face: face.normal), patch.object(
            hinge, "_point", side_effect=lambda frame, *point: point):
        yield


def contains(cut, point):
    delta = tuple(value - origin for value, origin in zip(point, cut.center_mm))
    return all(abs(sum(a * b for a, b in zip(delta, axis))) < size / 2
               for axis, size in ((cut.edge_axis, cut.length_mm), (cut.tangent_axis, cut.width_mm),
                                  (cut.normal_axis, cut.depth_mm))) and point[0] >= 0


FRAME = hinge.HingeFrame((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))


class SnapFitFinishTests(unittest.TestCase):
    def test_actual_complete_front_edges_are_beveled_through_root_and_arm_chain(self):
        settings = SnapFitSettings(print_support=False)
        unit = build_snap_fit_plan(settings, 60).units[0]
        outer, y = unit.root.x_max_mm, unit.root.y_max_mm
        edges = [edge((outer, y, -4), (outer, y, 0), (1, 0, 0), (0, 1, 0)),
                 edge((outer, y, 0), (outer, y, 16), (1, 0, 0), (0, 1, 0))]
        body = body_for(unit, edges)
        with native_edges():
            cuts = finish.plan_detail_chamfers(body, FRAME, settings)
        self.assertEqual(len(cuts), 1)
        cut = cuts[0]
        for actual, expected in zip(cut.start_mm, (outer, y, -4)):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(cut.end_mm, (outer, y, 16)):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(cut.length_mm, 20)
        self.assertEqual(cut.source_edge_count, 2)
        for fraction in (.001, .1, .5, .9, .999):
            z = -4 + 20 * fraction
            for factor, expected in ((.45, True), (.55, False)):
                point = (outer - factor * .3, y - factor * .3, z)
                self.assertEqual(contains(cut, point), expected)
        self.assertEqual(cut.diagnostic()["source_edge_count"], 2)

    def test_taper_and_twin_outer_longitudinal_edges_use_actual_endpoints(self):
        for style in ("tapered", "twin"):
            settings = SnapFitSettings(snap_style=style)
            unit = build_snap_fit_plan(settings, 60).units[0]
            outer = unit.root.x_max_mm
            edges = []
            for index, arm in enumerate(unit.arms):
                tip = max(x for x, z in arm.beam.points_xz_mm if z == settings.reach_mm)
                normal = finish._unit((settings.reach_mm, 0, outer - tip))
                y = arm.beam.y_min_mm if index == 0 else arm.beam.y_max_mm
                side = (0, -1, 0) if index == 0 else (0, 1, 0)
                edges.append(edge((outer, y, 0),
                                  (tip, y, settings.reach_mm), normal, side))
            body = body_for(unit, edges)
            with self.subTest(style=style), native_edges():
                cuts = finish.plan_detail_chamfers(body, FRAME, settings)
            self.assertEqual(len(cuts), len(unit.arms))
            for cut in cuts:
                self.assertEqual(cut.start_mm[2], 0)
                self.assertEqual(cut.end_mm[2], settings.reach_mm)

    def test_inner_beam_and_retaining_edges_are_never_eligible_or_sampled(self):
        settings = SnapFitSettings()
        unit = build_snap_fit_plan(settings, 60).units[0]
        y = unit.root.y_max_mm
        protected = [edge((.3, y, 0), (.3, y, 13), (-1, 0, 0), (0, 1, 0)),
                     edge((-1, y, 13), (.3, y, 13), (0, 0, -1), (0, 1, 0))]
        body = body_for(unit, protected)
        with native_edges(), self.assertRaisesRegex(ValueError, "No supported exterior"):
            finish.plan_detail_chamfers(body, FRAME, settings)
        body.pointContainment.assert_not_called()

    def test_actual_concave_arm_root_edge_is_excluded(self):
        settings = SnapFitSettings(snap_style="twin")
        unit = build_snap_fit_plan(settings, 60).units[0]
        arm = unit.arms[0]
        y = arm.beam.y_max_mm
        path = finish.EdgePath((.3, y, 0), (1.8, y, 0), (0, 1, 0), (0, 0, 1), "concave")
        body = body_for(unit, [])
        with native_edges():
            self.assertFalse(finish._convex(body, FRAME, path, settings.chamfer_size_mm))

    def test_ambiguous_convexity_is_an_error_instead_of_silently_partial_finish(self):
        settings = SnapFitSettings()
        unit = build_snap_fit_plan(settings, 60).units[0]
        outer = unit.root.x_max_mm
        body = body_for(unit, [edge((outer, 4, 0), (outer, 4, 16), (1, 0, 0), (0, 1, 0))])
        body.pointContainment.side_effect = None
        body.pointContainment.return_value = 2
        with native_edges(), self.assertRaisesRegex(ValueError, "could not prove"):
            finish.plan_detail_chamfers(body, FRAME, settings)

    def test_coplanar_edges_are_not_chamfered(self):
        settings = SnapFitSettings()
        unit = build_snap_fit_plan(settings, 60).units[0]
        body = body_for(unit, [edge((1.8, 4, 0), (1.8, 4, 16), (1, 0, 0), (1, 0, 0))])
        with native_edges(), self.assertRaisesRegex(ValueError, "No supported exterior"):
            finish.plan_detail_chamfers(body, FRAME, settings)
        body.pointContainment.assert_not_called()

    def test_disjoint_paths_and_different_incident_normals_cannot_be_merged(self):
        first = finish.EdgePath((1, 0, 0), (1, 0, 4), (1, 0, 0), (0, 1, 0), "first")
        gap = replace(first, start_mm=(1, 0, 5), end_mm=(1, 0, 8))
        different = replace(first, start_mm=(1, 0, 4), end_mm=(1, 0, 8), normal_two=(0, -1, 0))
        self.assertEqual(len(finish._merge_paths((first, gap, different))), 3)
        reversed_path = replace(first, start_mm=(1, 0, 8), end_mm=(1, 0, 4),
                                normal_one=(0, 1, 0), normal_two=(1, 0, 0))
        merged = finish._merge_paths((first, reversed_path))
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].end_mm, (1, 0, 8))

    def test_wall_crossing_path_is_trimmed_exactly_at_x_zero(self):
        self.assertEqual(finish._outside_segment((-.5, 4, -6.3), (1.8, 4, -4)),
                         ((0.0, 4.0, -5.8), (1.8, 4, -4)))
        self.assertIsNone(finish._outside_segment((-.5, 4, 0), (0, 4, 0)))

    def test_receiver_is_untouched_and_disabled_chamfers_do_no_native_work(self):
        settings = SnapFitSettings(chamfer_edges=False)
        self.assertEqual(finish.plan_receiver_chamfers(None, SnapFitSettings()), ())
        self.assertEqual(finish.plan_detail_chamfers(None, None, settings), ())
        body = object()
        self.assertIs(finish.apply_chamfers(None, None, body, ()), body)


if __name__ == "__main__":
    unittest.main()
