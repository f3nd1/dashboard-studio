"""Tests for the result-parity arithmetic.

FIXTURE ONLY: these prove the comparison LOGIC. They say nothing about whether
this app's numbers match real UCC figures — that needs the live-data validation
still blocked on staging access.
"""

import unittest

from dashboard_studio.analytics.comparison import (
    DISCREPANCY,
    FLAGGED,
    MATCH,
    compare_result_sets,
    compare_values,
)


class TestCompareValues(unittest.TestCase):
    def test_equal_values_match(self):
        self.assertEqual(compare_values(10, 10)["status"], MATCH)

    def test_difference_and_percentage(self):
        result = compare_values(200, 180)
        self.assertEqual(result["status"], DISCREPANCY)
        self.assertEqual(result["difference"], -20)
        self.assertEqual(result["difference_pct"], -10.0)

    def test_strings_are_parsed(self):
        # The DocType stores these as Data, so they arrive as strings.
        result = compare_values("1,200", "1200")
        self.assertEqual(result["status"], MATCH)

    def test_tolerance_absorbs_small_differences(self):
        self.assertEqual(compare_values(100, 101, tolerance_pct=2)["status"], MATCH)
        self.assertEqual(compare_values(100, 105, tolerance_pct=2)["status"], DISCREPANCY)

    def test_unparsable_is_flagged_not_treated_as_zero(self):
        result = compare_values("n/a", 5)
        self.assertEqual(result["status"], FLAGGED)
        self.assertIsNone(result["difference"])

    def test_missing_value_is_flagged(self):
        self.assertEqual(compare_values(None, 5)["status"], FLAGGED)
        self.assertEqual(compare_values(5, None)["status"], FLAGGED)

    def test_zero_baseline_has_no_percentage_but_still_compares(self):
        same = compare_values(0, 0)
        self.assertEqual(same["status"], MATCH)
        grew = compare_values(0, 7)
        self.assertEqual(grew["status"], DISCREPANCY)
        self.assertEqual(grew["difference"], 7)
        self.assertIsNone(grew["difference_pct"], "no meaningful percentage against zero")

    def test_accepted_is_never_produced_by_arithmetic(self):
        # Accepting a difference is a reviewer's decision, not a computation.
        for pair in ((10, 10), (10, 12), ("x", 1), (None, None)):
            self.assertIn(compare_values(*pair)["status"], (MATCH, DISCREPANCY, FLAGGED))


class TestCompareResultSets(unittest.TestCase):
    def setUp(self):
        # FIXTURE ONLY — invented academic years and counts.
        self.source = [
            {"academic_year": "2022", "count": 2},
            {"academic_year": "2023", "count": 3},
            {"academic_year": "2024", "count": 1},
        ]

    def test_identical_sets_match(self):
        result = compare_result_sets(self.source, list(self.source))
        self.assertEqual(result["status"], MATCH)
        self.assertEqual(result["summary"], {"matched": 3, "discrepancies": 0, "flagged": 0})
        self.assertEqual(result["totals"]["status"], MATCH)

    def test_differing_group_is_reported(self):
        target = [
            {"academic_year": "2022", "count": 2},
            {"academic_year": "2023", "count": 5},
            {"academic_year": "2024", "count": 1},
        ]
        result = compare_result_sets(self.source, target)
        self.assertEqual(result["status"], DISCREPANCY)
        row = [r for r in result["rows"] if r["label"] == "2023"][0]
        self.assertEqual(row["difference"], 2)
        self.assertEqual(result["totals"]["difference"], 2)

    def test_group_missing_from_target_is_flagged_not_dropped(self):
        target = [{"academic_year": "2022", "count": 2}, {"academic_year": "2023", "count": 3}]
        result = compare_result_sets(self.source, target)
        self.assertEqual(result["status"], FLAGGED)
        row = [r for r in result["rows"] if r["label"] == "2024"][0]
        self.assertEqual(row["status"], FLAGGED)
        self.assertEqual(len(result["rows"]), 3, "every group is reported")

    def test_extra_group_in_target_is_also_reported(self):
        target = list(self.source) + [{"academic_year": "2025", "count": 4}]
        result = compare_result_sets(self.source, target)
        self.assertEqual(result["status"], FLAGGED)
        self.assertIn("2025", [r["label"] for r in result["rows"]])

    def test_flagged_outranks_discrepancy_overall(self):
        target = [
            {"academic_year": "2022", "count": 99},  # discrepancy
            {"academic_year": "2023", "count": 3},
        ]  # 2024 missing -> flagged
        result = compare_result_sets(self.source, target)
        self.assertEqual(result["status"], FLAGGED, "unknown beats known-unequal")
        self.assertEqual(result["summary"]["discrepancies"], 1)
        self.assertEqual(result["summary"]["flagged"], 1)

    def test_empty_sets_match(self):
        self.assertEqual(compare_result_sets([], [])["status"], MATCH)


if __name__ == "__main__":
    unittest.main()
