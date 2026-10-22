"""Input-contract tests that do not require Autodesk Fusion."""

import math
import unittest

from Partelier.partelier.settings import HoneycombSettings


class HoneycombSettingsTests(unittest.TestCase):
    def test_fusion_centimetres_are_converted_once(self):
        settings = HoneycombSettings.from_centimetres(1.0, 0.12)
        self.assertEqual(settings, HoneycombSettings(10.0, 1.2))

    def test_cell_size_rejects_nonpositive_nonfinite_and_nonnumeric_values(self):
        for value in (0, -1, math.inf, -math.inf, math.nan, True, "10", None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Cell size"):
                HoneycombSettings(cell_size_mm=value)

    def test_wall_rejects_nonpositive_nonfinite_and_nonnumeric_values(self):
        for value in (0, -1, math.inf, -math.inf, math.nan, False, "1.2", None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Wall thickness"):
                HoneycombSettings(wall_thickness_mm=value)

    def test_wall_cannot_consume_the_cell_opening(self):
        for wall in (10.0, 11.0):
            with self.subTest(wall=wall), self.assertRaisesRegex(ValueError, "smaller"):
                HoneycombSettings(cell_size_mm=10.0, wall_thickness_mm=wall)

    def test_positive_opening_has_no_unconfirmed_printer_specific_limit(self):
        settings = HoneycombSettings(cell_size_mm=2.0, wall_thickness_mm=1.9)
        self.assertAlmostEqual(settings.cell_size_mm - settings.wall_thickness_mm, 0.1)

    def test_internal_values_are_validated_after_conversion(self):
        with self.assertRaises(ValueError):
            HoneycombSettings.from_centimetres(math.nan, 0.12)
        with self.assertRaises(ValueError):
            HoneycombSettings.from_centimetres(1.0, 1.1)

if __name__ == "__main__":
    unittest.main()
