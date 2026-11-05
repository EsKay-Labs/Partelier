"""Geometry, repeat closure and actual generated-facet support bounds."""
from collections import Counter
from dataclasses import replace
import math
import unittest

from Partelier.partelier.tools.knurl.settings import KnurlSettings, STYLES
from Partelier.partelier.tools.knurl import planner


class KnurlPlanTests(unittest.TestCase):
    def test_exact_typed_settings_and_defaults(self):
        settings = KnurlSettings()
        self.assertEqual((settings.style, settings.pitch_mm, settings.depth_mm, settings.border_mm), ('diamond', 6., .6, 1.))
        self.assertEqual(len(settings.to_dict()), 6)
        self.assertEqual(KnurlSettings.from_dict(settings.to_dict()), settings)
        for values in ({'depth_mm': True}, {'angle_deg': float('nan')}, {'pitch_mm': float('inf')},
                       {'border_mm': 10 ** 1000}, {'style': 'unknown'}, {'pitch_mm': 0},
                       {'angle_deg': 46}, {'phase_deg': -361}, {'depth_mm': -1}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                replace(settings, **values)
        for key in settings.to_dict():
            value = settings.to_dict()
            value.pop(key)
            with self.assertRaises(ValueError):
                KnurlSettings.from_dict(value)
        with self.assertRaises(ValueError):
            KnurlSettings.from_dict({**settings.to_dict(), 'extra': 0})

    def test_all_ten_default_styles_have_bounded_closed_positive_envelopes(self):
        self.assertEqual(len(STYLES), 10)
        for style in STYLES:
            with self.subTest(style=style):
                p = planner.plan(KnurlSettings(style=style), 15, 20)
                self.assertLessEqual(len(p.face_loops), planner.MAX_FACES)
                self.assertLessEqual(p.radial_approximation_mm, .04)
                self.assertLess(p.volume_mm3, math.pi * 15 ** 2 * 20)
                self.assertGreater(p.volume_mm3, math.pi * 14.4 ** 2 * 20)
                self.assertEqual(p.levels_mm[0], 0)
                self.assertEqual(p.levels_mm[-1], 20)
                edges = Counter(tuple(sorted((a, b))) for face in p.face_loops
                                for a, b in zip(face, face[1:] + face[:1]))
                self.assertTrue(all(uses == 2 for uses in edges.values()))

    def test_every_generated_triangle_is_supported_from_either_end(self):
        for style in STYLES:
            for angle in (0., 30., 45.):
                with self.subTest(style=style, angle=angle):
                    p = planner.plan(KnurlSettings(style=style, angle_deg=angle), 10, 12)
                    observed = 0.
                    for face in p.face_loops[2:]:
                        a, b, c = (p.points_mm[i] for i in face[:3])
                        ab = tuple(y - x for x, y in zip(a, b))
                        ac = tuple(y - x for x, y in zip(a, c))
                        nx = ab[1] * ac[2] - ab[2] * ac[1]
                        ny = ab[2] * ac[0] - ab[0] * ac[2]
                        nz = ab[0] * ac[1] - ab[1] * ac[0]
                        horizontal = math.hypot(nx, ny)
                        self.assertLessEqual(abs(nz), horizontal + 1e-8)
                        observed = max(observed, math.degrees(math.atan2(abs(nz), horizontal)))
                    self.assertAlmostEqual(observed, p.max_overhang_deg)

    def test_zero_depth_collar_chords_retain_complete_round_source(self):
        for style in STYLES:
            p = planner.plan(KnurlSettings(style=style), 12, 14)
            for z in (0., 1., 13., 14.):
                row = p.levels_mm.index(z)
                points = p.points_mm[row * p.columns:(row + 1) * p.columns]
                for a, b in zip(points, points[1:] + points[:1]):
                    # Perpendicular distance from the axis to the segment line
                    # is the inscribed radius of the regular collar polygon.
                    distance = abs(a[0] * b[1] - a[1] * b[0]) / math.dist(a[:2], b[:2])
                    self.assertAlmostEqual(distance, 12.)

    def test_repeat_pitch_closes_seam_without_duplicate_vertices(self):
        for radius in (2., 5.3, 15., 25.):
            p = planner.plan(KnurlSettings(style='straight', pitch_mm=6), radius, 10)
            self.assertAlmostEqual(p.repeats * p.effective_pitch_mm, 2 * math.pi * radius)
            self.assertEqual(p.columns % p.repeats, 0)
            for row in range(len(p.levels_mm)):
                self.assertEqual(len(set(p.points_mm[row * p.columns:(row + 1) * p.columns])), p.columns)

    def test_profile_functions_are_periodic_bounded_and_distinct(self):
        signatures = set()
        for style in STYLES:
            signature = []
            for u in (.11, .31, .61, .83):
                for z in (.7, 3.2, 6.1):
                    value = planner.relief(style, u, z, 6, 30, 14)
                    self.assertGreaterEqual(value, 0)
                    self.assertLessEqual(value, 1)
                    self.assertAlmostEqual(value, planner.relief(style, u + 1, z, 6, 30, 14))
                    signature.append(round(value, 8))
            signatures.add(tuple(signature))
        self.assertEqual(len(signatures), 10)

    def test_phase_one_turn_is_same_shape(self):
        a = planner.plan(KnurlSettings(phase_deg=0), 8, 8)
        b = planner.plan(KnurlSettings(phase_deg=360), 8, 8)
        self.assertEqual(a.face_loops, b.face_loops)
        self.assertTrue(all(math.dist(x, y) < 1e-10 for x, y in zip(a.points_mm, b.points_mm)))

    def test_angle_only_changes_directional_styles(self):
        for style in STYLES:
            a = planner.plan(KnurlSettings(style=style, angle_deg=15), 8, 8)
            b = planner.plan(KnurlSettings(style=style, angle_deg=45), 8, 8)
            if style in ('diamond', 'helical', 'chevron', 'waves'):
                self.assertNotEqual(a.points_mm, b.points_mm)
            else:
                self.assertEqual(a.points_mm, b.points_mm)

    def test_small_wave_angle_keeps_interior_wave_extrema(self):
        radius = 15
        pitch = 2 * math.pi * radius / round(2 * math.pi * radius / 6)
        settings = KnurlSettings(style='waves', angle_deg=5)
        p = planner.plan(settings, radius, 2 * pitch + 2)
        self.assertIn(1 + pitch / 2, p.levels_mm)
        self.assertIn(1 + 3 * pitch / 2, p.levels_mm)
        straight = planner.plan(replace(settings, style='straight'), radius, 2 * pitch + 2)
        # The periodic sinusoid must not disappear by sampling only its zeros.
        self.assertGreater(len(p.levels_mm), len(straight.levels_mm))
        u = .25
        self.assertNotAlmostEqual(planner.relief('waves', u, pitch / 2, pitch, 5, 2 * pitch),
                                  planner.relief('straight', u, pitch / 2, pitch, 5, 2 * pitch))

    def test_spacing_and_depth_change_actual_shape(self):
        a = planner.plan(KnurlSettings(), 15, 20)
        b = planner.plan(KnurlSettings(pitch_mm=8), 15, 20)
        c = planner.plan(KnurlSettings(depth_mm=.3), 15, 20)
        self.assertNotEqual(a.repeats, b.repeats)
        self.assertGreater(c.volume_mm3, a.volume_mm3)

    def test_identical_pure_plans_reuse_bounded_immutable_cache(self):
        a = planner.plan(KnurlSettings(), 8, 8)
        b = planner.plan(KnurlSettings.from_dict(KnurlSettings().to_dict()), 8, 8)
        self.assertIs(a, b)
        self.assertEqual(planner._plan.cache_info().maxsize, 8)

    def test_diamond_triangles_follow_sharp_unwrapped_creases(self):
        # Test the actual chosen topology against the analytic piecewise-linear
        # relief. A fixed cell diagonal crosses alternating diamond valleys.
        for phase in (0., 19.):
            settings = KnurlSettings(phase_deg=phase)
            p = planner.plan(settings, 15, 20)
            samples = p.columns / p.repeats
            factor = 1. / math.cos(math.pi / p.columns)
            slope = math.tan(math.radians(settings.angle_deg)) / p.effective_pitch_mm
            checked = 0
            for face in p.face_loops[2:]:
                if len(face) != 3:
                    continue
                vertices = [p.points_mm[k] for k in face]
                if any(not 2. < point[2] < 18. for point in vertices):
                    continue
                if any(abs((point[2] - 1.) * slope * samples - round((point[2] - 1.) * slope * samples)) > 1e-7 for point in vertices):
                    continue
                us = [((math.atan2(point[1], point[0]) + math.radians(phase)) % (2 * math.pi)) * p.repeats / (2 * math.pi) for point in vertices]
                if max(us) - min(us) > .5:
                    continue
                z = sum(point[2] for point in vertices) / 3.
                u = sum(us) / 3.
                expected = settings.depth_mm * planner.relief('diamond', u, z - 1., p.effective_pitch_mm, settings.angle_deg, 18.)
                actual = sum(15. - math.hypot(point[0], point[1]) / factor for point in vertices) / 3.
                self.assertAlmostEqual(actual, expected, places=8)
                checked += 1
            self.assertGreater(checked, 100)

    def test_coplanar_bands_do_not_keep_artificial_triangle_diagonals(self):
        p = planner.plan(KnurlSettings(style='straight'), 15, 20)
        self.assertGreater(sum(len(face) == 4 for face in p.face_loops[2:]), p.columns)

    def test_excessive_overhang_requested_depth_is_refused_not_clamped(self):
        for style in ('diamond', 'helical', 'chevron', 'waves', 'pyramids', 'rings', 'dimples'):
            with self.subTest(style=style), self.assertRaisesRegex(ValueError, '45'):
                planner.plan(KnurlSettings(style=style, depth_mm=3, pitch_mm=3, angle_deg=45), 15, 20)

    def test_dense_requests_are_refused_before_unbounded_allocation(self):
        with self.assertRaisesRegex(ValueError, 'dense'):
            planner.plan(KnurlSettings(pitch_mm=2), 100, 200)

    def test_short_borders_and_collapsed_core_refused(self):
        with self.assertRaisesRegex(ValueError, 'Border'):
            planner.plan(KnurlSettings(border_mm=4), 10, 8)
        with self.assertRaisesRegex(ValueError, 'core'):
            planner.plan(KnurlSettings(depth_mm=1), 2, 8)
        for radius, height in ((float('nan'), 10), (8, True), (10 ** 1000, 10)):
            with self.assertRaises(ValueError):
                planner.plan(KnurlSettings(), radius, height)


if __name__ == '__main__':
    unittest.main()
