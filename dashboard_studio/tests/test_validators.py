import unittest

from dashboard_studio.analytics.query_engine import build_query_plan
from dashboard_studio.analytics.validators import DefinitionValidationError, validate_metric_config


class TestMetricValidation(unittest.TestCase):
    def setUp(self):
        self.dataset = {
            "source_doctype": "Student Applicant",
            "allowed_fields": ["name", "academic_year", "application_status"],
            "restricted_fields": ["passport_no"],
        }

    def test_grouped_count_plan(self):
        plan = build_query_plan(
            {
                "dimension": "academic_year",
                "measure": "name",
                "aggregation": "count",
                "conditions": [],
            },
            self.dataset,
        )
        self.assertEqual(plan["source"]["doctype"], "Student Applicant")
        self.assertEqual(plan["group_by"], ["academic_year"])
        self.assertFalse(plan["executable"])

    def test_restricted_field_is_rejected(self):
        with self.assertRaises(DefinitionValidationError):
            validate_metric_config(
                {
                    "dimension": "passport_no",
                    "measure": "name",
                    "aggregation": "count",
                },
                self.dataset,
            )

    def test_unknown_aggregation_is_rejected(self):
        with self.assertRaises(DefinitionValidationError):
            validate_metric_config(
                {
                    "dimension": "academic_year",
                    "measure": "name",
                    "aggregation": "median",
                },
                self.dataset,
            )


if __name__ == "__main__":
    unittest.main()
