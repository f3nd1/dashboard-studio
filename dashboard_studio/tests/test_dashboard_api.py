"""Tests for listing and creating DS Dashboards.

These two endpoints are what let the editor open on real records instead of
mock data, so the role gate on create matters: a Viewer must not be able to
make one. MOCK-BASED — endpoint logic only, no live Bench.

Reuses the fake Frappe from test_section_api rather than re-declaring it.
"""

import sys
import unittest

from dashboard_studio.tests.test_section_api import (
    _make_fake_frappe,
    _PermissionError,
    _ValidationError,
)


class TestDashboardApi(unittest.TestCase):
    def setUp(self):
        self._saved = {
            k: v for k, v in sys.modules.items()
            if k == "frappe" or k.startswith("dashboard_studio.api")
        }
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)

        # FIXTURE ONLY — invented dashboards.
        self.store = {
            "DS Dashboard": {
                "D1": {"name": "D1", "dashboard_title": "Admissions", "status": "Draft"},
                "D2": {"name": "D2", "dashboard_title": "Outcomes", "status": "Published"},
            }
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

    def test_list_returns_every_dashboard(self):
        names = {row["name"] for row in self.studio.list_dashboards()}
        self.assertEqual(names, {"D1", "D2"})

    def test_list_is_ordered_most_recently_modified_first(self):
        """The picker's "Recent" group is this ordering and nothing else.

        There is no separate recency field — it relies entirely on the endpoint
        asking for modified desc, so that request is worth pinning down.
        """
        seen = {}
        original = self.frappe.get_all

        def spy(doctype, **kwargs):
            seen.update(kwargs, doctype=doctype)
            return original(doctype, **kwargs)

        self.frappe.get_all = spy
        self.studio.list_dashboards()
        self.assertEqual(seen["doctype"], "DS Dashboard")
        self.assertEqual(seen["order_by"], "modified desc")
        # The picker renders a title and a status pill for every row.
        for field in ("name", "dashboard_title", "status"):
            self.assertIn(field, seen["fields"])

    def test_viewer_may_list_but_not_create(self):
        self.frappe._roles = {"Dashboard Studio Viewer"}
        self.assertEqual(len(self.studio.list_dashboards()), 2)
        with self.assertRaises(_PermissionError):
            self.studio.create_dashboard("Nope")

    def test_create_trims_and_starts_as_draft(self):
        created = self.studio.create_dashboard("  New Board  ")
        self.assertEqual(created["dashboard_title"], "New Board")
        self.assertEqual(created["status"], "Draft")
        stored = self.store["DS Dashboard"][created["name"]]
        self.assertEqual(stored["dashboard_title"], "New Board")
        self.assertEqual(stored["status"], "Draft")

    def test_blank_title_is_rejected(self):
        with self.assertRaises(_ValidationError):
            self.studio.create_dashboard("   ")
        self.assertEqual(len(self.store["DS Dashboard"]), 2, "nothing created")


if __name__ == "__main__":
    unittest.main()


class TestChartMetricStatusInPayload(unittest.TestCase):
    """The Builder renders a card by calling run_ds_metric, and the engine
    refuses a metric that is not Approved. The status has to travel with the
    chart so the card can say so WITHOUT making that call — a frontend catch
    cannot suppress Frappe's dialog, because Frappe raises it first."""

    def setUp(self):
        self._saved = {
            k: v for k, v in sys.modules.items()
            if k == "frappe" or k.startswith("dashboard_studio.")
        }
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        self.store = {
            "DS Dashboard": {
                "D1": {"name": "D1", "dashboard_title": "Admissions",
                       "status": "Draft", "subcriterion": "4.1.1"},
            },
            "DS Chart": {
                "c-ok": {"name": "c-ok", "dashboard": "D1", "chart_title": "Approved",
                         "metric": "M-approved", "modified": "2026-07-26 09:00:00"},
                "c-draft": {"name": "c-draft", "dashboard": "D1", "chart_title": "Draft",
                            "metric": "M-draft", "modified": "2026-07-26 09:00:00"},
                "c-gone": {"name": "c-gone", "dashboard": "D1", "chart_title": "Dangling",
                           "metric": "M-deleted", "modified": "2026-07-26 09:00:00"},
                "c-none": {"name": "c-none", "dashboard": "D1", "chart_title": "Unlinked",
                           "metric": "", "modified": "2026-07-26 09:00:00"},
            },
            "DS Metric": {
                "M-approved": {"name": "M-approved", "status": "Approved",
                               "calculation_type": "Count"},
                "M-draft": {"name": "M-draft", "status": "Draft", "calculation_type": "Count"},
            },
        }
        self.frappe = _make_fake_frappe(self.store)
        sys.modules["frappe"] = self.frappe
        self.frappe._roles = {"Dashboard Studio Editor"}
        import dashboard_studio.api.studio as studio

        self.studio = studio

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    def _charts(self):
        return {c["name"]: c for c in self.studio.get_studio_dashboard("D1")["charts"]}

    def test_status_travels_with_each_chart(self):
        charts = self._charts()
        self.assertEqual(charts["c-ok"]["metric_status"], "Approved")
        self.assertEqual(charts["c-draft"]["metric_status"], "Draft")
        self.assertEqual(charts["c-ok"]["metric_calculation"], "Count")

    def test_a_chart_pointing_at_a_deleted_metric_is_marked(self):
        charts = self._charts()
        self.assertTrue(charts["c-gone"]["metric_missing"])
        self.assertIsNone(charts["c-gone"]["metric_status"])
        self.assertFalse(charts["c-ok"]["metric_missing"])

    def test_a_chart_with_no_metric_is_not_marked_missing(self):
        """Unlinked and dangling are different problems with different remedies."""
        self.assertFalse(self._charts()["c-none"]["metric_missing"])
        self.assertIsNone(self._charts()["c-none"]["metric_status"])

    def test_one_metric_read_regardless_of_chart_count(self):
        self.frappe._metric_reads = 0
        self.studio.get_studio_dashboard("D1")
        self.assertEqual(self.frappe._metric_reads, 1)
