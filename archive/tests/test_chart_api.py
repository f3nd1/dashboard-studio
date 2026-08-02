"""Tests for adding, duplicating and removing DS Charts.

Until these endpoints existed the Builder could only edit charts created in the
Frappe form, so the load-bearing cases here are the ones that stop the editor
creating something it should not: an unknown chart type, or a duplicate that
crosses into another dashboard's governance scope.

MOCK-BASED — endpoint logic only, no live Bench. Chart-type validation reads the
real ds_chart.json through the fake's get_meta, so it cannot drift from schema.
"""

import sys
import unittest

from dashboard_studio.tests.test_section_api import (
    _make_fake_frappe,
    _PermissionError,
    _ValidationError,
)


class TestChartApi(unittest.TestCase):
    def setUp(self):
        self._saved = {
            k: v for k, v in sys.modules.items()
            if k == "frappe" or k.startswith("dashboard_studio.api")
        }
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)

        # FIXTURE ONLY — invented dashboards and charts.
        self.store = {
            "DS Dashboard": {"D1": {"name": "D1"}, "D2": {"name": "D2"}},
            "DS Chart": {
                "c1": {
                    "name": "c1", "dashboard": "D1", "section": "sec-a",
                    "chart_title": "Applicants by Year", "chart_type": "Line Chart",
                    "metric": "M1", "description": "Count by year",
                    "pos_x": 0, "pos_y": 0, "width": 6, "height": 4,
                    "chart_filters": [
                        {"fieldname": "application_status", "operator": "=",
                         "value": "Admitted", "filter_type": "Static"}
                    ],
                },
                "c2": {
                    "name": "c2", "dashboard": "D1", "chart_title": "Total",
                    "chart_type": "KPI Card", "pos_x": 6, "pos_y": 4,
                    "width": 3, "height": 2,
                },
                "other": {
                    "name": "other", "dashboard": "D2", "chart_title": "Elsewhere",
                    "chart_type": "Bar Chart", "pos_x": 0, "pos_y": 0,
                    "width": 4, "height": 4,
                },
            },
        }
        self.frappe = _make_fake_frappe(self.store)
        sys.modules["frappe"] = self.frappe
        import dashboard_studio.api.studio as studio

        self.studio = studio
        self.frappe._roles = {"Dashboard Studio Editor"}

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    # ---- role gating ----
    def test_viewer_cannot_create_or_delete(self):
        self.frappe._roles = {"Dashboard Studio Viewer"}
        with self.assertRaises(_PermissionError):
            self.studio.create_chart("D1", "Bar Chart")
        with self.assertRaises(_PermissionError):
            self.studio.delete_chart("c1")

    # ---- create ----
    def test_create_lands_below_existing_charts(self):
        created = self.studio.create_chart("D1", "Bar Chart")
        # c2 occupies rows 4..6, so the first free row is 6.
        self.assertEqual(created["pos_y"], 6)
        self.assertEqual(created["pos_x"], 0)
        self.assertEqual(created["chart_type"], "Bar Chart")
        self.assertEqual(created["dashboard"], "D1")
        self.assertIsNone(created["metric"], "a new chart has no metric yet")

    def test_create_on_empty_dashboard_starts_at_row_zero(self):
        self.assertEqual(self.studio.create_chart("D-empty", "Table")["pos_y"], 0)

    def test_unknown_chart_type_is_rejected(self):
        with self.assertRaises(_ValidationError):
            self.studio.create_chart("D1", "Sankey")
        self.assertEqual(len(self.store["DS Chart"]), 3, "nothing created")

    def test_every_schema_chart_type_is_accepted(self):
        """The picker offers whatever the DocType lists — none may be refused."""
        for chart_type in self.studio._chart_type_options():
            created = self.studio.create_chart("D1", chart_type)
            self.assertEqual(created["chart_type"], chart_type)

    # ---- duplicate ----
    def test_duplicate_copies_metric_description_size_and_filters(self):
        copy = self.studio.create_chart("D1", copy_from="c1")
        self.assertEqual(copy["chart_title"], "Applicants by Year (copy)")
        self.assertEqual(copy["chart_type"], "Line Chart")
        self.assertEqual(copy["metric"], "M1")
        self.assertEqual(copy["description"], "Count by year")
        self.assertEqual(copy["section"], "sec-a")
        self.assertEqual((copy["width"], copy["height"]), (6, 4))
        self.assertEqual(copy["chart_filters"], [
            {"fieldname": "application_status", "operator": "=",
             "value": "Admitted", "filter_type": "Static"}
        ])
        self.assertNotEqual(copy["name"], "c1", "a new record, not the original")
        self.assertEqual(copy["pos_y"], 6, "placed below, never on top of the original")

    def test_duplicate_across_dashboards_is_refused(self):
        with self.assertRaises(_ValidationError):
            self.studio.create_chart("D1", copy_from="other")
        self.assertEqual(len(self.store["DS Chart"]), 3, "nothing created")

    def test_duplicate_carries_only_the_four_filter_fields(self):
        self.store["DS Chart"]["c1"]["chart_filters"] = [
            {"fieldname": "x", "operator": "=", "value": "1", "filter_type": "Static",
             "parent": "c1", "doctype": "DS Chart Filter", "name": "row-1"}
        ]
        copy = self.studio.create_chart("D1", copy_from="c1")
        self.assertEqual(sorted(copy["chart_filters"][0]),
                         ["fieldname", "filter_type", "operator", "value"],
                         "parent/doctype/name from the source row are not carried over")

    # ---- delete ----
    def test_delete_removes_only_that_chart(self):
        result = self.studio.delete_chart("c1")
        self.assertEqual(result, {"deleted": "c1", "dashboard": "D1"})
        self.assertNotIn("c1", self.store["DS Chart"])
        self.assertIn("c2", self.store["DS Chart"], "sibling untouched")
        self.assertIn("other", self.store["DS Chart"])


    # ---- create from a migration-generated metric ----
    def test_create_links_the_metric_it_is_given(self):
        created = self.studio.create_chart("D1", "Bar Chart", metric="M-new")
        self.assertEqual(created["metric"], "M-new")
        self.assertEqual(created["chart_type"], "Bar Chart")
        self.assertEqual(created["dashboard"], "D1")

    def test_a_duplicate_still_takes_its_source_metric_not_the_argument(self):
        """copy_from means copy; the metric argument must not override it."""
        created = self.studio.create_chart("D1", copy_from="c1", metric="M-other")
        self.assertEqual(created["metric"], "M1", "the duplicate lost its source's metric")

    def test_no_metric_argument_still_creates_an_unlinked_chart(self):
        self.assertIsNone(self.studio.create_chart("D1", "Table")["metric"])

    def test_an_unapproved_metric_is_not_refused_here(self):
        """DS Chart.metric has no status constraint, and the engine already
        refuses to RUN an unapproved metric. A second check here would be a
        weaker copy of the gate that exists."""
        self.assertEqual(
            self.studio.create_chart("D1", "Bar Chart", metric="M-draft")["metric"], "M-draft")


if __name__ == "__main__":
    unittest.main()
