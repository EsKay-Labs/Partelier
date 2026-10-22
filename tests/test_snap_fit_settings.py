"""The snap-fit input contract is independent of Autodesk Fusion."""

from dataclasses import FrozenInstanceError, fields, replace
import json
import math
import unittest

from Partelier.partelier.tools.snap_fit.settings import SnapFitSettings


class SnapFitSettingsTests(unittest.TestCase):
    def test_defaults_describe_one_exterior_cantilever(self):
        settings = SnapFitSettings()
        self.assertEqual((settings.width_mm, settings.thickness_mm, settings.reach_mm),
                         (8.0, 1.5, 16.0))
        self.assertEqual(settings.snap_count, 1)
        self.assertEqual(settings.clearance_mm, .3)
        self.assertEqual((settings.hook_depth_mm, settings.lead_in_mm), (1.0, 3.0))
        self.assertEqual((settings.root_length_mm, settings.attachment_overlap_mm), (4.0, .5))

    def test_settings_are_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            SnapFitSettings().width_mm = 7

    def test_integer_lengths_normalize_to_float(self):
        settings = SnapFitSettings(width_mm=8, start_margin_mm=0)
        self.assertIs(type(settings.width_mm), float)
        self.assertIs(type(settings.start_margin_mm), float)
        self.assertIs(type(settings.snap_count), int)

    def test_each_length_rejects_invalid_numeric_types_and_nonfinite_values(self):
        for field in fields(SnapFitSettings):
            if not field.name.endswith("_mm"):
                continue
            for value in (-1, math.inf, -math.inf, math.nan, True, False, "3", None,
                          10 ** 1000):
                with self.subTest(field=field.name, value=repr(value)[:30]):
                    with self.assertRaises(ValueError):
                        replace(SnapFitSettings(), **{field.name: value})

    def test_only_margins_allow_zero(self):
        for field in fields(SnapFitSettings):
            if not field.name.endswith("_mm"):
                continue
            with self.subTest(field=field.name):
                if field.name in {"start_margin_mm", "end_margin_mm"}:
                    replace(SnapFitSettings(), **{field.name: 0})
                else:
                    with self.assertRaises(ValueError):
                        replace(SnapFitSettings(), **{field.name: 0})

    def test_count_is_bounded_integer_without_bool_coercion(self):
        for value in (0, 21, 1.0, True, False, "2", None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Snap count"):
                SnapFitSettings(snap_count=value)
        for value in (1, 2, 20):
            self.assertEqual(SnapFitSettings(snap_count=value).snap_count, value)

    def test_lead_in_must_finish_beyond_root_with_clearance(self):
        for reach, lead_in in ((3, 3), (2, 3), (3.3, 3), (3.1, 3)):
            with self.subTest(reach=reach, lead_in=lead_in), self.assertRaises(ValueError):
                SnapFitSettings(reach_mm=reach, lead_in_mm=lead_in)
        SnapFitSettings(reach_mm=3.31, lead_in_mm=3)

    def test_overflowing_derived_dimensions_are_refused(self):
        for changes in ({"thickness_mm": 1e308, "attachment_overlap_mm": 1e308},
                        {"thickness_mm": 1e308, "hook_depth_mm": 1e308},
                        {"reach_mm": 1e308},
                        {"width_mm": 1e308},
                        {"clearance_mm": 1e308, "reach_mm": 1.1e308}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "distinct|Reach"):
                SnapFitSettings(**changes)

    def test_finite_endpoints_cannot_hide_an_overflowing_box_extent(self):
        changes = {"width_mm": 1e308, "thickness_mm": 1e307,
                   "reach_mm": 1e308, "clearance_mm": 1e307,
                   "hook_depth_mm": 1e307, "lead_in_mm": 2e307,
                   "root_length_mm": 1e308}
        with self.assertRaisesRegex(ValueError, "distinct finite"):
            SnapFitSettings(**changes)
        changes["root_length_mm"] = 1e307
        SnapFitSettings(**changes)

    def test_positive_values_lost_at_float_precision_are_refused(self):
        for changes in ({"thickness_mm": 1e-30}, {"clearance_mm": 1e-30},
                        {"lead_in_mm": 1e-30}, {"width_mm": 5e-324}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                SnapFitSettings(**changes)

    def test_atomic_recipe_roundtrip_uses_all_fields(self):
        settings = SnapFitSettings(snap_count=3, width_mm=9, end_margin_mm=8)
        snapshot = json.loads(json.dumps(settings.to_dict()))
        self.assertEqual(SnapFitSettings.from_dict(snapshot), settings)
        self.assertEqual(set(snapshot), {field.name for field in fields(SnapFitSettings)})
        snapshot["width_mm"] = 2
        self.assertEqual(settings.width_mm, 9)

    def test_partial_extra_and_nonobject_recipes_are_refused(self):
        complete = SnapFitSettings().to_dict()
        missing = dict(complete)
        del missing["lead_in_mm"]
        extra = dict(complete, profile="other")
        for recipe in (missing, extra, {}, None, [], 5, "{}"):
            with self.subTest(recipe=recipe), self.assertRaises(ValueError):
                SnapFitSettings.from_dict(recipe)

    def test_recipe_values_are_validated_without_coercion(self):
        for changes in ({"width_mm": "8"}, {"snap_count": True}, {"clearance_mm": -1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                SnapFitSettings.from_dict(dict(SnapFitSettings().to_dict(), **changes))


if __name__ == "__main__":
    unittest.main()
