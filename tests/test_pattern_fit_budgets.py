"""Automatic multi-face work sharing stays within the native operation budget."""

import unittest

from Partelier.partelier.tools.patterns.fusion import _face_budgets


class PatternFitBudgetTests(unittest.TestCase):
    def test_one_or_two_faces_keep_the_full_per_face_budget(self):
        self.assertEqual(_face_budgets([100]),(200,))
        self.assertEqual(_face_budgets([100,100]),(200,200))

    def test_unequal_areas_share_without_exceeding_either_limit(self):
        for areas in ([100,100,100],[10000,1,1],[10000,10000,1],[1]*100):
            with self.subTest(areas=areas):
                budgets=_face_budgets(areas)
                self.assertEqual(sum(budgets),400)
                self.assertEqual(len(budgets),len(areas))
                self.assertTrue(all(1<=budget<=200 for budget in budgets))
                self.assertEqual(_face_budgets([area*100 for area in areas]),budgets)

    def test_small_rims_do_not_consume_the_large_faces_allocation(self):
        budgets=_face_budgets([10000,10000,1])
        self.assertGreaterEqual(min(budgets[:2]),199)
        self.assertEqual(budgets[2],1)


if __name__=='__main__':unittest.main()
