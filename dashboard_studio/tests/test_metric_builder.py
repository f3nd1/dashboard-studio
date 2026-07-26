"""Tests for deriving a DS Metric from a parsed query.

Pure logic — no Frappe, no Bench. The load-bearing cases are the refusals: this
runs unattended when a mapping is confirmed, so anything it cannot describe
exactly must produce nothing rather than an approximate metric.
"""

import unittest

from dashboard_studio.integrations.metabase.metric_builder import (
    metric_from_analysis,
    metric_name,
)
from dashboard_studio.integrations.metabase.parser import analyze_sql

# The query from the live report, verbatim.
AGENT_SQL = """
SELECT `tabStudent Applicant`.`agent` AS `agent`, COUNT(*) AS `count`
FROM `tabStudent Applicant`
GROUP BY `tabStudent Applicant`.`agent`
ORDER BY `tabStudent Applicant`.`agent` ASC
"""


class TestMetricFromAnalysis(unittest.TestCase):
    def test_the_reported_query_end_to_end(self):
        fields, reason = metric_from_analysis(analyze_sql(AGENT_SQL))
        self.assertIsNone(reason)
        self.assertEqual(fields, {
            "metric_name": "Count of Student Applicant by agent",
            "status": "Draft",
            "source_doctype": "Student Applicant",
            "calculation_type": "Count",
            "group_by_field": "agent",
            "value_field": "name",
            "allowed_fields": "agent\nname",
        })

    def test_it_is_always_draft(self):
        """A parser cannot approve a metric. Nothing here may produce Approved."""
        fields, _ = metric_from_analysis(analyze_sql(AGENT_SQL))
        self.assertEqual(fields["status"], "Draft")

    def test_allowed_fields_are_only_what_the_query_names(self):
        fields, _ = metric_from_analysis(analyze_sql(AGENT_SQL))
        self.assertEqual(set(fields["allowed_fields"].split("\n")), {"agent", "name"})

    def test_the_same_query_yields_the_same_name(self):
        """The name is the reuse key — DS Metric is autoname: field:metric_name."""
        first, _ = metric_from_analysis(analyze_sql(AGENT_SQL))
        second, _ = metric_from_analysis(analyze_sql(AGENT_SQL.replace("\n", " ")))
        self.assertEqual(first["metric_name"], second["metric_name"])

    def test_different_dimensions_are_different_metrics(self):
        by_agent, _ = metric_from_analysis(analyze_sql(AGENT_SQL))
        by_year, _ = metric_from_analysis(analyze_sql(
            "SELECT `tabStudent Applicant`.`academic_year`, COUNT(*) "
            "FROM `tabStudent Applicant` GROUP BY `tabStudent Applicant`.`academic_year`"
        ))
        self.assertNotEqual(by_agent["metric_name"], by_year["metric_name"])

    # ---- refusals: what it will not describe ----
    def test_an_unsupported_query_produces_nothing(self):
        fields, reason = metric_from_analysis(
            {"supported": False, "reasons": ["subquery present"]}
        )
        self.assertIsNone(fields)
        self.assertIn("not translated", reason)

    def test_a_filtered_query_is_refused_rather_than_unfiltered(self):
        """Dropping the WHERE would count more rows than the source query, and
        keeping it without naming it would collide with the unfiltered metric."""
        analysis = analyze_sql(
            "SELECT `tabStudent Applicant`.`academic_year`, COUNT(*) "
            "FROM `tabStudent Applicant` "
            "WHERE `tabStudent Applicant`.`application_status` = 'Admitted' "
            "GROUP BY `tabStudent Applicant`.`academic_year`"
        )
        self.assertTrue(analysis["supported"], "fixture must parse, or this proves nothing")
        fields, reason = metric_from_analysis(analysis)
        self.assertIsNone(fields)
        self.assertIn("application_status", reason)

        # ...and it must not collide with the unfiltered version, which is the
        # reason it is refused.
        unfiltered, _ = metric_from_analysis(analyze_sql(
            "SELECT `tabStudent Applicant`.`academic_year`, COUNT(*) "
            "FROM `tabStudent Applicant` GROUP BY `tabStudent Applicant`.`academic_year`"
        ))
        self.assertEqual(unfiltered["metric_name"],
                         metric_name("Count", "Student Applicant", "academic_year"))

    def test_no_group_by_is_refused(self):
        fields, reason = metric_from_analysis(
            {"supported": True, "doctypes": ["X"], "group_by": [],
             "aggregations": [{"function": "COUNT", "argument": "*"}], "filters": []}
        )
        self.assertIsNone(fields)
        self.assertIn("one group-by field", reason)

    def test_two_doctypes_are_refused(self):
        fields, reason = metric_from_analysis(
            {"supported": True, "doctypes": ["A", "B"], "group_by": ["x"],
             "aggregations": [{"function": "COUNT", "argument": "*"}], "filters": []}
        )
        self.assertIsNone(fields)
        self.assertIn("one source DocType", reason)

    def test_an_unmappable_aggregation_is_refused_not_filed_as_custom(self):
        fields, reason = metric_from_analysis(
            {"supported": True, "doctypes": ["X"], "group_by": ["y"], "filters": [],
             "aggregations": [{"function": "STDDEV", "argument": "z"}]}
        )
        self.assertIsNone(fields)
        self.assertIn("STDDEV", reason)

    def test_sum_measures_its_own_column(self):
        fields, _ = metric_from_analysis(
            {"supported": True, "doctypes": ["X"], "group_by": ["y"], "filters": [],
             "aggregations": [{"function": "SUM", "argument": "fee_amount"}]}
        )
        self.assertEqual(fields["calculation_type"], "Sum")
        self.assertEqual(fields["value_field"], "fee_amount")
        self.assertEqual(set(fields["allowed_fields"].split("\n")), {"y", "fee_amount"})

    def test_the_engine_refuses_it_until_a_human_approves_it(self):
        from dashboard_studio.analytics.query_engine import build_plan_from_ds_metric

        fields, _ = metric_from_analysis(analyze_sql(AGENT_SQL))
        with self.assertRaises(ValueError) as caught:
            build_plan_from_ds_metric(dict(fields, metric_filters=[]))
        self.assertIn("Draft", str(caught.exception))

    def test_and_runs_once_approved_because_allowed_fields_is_right(self):
        """The point of deriving allowed_fields: the metric must actually run
        after approval, not merely save. block-by-default refuses an empty list,
        so a metric generated without this would approve and then fail."""
        from dashboard_studio.analytics.query_engine import build_plan_from_ds_metric

        fields, _ = metric_from_analysis(analyze_sql(AGENT_SQL))
        approved = dict(fields, status="Approved", metric_filters=[])
        plan = build_plan_from_ds_metric(approved)
        self.assertEqual(plan["source"]["doctype"], "Student Applicant")
        self.assertEqual(plan["group_by"], ["agent"])
        self.assertEqual(plan["measure"], {"field": "name", "aggregation": "count"})


if __name__ == "__main__":
    unittest.main()
