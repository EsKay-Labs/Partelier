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
        SnapFitSettings(reach_mm=3.31, lead_in_mm=3, chamfer_edges=False)

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


    def test_new_styles_and_finish_defaults_are_explicit_settings(self):
        current = SnapFitSettings()
        self.assertEqual(len(current.to_dict()), 21)
        self.assertEqual(current.snap_style, "standard")
        self.assertTrue(current.chamfer_edges)
        self.assertTrue(current.print_support)
        self.assertEqual(current.chamfer_size_mm, .3)
        for style in ("standard", "tapered", "twin"):
            self.assertEqual(SnapFitSettings(snap_style=style).snap_style, style)

    def test_unknown_styles_and_nonboolean_finish_flags_are_refused(self):
        for style in ("other", None, True, 1):
            with self.subTest(style=style), self.assertRaisesRegex(ValueError, "Snap style"):
                SnapFitSettings(snap_style=style)
        for key in ("chamfer_edges", "print_support"):
            for value in (1, 0, "yes", None):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    SnapFitSettings(**{key: value})

    def test_twin_gap_and_tapered_tip_constrain_requested_chamfer_without_shrinking(self):
        with self.assertRaisesRegex(ValueError, "Twin arms"):
            SnapFitSettings(snap_style="twin", width_mm=1)
        with self.assertRaisesRegex(ValueError, "tip thickness"):
            SnapFitSettings(snap_style="tapered", chamfer_size_mm=.5)
        with self.assertRaisesRegex(ValueError, "Chamfer size"):
            SnapFitSettings(chamfer_size_mm=1.5)
        wider = SnapFitSettings(snap_style="twin", width_mm=12, thickness_mm=1.6,
                                hook_depth_mm=2, clearance_mm=.1, chamfer_size_mm=.75)
        self.assertEqual(wider.chamfer_size_mm, .75)
        current = SnapFitSettings(snap_style="tapered", chamfer_size_mm=.4)
        self.assertEqual(current.chamfer_size_mm, .4)

    def test_full_new_contract_refuses_old_partial_values_outside_recipe_migration(self):
        old = {key: value for key, value in SnapFitSettings().to_dict().items()
               if key not in {"snap_style", "print_support", "chamfer_edges", "chamfer_size_mm",
                              "snap_family", "ball_radius_mm", "torsion_radius_mm",
                              "annular_bead_width_mm", "annular_bead_height_mm", "annular_offset_mm"}}
        self.assertEqual(len(old), 11)
        with self.assertRaisesRegex(ValueError, "exactly"):
            SnapFitSettings.from_dict(old)

    def test_all_four_families_roundtrip_complete_twenty_one_field_snapshots(self):
        for family in ("hook", "ball_detent", "torsion", "annular"):
            current = SnapFitSettings(snap_family=family, chamfer_edges=family != "annular")
            self.assertEqual(len(current.to_dict()), 21)
            self.assertEqual(SnapFitSettings.from_dict(current.to_dict()), current)
        with self.assertRaisesRegex(ValueError, "Choose hook"):
            SnapFitSettings(snap_family="unknown")


if __name__ == "__main__":
    unittest.main()
