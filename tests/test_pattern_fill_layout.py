"""User-facing density presets and independent cell size/gap behavior."""

from dataclasses import replace
import itertools
import math
import unittest

from Partelier.partelier.tools.patterns.planner import build_layout, PatternDensityError
from Partelier.partelier.tools.patterns.settings import PatternSettings
from test_pattern_fit_layout import opening_distance, envelope


class PatternFillLayoutTests(unittest.TestCase):
    def test_balanced_cell_size_changes_below_the_same_soft_budget_floor(self):
        for shape in ('hexagon','circle','diamond','square','slot'):
            for edge in ('clip','whole'):
                layouts=[]
                for size in (5,10,20):
                    with self.subTest(shape=shape,edge=edge,size=size):
                        settings=PatternSettings(pattern=shape,pitch_mm=size+5,web_mm=5,layout_mode="balanced",edge_mode=edge)
                        layout=build_layout(settings,(0,300,0,170))
                        self.assertTrue(0<layout.cell_count<=48)
                        self.assertGreaterEqual(layout.pitch_mm,settings.pitch_mm-1e-7)
                        width=max(max(x for x,y in c.polygon_mm)-min(x for x,y in c.polygon_mm) for c in layout.cells)
                        self.assertAlmostEqual(width,size)
                        layouts.append(layout)
                self.assertNotEqual(layouts[0].cells,layouts[1].cells)
                self.assertNotEqual(layouts[1].cells,layouts[2].cells)

    def test_balanced_size_and_minimum_gap_survive_wrap_spacing_adjustment(self):
        period=200
        for size in (5,10,15):
            settings=PatternSettings(pitch_mm=size+5,web_mm=5,layout_mode='balanced',edge_mode='whole')
            layout=build_layout(settings,(0,period,0,100),period)
            self.assertTrue(0<layout.cell_count<=48)
            self.assertGreaterEqual(layout.pitch_mm,settings.pitch_mm-1e-7)
            width=max(x for x,y in layout.cells[0].polygon_mm)-min(x for x,y in layout.cells[0].polygon_mm)
            self.assertAlmostEqual(width,size)
            for one,two in itertools.combinations(layout.cells,2):
                if math.dist(one.center_mm,two.center_mm)<layout.pitch_mm*1.1:
                    self.assertGreaterEqual(opening_distance(one,two),5-1e-7)

    def test_default_is_less_dense_than_legacy_auto_on_a_large_face(self):
        settings = PatternSettings()
        sparse = build_layout(settings, (0,200,0,160))
        automatic = build_layout(replace(settings, layout_mode='fit'), (0,200,0,160))
        self.assertEqual(settings.layout_mode, 'auto')
        self.assertEqual((settings.web_mm, settings.border_mm), (7, 7))
        self.assertEqual(settings.pitch_mm-settings.web_mm, 12.5)
        self.assertFalse(settings.size_locked)
        self.assertTrue(0 < sparse.cell_count <= 64)
        self.assertGreater(automatic.cell_count, sparse.cell_count)
        self.assertGreater(sparse.pitch_mm, automatic.pitch_mm)

    def test_fill_preserves_requested_size_border_and_minimum_gap_for_every_shape(self):
        for shape in ('hexagon','circle','diamond','square','slot'):
            with self.subTest(shape=shape):
                settings = PatternSettings(pattern=shape, layout_mode='fill', edge_mode='whole', pitch_mm=11.5, web_mm=1.5)
                result = build_layout(settings, (0,80,0,60))
                self.assertGreater(result.cell_count, 12)
                self.assertEqual(result.pitch_mm, settings.pitch_mm)
                low_u, high_u, low_v, high_v = envelope(result.cells)
                self.assertGreaterEqual(min(low_u,low_v), 2-1e-7)
                self.assertLessEqual(high_u, 78+1e-7)
                self.assertLessEqual(high_v, 58+1e-7)
                # Check actual polygon separation, not just distance between centers.
                for one,two in itertools.combinations(result.cells,2):
                    if math.dist(one.center_mm,two.center_mm) < 25:
                        self.assertGreaterEqual(opening_distance(one,two), 1.5-1e-7)
                polygon = result.cells[0].polygon_mm
                width = max(x for x,y in polygon)-min(x for x,y in polygon)
                self.assertAlmostEqual(width, 10)

    def test_wrap_preserves_opening_size_and_never_narrows_the_seam_gap(self):
        settings = PatternSettings(layout_mode='fill', edge_mode='whole', pitch_mm=11.5, web_mm=1.5)
        result = build_layout(settings, (0,100,0,50), 100)
        self.assertEqual(result.pitch_mm, 12.5)
        polygon = result.cells[0].polygon_mm
        self.assertAlmostEqual(max(x for x,y in polygon)-min(x for x,y in polygon), 10)
        rows = {}
        for cell in result.cells:
            rows.setdefault(round(cell.center_mm[1],7),[]).append(cell.center_mm[0])
        for row in rows.values():
            row.sort()
            self.assertEqual(len(row), 8)
            steps = [b-a for a,b in zip(row,row[1:])] + [100-row[-1]+row[0]]
            self.assertTrue(all(step >= 11.5 for step in steps))
            self.assertAlmostEqual(min(steps), max(steps))

    def test_dense_fill_refuses_instead_of_silently_resizing_or_dropping_cells(self):
        settings = PatternSettings(layout_mode='fill', pitch_mm=2, web_mm=.5)
        with self.assertRaises(PatternDensityError):
            build_layout(settings, (0,200,0,200))
        self.assertEqual(settings.pitch_mm, 2)
        self.assertEqual(settings.web_mm, .5)

    def test_trim_acceptance_is_bounded_and_does_not_change_fill_size(self):
        calls = []
        settings = PatternSettings(layout_mode='fill')
        layout = build_layout(settings,(0,80,0,60),accept=lambda cell: calls.append(cell) or cell.center_mm[0]<40)
        self.assertTrue(layout.cells)
        self.assertTrue(all(cell.center_mm[0]<40 for cell in layout.cells))
        self.assertEqual(layout.pitch_mm, settings.pitch_mm)
        self.assertLessEqual(len(calls), 600)

    def test_all_layout_modes_round_trip_in_the_unchanged_strict_snapshot(self):
        for mode in ('balanced','fill','fit','fixed'):
            settings = PatternSettings(layout_mode=mode)
            self.assertEqual(PatternSettings.from_dict(settings.to_dict()), settings)
            self.assertEqual(len(settings.to_dict()),28)
