"""Attached support option contracts; no printer or native kernel claims."""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import re
import unittest

from Partelier.partelier.tools.hinge.planner import build_hinge_plan
from Partelier.partelier.tools.hinge.settings import HingeSettings


class WebProfileSettingsTests(unittest.TestCase):
    def test_new_create_defaults_to_taper_and_roundtrips_complete_snapshot(self):
        settings = HingeSettings()
        self.assertEqual(settings.web_profile, "tangent")
        self.assertEqual(HingeSettings.from_dict(settings.to_dict()), settings)
        with self.assertRaises(FrozenInstanceError):
            settings.web_profile = "flat"

    def test_support_enum_is_strict_and_required_in_current_settings(self):
        for value in ("tangent", "flat"):
            settings = HingeSettings(web_profile=value)
            self.assertEqual(HingeSettings.from_dict(settings.to_dict()), settings)
        for value in ("Tangent", "taper", "", None, True, 1, ["flat"]):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Attachment shape"):
                HingeSettings(web_profile=value)
        incomplete = HingeSettings().to_dict()
        incomplete.pop("web_profile")
        with self.assertRaisesRegex(ValueError, "exactly"):
            HingeSettings.from_dict(incomplete)

    def test_support_option_preserves_nominal_layout_bore_and_legacy_bounds(self):
        original = HingeSettings()
        tapered = build_hinge_plan(original)
        flat = build_hinge_plan(replace(original, web_profile="flat"))
        for name in ("knuckles", "webs", "plates", "bore_radius_mm",
                     "pin_start_mm", "pin_end_mm"):
            self.assertEqual(getattr(tapered, name), getattr(flat, name))
        for profile in ("tangent", "flat"):
            with self.subTest(profile=profile), self.assertRaisesRegex(ValueError, "Leaf thickness"):
                HingeSettings(web_profile=profile, leaf_thickness_mm=3)

    def test_html_snapshot_has_every_current_settings_field_and_taper_default(self):
        palette = Path(__file__).resolve().parents[1] / "Partelier/partelier/ui/palette.js"
        source = palette.read_text(encoding="utf-8")
        defaults = re.search(r"const hingeDefaults = \{([^}]+)\};", source).group(1)
        keys = re.findall(r"\b([a-z_]+):", defaults)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), set(HingeSettings().to_dict()))
        self.assertRegex(defaults, r'web_profile:\s*"tangent"')

    def test_inapplicable_modes_keep_stored_choice_without_rejecting_it(self):
        for mode, housing in (("separate", "round"), ("attached", "square"),
                              ("separate", "square")):
            for profile in ("tangent", "flat"):
                settings = HingeSettings(output_mode=mode, knuckle_profile=housing,
                                         web_profile=profile)
                self.assertEqual(HingeSettings.from_dict(settings.to_dict()), settings)


if __name__ == "__main__":
    unittest.main()
