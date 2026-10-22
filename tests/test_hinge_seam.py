"""Pure seam clearance bounds; these tests do not run a CAD kernel."""

import unittest

from Partelier.partelier.tools.hinge.seam import plan_seam_clearance


class HingeSeamTests(unittest.TestCase):
    def corners(self, width=60, depth=8):
        return ((0, -width / 2, 0), (0, width / 2, 0),
                (0, width / 2, -depth), (0, -width / 2, -depth))

    def test_cut_covers_full_mating_face_not_just_hinge_length(self):
        bounds = plan_seam_clearance(self.corners(), self.corners(), 0.3, 60)
        self.assertEqual((bounds.x_min_mm, bounds.x_max_mm), (-0.15, 0.15))
        self.assertLess(bounds.y_min_mm, -30)
        self.assertGreater(bounds.y_max_mm, 30)
        self.assertLess(bounds.z_min_mm, -8)
        self.assertGreater(bounds.z_max_mm, 0)
        # A 40 mm hinge on this 60 mm edge still needs the whole interface cut.
        self.assertGreater(bounds.y_max_mm - bounds.y_min_mm, 60)

    def test_corner_order_and_winding_do_not_change_bounds(self):
        corners = self.corners()
        self.assertEqual(plan_seam_clearance(corners, corners, 0.3, 60),
                         plan_seam_clearance(corners[2:] + corners[:2], tuple(reversed(corners)), 0.3, 60))

    def test_nonmatching_depth_is_refused(self):
        with self.assertRaisesRegex(ValueError, "matching rectangular"):
            plan_seam_clearance(self.corners(), self.corners(depth=7), 0.3, 60)

    def test_incomplete_edge_span_is_refused(self):
        with self.assertRaisesRegex(ValueError, "full edge"):
            plan_seam_clearance(self.corners(), self.corners(), 0.3, 50)

    def test_nonrectangular_and_duplicate_corners_are_refused(self):
        for corners in (((0, -30, 0), (0, 30, 0), (0, 25, -8), (0, -30, -8)),
                        ((0, -30, 0), (0, 30, 0), (0, 30, -8), (0, 30, -8))):
            with self.subTest(corners=corners), self.assertRaisesRegex(ValueError, "rectangular"):
                plan_seam_clearance(corners, corners, 0.3, 60)

    def test_faces_in_front_or_off_the_seam_are_refused(self):
        for corners in (tuple((x + 0.01, y, z) for x, y, z in self.corners()),
                        tuple((x, y, z + 1) for x, y, z in self.corners())):
            with self.subTest(corners=corners), self.assertRaises(ValueError):
                plan_seam_clearance(corners, corners, 0.3, 60)

    def test_nonfinite_and_kernel_sized_gaps_are_refused(self):
        for gap in (0, -0.3, True, float("nan"), float("inf"), 0.00001):
            with self.subTest(gap=gap), self.assertRaises(ValueError):
                plan_seam_clearance(self.corners(), self.corners(), gap, 60)


if __name__ == "__main__":
    unittest.main()
