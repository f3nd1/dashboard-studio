"""Logic tests for the DS Metric -> query engine connection.

Proves a DS Metric *record* (built here as a plain dict, not a live doc) drives
the same engine path as the raw-config case and yields the same result, and that
the scope guards fire (status gate, Count-only, Static-filters-only,
unsupported operators).

SCHEMA-AND-LOGIC ONLY: this does NOT verify anything on a live Frappe site. No
bench migrate, no real DS Metric doc, no real UCC data. The academic-year values
and counts are invented fixtures. Live-server verification remains a separate
follow-up.
"""

import unittest
from collections import Counter

from dashboard_studio.analytics.query_engine import (
    build_plan_from_ds_metric,
    build_query_plan,
    execute_query_plan,
)


def _fetch_factory(rows):
    """A grouped-COUNT fetch over in-memory fixture rows."""

    def _fetch(doctype, dimension, conditions, limit):
        selected = rows
        for cond in conditions:
            if cond["operator"] == "=":
                selected = [r for r in selected if r.get(cond["field"]) == cond["value"]]
        counts = Counter(r[dimension] for r in selected)
        return [{dimension: v, "count": n} for v, n in counts.items()][:limit]

    return _fetch


class TestDSMetricExecution(unittest.TestCase):
    def setUp(self):
        # FIXTURE ONLY — placeholder academic years, not real UCC data.
        self.rows = (
            [{"academic_year": "2022", "application_status": "Admitted"}] * 2
            + [{"academic_year": "2023", "application_status": "Admitted"}] * 3
            + [{"academic_year": "2024", "application_status": "Pending"}] * 1
        )
        self.metric = {
            "metric_name": "Student Applicants by Year",
            "status": "Approved",
            "calculation_type": "Count",
            "source_doctype": "Student Applicant",
            "group_by_field": "academic_year",
            "value_field": "name",
            # Block-by-default allowlist: every referenced field must be listed.
            "allowed_fields": "academic_year\nname\napplication_status",
            "metric_filters": [],
        }

    def _run(self, metric):
        plan = build_plan_from_ds_metric(metric)
        return execute_query_plan(
            plan, fetch=_fetch_factory(self.rows), permission_check=lambda: None
        )

    def test_ds_metric_matches_raw_config_path(self):
        # Same numbers whether driven by a DS Metric or the raw engine config.
        ds_result = self._run(self.metric)
        raw_plan = build_query_plan(
            {"dimension": "academic_year", "measure": "name", "aggregation": "count", "conditions": []},
            {"source_doctype": "Student Applicant", "allowed_fields": [], "restricted_fields": []},
        )
        raw_result = execute_query_plan(
            raw_plan, fetch=_fetch_factory(self.rows), permission_check=lambda: None
        )
        self.assertEqual(ds_result, raw_result)
        self.assertEqual(
            ds_result,
            [
                {"academic_year": "2022", "count": 2},
                {"academic_year": "2023", "count": 3},
                {"academic_year": "2024", "count": 1},
            ],
        )

    def test_static_filter_maps_to_conditions(self):
        metric = dict(self.metric)
        metric["metric_filters"] = [
            {"fieldname": "application_status", "operator": "=", "value": "Admitted", "filter_type": "Static"}
        ]
        # Only the 2022/2023 Admitted rows survive the filter.
        self.assertEqual(
            self._run(metric),
            [{"academic_year": "2022", "count": 2}, {"academic_year": "2023", "count": 3}],
        )

    def test_draft_metric_is_blocked(self):
        metric = dict(self.metric, status="Draft")
        with self.assertRaises(ValueError):
            build_plan_from_ds_metric(metric)

    def test_deprecated_metric_is_blocked(self):
        metric = dict(self.metric, status="Deprecated")
        with self.assertRaises(ValueError):
            build_plan_from_ds_metric(metric)

    def test_non_count_calculation_is_blocked(self):
        metric = dict(self.metric, calculation_type="Sum")
        with self.assertRaises(NotImplementedError):
            build_plan_from_ds_metric(metric)

    def test_dynamic_filter_is_blocked(self):
        metric = dict(self.metric)
        metric["metric_filters"] = [
            {"fieldname": "academic_year", "operator": "=", "value": "x", "filter_type": "Dynamic"}
        ]
        with self.assertRaises(NotImplementedError):
            build_plan_from_ds_metric(metric)

    def test_unsupported_operator_is_blocked(self):
        # 'like' is a valid DS Metric Filter operator but not allowed by the
        # engine's operator allowlist, so it must be rejected clearly.
        metric = dict(self.metric)
        metric["metric_filters"] = [
            {"fieldname": "academic_year", "operator": "like", "value": "202%", "filter_type": "Static"}
        ]
        with self.assertRaises(Exception):
            build_plan_from_ds_metric(metric)

    def test_missing_group_by_is_blocked(self):
        metric = dict(self.metric, group_by_field="")
        with self.assertRaises(ValueError):
            build_plan_from_ds_metric(metric)

    def test_empty_allowlist_blocks_execution(self):
        # Block-by-default: no allowed_fields -> refuse to run.
        metric = dict(self.metric, allowed_fields="")
        with self.assertRaises(ValueError):
            build_plan_from_ds_metric(metric)
        del metric["allowed_fields"]
        with self.assertRaises(ValueError):
            build_plan_from_ds_metric(dict(metric))

    def test_out_of_allowlist_field_is_rejected(self):
        # group_by references academic_year, but the allowlist omits it.
        metric = dict(self.metric, allowed_fields="name")
        with self.assertRaises(Exception):
            build_plan_from_ds_metric(metric)

    def test_comma_separated_allowlist_is_parsed(self):
        metric = dict(self.metric, allowed_fields="academic_year, name")
        # academic_year + name are allowlisted -> runs fine.
        self.assertEqual(
            self._run(metric),
            [
                {"academic_year": "2022", "count": 2},
                {"academic_year": "2023", "count": 3},
                {"academic_year": "2024", "count": 1},
            ],
        )


if __name__ == "__main__":
    unittest.main()
