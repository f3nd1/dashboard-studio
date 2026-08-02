"""Full-path tests for the count-by-single-dimension slice.

IMPORTANT: These tests prove the validate -> plan -> execute LOGIC against
in-memory FIXTURE data only. The academic-year values and counts below are
invented placeholders, NOT real United Ceres College data. They have NOT been
checked against the live Bench or the Metabase baseline query in
reference/metabase/admission_dashboard_queries.sql ("Student applicants by
year"). Validating the live number against that baseline is a separate
follow-up task that requires a real staging connection.
"""

import unittest
from collections import Counter

from dashboard_studio.analytics.query_engine import build_query_plan, execute_query_plan


class TestCountByAcademicYear(unittest.TestCase):
    def setUp(self):
        self.dataset = {
            "source_doctype": "Student Applicant",
            "allowed_fields": ["name", "academic_year"],
            "restricted_fields": ["passport_no"],
        }
        # FIXTURE ONLY — placeholder academic years, not real UCC data.
        self.fixture = (
            [{"academic_year": "2022"}] * 2
            + [{"academic_year": "2023"}] * 3
            + [{"academic_year": "2024"}] * 1
        )

    def _fetch(self, doctype, dimension, conditions, limit):
        """Emulate a grouped DB COUNT over the fixture rows."""
        counts = Counter(row[dimension] for row in self.fixture)
        rows = [{dimension: value, "count": n} for value, n in counts.items()]
        return rows[:limit]

    def _plan(self):
        return build_query_plan(
            {
                "dimension": "academic_year",
                "measure": "name",
                "aggregation": "count",
                "conditions": [],
            },
            self.dataset,
        )

    def test_full_path_matches_fixture_counts(self):
        result = execute_query_plan(
            self._plan(), fetch=self._fetch, permission_check=lambda: None
        )
        self.assertEqual(
            result,
            [
                {"academic_year": "2022", "count": 2},
                {"academic_year": "2023", "count": 3},
                {"academic_year": "2024", "count": 1},
            ],
        )

    def test_multiple_dimensions_are_out_of_scope(self):
        plan = self._plan()
        plan["group_by"] = ["academic_year", "program"]
        with self.assertRaises(NotImplementedError):
            execute_query_plan(plan, fetch=self._fetch, permission_check=lambda: None)

    def test_non_count_aggregation_is_out_of_scope(self):
        plan = self._plan()
        plan["measure"]["aggregation"] = "sum"
        with self.assertRaises(NotImplementedError):
            execute_query_plan(plan, fetch=self._fetch, permission_check=lambda: None)

    def test_mixed_type_dimension_values_do_not_crash_sort(self):
        # A dimension can come back int from one source and str from another;
        # sorting must fall back to string order instead of raising TypeError.
        def fetch(doctype, dimension, conditions, limit):
            return [
                {"academic_year": 2024, "count": 1},
                {"academic_year": "2022", "count": 2},
                {"academic_year": None, "count": 1},
            ]

        result = execute_query_plan(self._plan(), fetch=fetch, permission_check=lambda: None)
        self.assertEqual([row["academic_year"] for row in result], ["2022", 2024, None])

    def test_result_exceeding_max_groups_is_rejected(self):
        plan = self._plan()
        plan["limits"]["max_groups"] = 1  # ceiling below the 3 fixture groups
        with self.assertRaises(ValueError):
            execute_query_plan(plan, fetch=self._fetch, permission_check=lambda: None)


if __name__ == "__main__":
    unittest.main()
