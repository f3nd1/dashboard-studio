"""Tests for the EduTrust scope map.

This module is a COPY of data owned by the Sophia runtime (see edutrust.py), so
what is worth testing is not the values themselves but the invariants that stop
the copy rotting: that the DocType's Select options and the map cannot drift
apart, that only canonical codes are present, and that the criterion is always
derivable rather than needing a second stored field.

Pure Python — no Frappe, no Bench.
"""

import json
import os
import unittest

from dashboard_studio.edutrust import CRITERIA, SUBCRITERIA, criterion_of, describe

_DOCTYPE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dashboard_studio", "doctype", "ds_dashboard", "ds_dashboard.json",
)


class TestEdutrustScope(unittest.TestCase):
    def test_all_thirty_two_subcriteria_are_enumerated(self):
        """32 codes, enumerated from POLICY_REGISTRY — never generated."""
        self.assertEqual(len(SUBCRITERIA), 32)
        # Per-criterion counts, as read from the seven Server Scripts.
        expected = {"1": 2, "2": 8, "3": 2, "4": 7, "5": 7, "6": 5, "7": 1}
        actual = {}
        for code in SUBCRITERIA:
            actual[code.split(".")[0]] = actual.get(code.split(".")[0], 0) + 1
        self.assertEqual(actual, expected)

    def test_doctype_options_match_the_map_exactly(self):
        """The Select and the map are two copies; this is what pins them."""
        with open(_DOCTYPE) as handle:
            fields = json.load(handle)["fields"]
        field = next(f for f in fields if f["fieldname"] == "subcriterion")
        options = [line for line in field["options"].split("\n") if line]
        self.assertEqual(options, sorted(SUBCRITERIA))
        self.assertTrue(
            field["options"].startswith("\n"),
            "a blank first option keeps scope optional while authoring",
        )

    def test_only_canonical_criterion_5_codes_are_present(self):
        """Sophia's frontend spells these 5.4/5.5; its server canonicalises them."""
        self.assertIn("5.4.1", SUBCRITERIA)
        self.assertIn("5.5.1", SUBCRITERIA)
        self.assertNotIn("5.4", SUBCRITERIA)
        self.assertNotIn("5.5", SUBCRITERIA)

    def test_overview_is_excluded(self):
        """Sophia never requests 'overview'; a dashboard scoped to it would be lost."""
        self.assertNotIn("overview", SUBCRITERIA)

    def test_criterion_is_derived_from_the_prefix(self):
        self.assertEqual(criterion_of("4.1.1"), "4")
        self.assertEqual(criterion_of("6.5.3"), "6")
        # Every code resolves to a criterion that has a title.
        for code in SUBCRITERIA:
            self.assertIn(criterion_of(code), CRITERIA)

    def test_unknown_codes_resolve_to_nothing_rather_than_guessing(self):
        for bad in ("9.9.9", "4.9.9", "overview", "", None, "5.4"):
            self.assertIsNone(criterion_of(bad), f"{bad!r} must not resolve")
            self.assertIsNone(describe(bad), f"{bad!r} must not describe")

    def test_describe_returns_display_text_without_storing_it(self):
        scope = describe("4.1.1")
        self.assertEqual(scope["criterion"], "4")
        self.assertEqual(scope["subcriterion"], "4.1.1")
        self.assertEqual(scope["subcriterion_title"], "Pre-Course Counselling, Selection and Admissions")
        self.assertEqual(scope["criterion_title"], "Student Protection and Support Services")
        self.assertEqual(scope["label"], "Criterion 4 · 4.1.1")

    def test_every_criterion_one_to_seven_is_covered(self):
        self.assertEqual(sorted(CRITERIA), ["1", "2", "3", "4", "5", "6", "7"])


if __name__ == "__main__":
    unittest.main()
