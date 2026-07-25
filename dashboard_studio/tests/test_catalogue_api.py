"""Tests for the Data & DocTypes workspace endpoints.

The relationship graph is read from the REAL committed schema files, so these
also act as a guard that the DS DocTypes stay wired together as documented.
MOCK-BASED for Frappe itself — no live Bench.
"""

import os
import sys
import types
import unittest

DOCTYPE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard_studio", "doctype"
)


class _PermissionError(Exception):
    pass


def _make_fake_frappe(store):
    frappe = types.ModuleType("frappe")
    frappe.PermissionError = _PermissionError
    frappe._roles = set()

    def only_for(roles, message=None):
        if isinstance(roles, str):
            roles = (roles,)
        if not (set(roles) & frappe._roles):
            raise _PermissionError(f"need one of {roles}")

    def whitelist(*a, **k):
        def deco(fn):
            return fn

        return deco

    def get_all(doctype, filters=None, fields=None, order_by=None, limit=None, **kwargs):
        rows = [dict(r) for r in store.get(doctype, [])]
        return rows[:limit] if limit else rows

    frappe.only_for = only_for
    frappe.whitelist = whitelist
    frappe.get_all = get_all
    frappe.throw = lambda msg: (_ for _ in ()).throw(Exception(msg))
    frappe.db = types.SimpleNamespace(count=lambda dt: len(store.get(dt, [])))
    return frappe


class TestCatalogueApi(unittest.TestCase):
    def setUp(self):
        self._saved = {
            k: v for k, v in sys.modules.items()
            if k == "frappe" or k.startswith("dashboard_studio.api")
        }
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)

        # FIXTURE ONLY — invented records.
        self.store = {
            "DS Dashboard": [
                {"name": "D1", "dashboard_title": "Admission (MOCK)", "status": "Published"},
                {"name": "D2", "dashboard_title": "Outcomes (MOCK)", "status": "Draft"},
            ],
            "DS Metric": [
                {"name": "M1", "metric_name": "By Year", "status": "Approved",
                 "source_doctype": "Student Applicant", "allowed_fields": "academic_year\nname"},
                {"name": "M2", "metric_name": "No allowlist", "status": "Draft",
                 "source_doctype": "Student Applicant", "allowed_fields": ""},
            ],
            "DS Chart": [{"name": "C1", "chart_title": "Chart (MOCK)"}],
        }
        self.frappe = _make_fake_frappe(self.store)
        sys.modules["frappe"] = self.frappe
        import dashboard_studio.api.catalogue as catalogue

        self.catalogue = catalogue
        self.frappe._roles = {"Dashboard Studio Viewer"}

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    def test_read_role_is_required(self):
        self.frappe._roles = {"Some Other Role"}
        for call in (self.catalogue.get_catalogue, self.catalogue.get_field_catalogue):
            with self.assertRaises(_PermissionError):
                call()

    def test_counts_and_status_breakdown(self):
        entries = {e["doctype"]: e for e in self.catalogue.get_catalogue()["doctypes"]}
        self.assertEqual(entries["DS Dashboard"]["count"], 2)
        self.assertEqual(entries["DS Dashboard"]["statuses"], {"Published": 1, "Draft": 1})
        self.assertIn("Admission (MOCK)", entries["DS Dashboard"]["recent"])
        # A DocType with no records still reports, at zero.
        self.assertEqual(entries["DS Data Source"]["count"], 0)

    # ---- relationship graph, read from the real committed schema ----
    def test_real_schema_edges_are_discovered(self):
        edges = self.catalogue.relationships_from_schema_dir(DOCTYPE_DIR)
        pairs = {(e["source"], e["fieldname"], e["target"], e["kind"]) for e in edges}
        self.assertIn(("DS Chart", "dashboard", "DS Dashboard", "link"), pairs)
        self.assertIn(("DS Chart", "metric", "DS Metric", "link"), pairs)
        self.assertIn(("DS Chart", "chart_filters", "DS Chart Filter", "child"), pairs)
        self.assertIn(("DS Migration Project", "canvas_nodes", "DS Canvas Node", "child"), pairs)
        self.assertIn(("DS Validation Comparison", "chart", "DS Chart", "link"), pairs)

    def test_self_reference_is_marked(self):
        edges = self.catalogue.relationships_from_schema_dir(DOCTYPE_DIR)
        selfies = [e for e in edges if e["self_reference"]]
        self.assertTrue(selfies, "DS Metric numerator/denominator are self-references")
        self.assertTrue(all(e["source"] == e["target"] for e in selfies))

    def test_only_ds_targets_are_included(self):
        edges = self.catalogue.relationships_from_schema_dir(DOCTYPE_DIR)
        # source_doctype links to core DocType, reviewer to User — not schema edges.
        self.assertTrue(all(e["target"].startswith("DS ") for e in edges))

    # ---- safe field catalogue ----
    def test_field_catalogue_reports_allowlists_and_executability(self):
        rows = {r["metric"]: r for r in self.catalogue.get_field_catalogue()}
        self.assertEqual(rows["M1"]["fields"], ["academic_year", "name"])
        self.assertTrue(rows["M1"]["executable"])
        # Block-by-default: no allowlist means the engine will refuse to run it.
        self.assertEqual(rows["M2"]["fields"], [])
        self.assertFalse(rows["M2"]["executable"])

    def test_field_catalogue_reports_no_restricted_concept(self):
        # Guard against a future "restricted" column being invented: DS Metric
        # has an allowlist only, and this endpoint must not imply otherwise.
        for row in self.catalogue.get_field_catalogue():
            self.assertNotIn("restricted", row)
            self.assertNotIn("field_types", row)


if __name__ == "__main__":
    unittest.main()
