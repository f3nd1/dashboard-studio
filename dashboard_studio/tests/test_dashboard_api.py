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
