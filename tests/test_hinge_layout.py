"""Equal multi-hinge placement and pin-envelope spacing without Autodesk APIs."""

from dataclasses import FrozenInstanceError
import math
import unittest

from Partelier.partelier.tools.hinge.layout import build_hinge_layout
from Partelier.partelier.tools.hinge.settings import HingeSettings


class HingeLayoutTests(unittest.TestCase):
    def test_default_single_hinge_is_centred(self):
        layout = build_hinge_layout(HingeSettings(), 100)
        self.assertEqual(layout.edge_length_mm, 100.0)
        self.assertEqual(layout.gap_mm, 0.0)
        self.assertEqual(len(layout.placements), 1)
        placement = layout.placements[0]
        self.assertEqual((placement.index, placement.center_mm,
                          placement.start_mm, placement.end_mm), (0, 0, -20, 20))

    def test_single_hinge_centres_within_asymmetric_minimum_margins(self):
        settings = HingeSettings(start_margin_mm=10, end_margin_mm=20)
        placement = build_hinge_layout(settings, 100).placements[0]
        self.assertEqual((placement.start_mm, placement.center_mm, placement.end_mm), (-25, -5, 15))
        self.assertGreaterEqual(placement.start_mm + 50, settings.start_margin_mm)
        self.assertGreaterEqual(50 - placement.end_mm, settings.end_margin_mm)

    def test_single_exact_fit_and_margins_measure_body_not_pin(self):
        settings = HingeSettings(start_margin_mm=10, end_margin_mm=10, pin_overhang_mm=25)
        placement = build_hinge_layout(settings, 60).placements[0]
        self.assertEqual((placement.start_mm, placement.end_mm), (-20, 20))

    def test_multiple_hinges_have_exact_outer_margins_and_equal_gaps(self):
        settings = HingeSettings(hinge_count=2, start_margin_mm=10, end_margin_mm=20)
        layout = build_hinge_layout(settings, 120)
        self.assertEqual(layout.gap_mm, 10)
        self.assertEqual([(p.index, p.start_mm, p.center_mm, p.end_mm) for p in layout.placements],
                         [(0, -50, -30, -10), (1, 0, 20, 40)])

    def test_spacing_matrix_fills_the_remaining_edge_and_keeps_pins_apart(self):
        for count in (2, 3, 7, 20):
            for length, start_margin, end_margin, desired_gap in (
                (40, 0, 0, 12), (12, 3, 9, 5), (100, 20, 5, 8),
            ):
                settings = HingeSettings(hinge_count=count, length_mm=length,
                                         start_margin_mm=start_margin, end_margin_mm=end_margin)
                edge = count * length + (count - 1) * desired_gap + start_margin + end_margin
                layout = build_hinge_layout(settings, edge)
                with self.subTest(count=count, length=length):
                    self.assertAlmostEqual(layout.gap_mm, desired_gap)
                    self.assertEqual(layout.placements[0].start_mm, -edge / 2 + start_margin)
                    self.assertEqual(layout.placements[-1].end_mm, edge / 2 - end_margin)
                    for index, placement in enumerate(layout.placements):
                        self.assertEqual(placement.index, index)
                        self.assertAlmostEqual(placement.end_mm - placement.start_mm, length)
                        self.assertAlmostEqual(placement.center_mm,
                                               (placement.start_mm + placement.end_mm) / 2)
                        if index:
                            previous = layout.placements[index - 1]
                            pin_gap = (placement.start_mm - settings.pin_overhang_mm
                                       - previous.end_mm - settings.pin_overhang_mm)
                            self.assertAlmostEqual(placement.start_mm - previous.end_mm, desired_gap)
                            self.assertGreaterEqual(pin_gap + 1e-12, settings.axial_gap_mm)

    def test_decimal_exact_fit_allows_only_arithmetic_roundoff(self):
        settings = HingeSettings(hinge_count=2)
        layout = build_hinge_layout(settings, 84.3)
        self.assertGreaterEqual(layout.gap_mm, 2 * settings.pin_overhang_mm + settings.axial_gap_mm)
        self.assertAlmostEqual(layout.gap_mm, 4.3)
        self.assertEqual(layout.placements[0].start_mm, -84.3 / 2)
        self.assertEqual(layout.placements[-1].end_mm, 84.3 / 2)
        with self.assertRaisesRegex(ValueError, "do not fit"):
            build_hinge_layout(settings, 84.299999)

    def test_excluding_pins_uses_axial_gap_as_minimum_inter_hinge_spacing(self):
        settings = HingeSettings(hinge_count=2, include_pin=False)
        layout = build_hinge_layout(settings, 80.3)
        self.assertAlmostEqual(layout.gap_mm, 0.3)
        with self.assertRaisesRegex(ValueError, "do not fit"):
            build_hinge_layout(HingeSettings(hinge_count=2), 80.3)

    def test_count_length_margins_and_pin_envelope_can_each_prevent_fit(self):
        cases = (
            (HingeSettings(), 39.9),
            (HingeSettings(start_margin_mm=5, end_margin_mm=6), 50),
            (HingeSettings(hinge_count=3), 120),
            (HingeSettings(hinge_count=2, start_margin_mm=10, end_margin_mm=10), 100),
            (HingeSettings(hinge_count=2, pin_overhang_mm=5), 90),
        )
        for settings, edge in cases:
            with self.subTest(settings=settings, edge=edge), self.assertRaisesRegex(ValueError, "fit"):
                build_hinge_layout(settings, edge)

    def test_zero_or_negative_usable_interval_is_rejected(self):
        for start_margin, end_margin in ((50, 50), (60, 50), (100, 0), (0, 100)):
            settings = HingeSettings(start_margin_mm=start_margin, end_margin_mm=end_margin)
            with self.subTest(start=start_margin, end=end_margin), self.assertRaisesRegex(ValueError, "no usable edge"):
                build_hinge_layout(settings, 100)

    def test_edge_input_is_strict_finite_and_positive(self):
        for value in (0, -1, math.inf, -math.inf, math.nan, True, "100", None, 10 ** 1000):
            with self.subTest(value=repr(value)), self.assertRaisesRegex(ValueError, "Reference edge length"):
                build_hinge_layout(HingeSettings(), value)
        with self.assertRaisesRegex(ValueError, "HingeSettings"):
            build_hinge_layout(HingeSettings().to_dict(), 100)

    def test_collapsed_numeric_placements_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "collapse"):
            build_hinge_layout(HingeSettings(hinge_count=2), 1e20)
        with self.assertRaisesRegex(ValueError, "no usable edge"):
            build_hinge_layout(HingeSettings(), 5e-324)
        with self.assertRaisesRegex(ValueError, "no usable edge"):
            build_hinge_layout(HingeSettings(start_margin_mm=1e308, end_margin_mm=1e308), 100)

    def test_layout_results_are_immutable_and_do_not_change_unit_shape(self):
        settings = HingeSettings(hinge_count=3)
        layout = build_hinge_layout(settings, 160)
        self.assertIsInstance(layout.placements, tuple)
        with self.assertRaises(FrozenInstanceError):
            layout.placements[0].center_mm = 0
        with self.assertRaises(FrozenInstanceError):
            layout.gap_mm = 4
        self.assertEqual(settings.length_mm, 40)
        self.assertEqual(build_hinge_layout(settings, 160), layout)


if __name__ == "__main__":
    unittest.main()
