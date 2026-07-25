"""Tests for the deploy check.

The point of this endpoint is catching a site whose database is behind the code,
so the fake here models the SITE separately from the shipped JSON — unlike the
other fakes, whose get_meta deliberately mirrors the shipped schema. Starting
from an in-sync site and removing pieces is what makes the drift cases real.

MOCK-BASED — no live Bench.
"""

import json
import os
import sys
import types
import unittest

_DOCTYPE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard_studio", "doctype"
)


def _site_matching_shipped():
    """A simulated site whose schema exactly matches what the app ships."""
    site = {}
    for folder in sorted(os.listdir(_DOCTYPE_DIR)):
        path = os.path.join(_DOCTYPE_DIR, folder, folder + ".json")
        if not os.path.exists(path):
            continue
        with open(path) as handle:
            shipped = json.load(handle)
        site[shipped["name"]] = {
            f["fieldname"]: dict(f) for f in shipped.get("fields", []) if f.get("fieldname")
        }
    return site


def _fake_frappe(site):
    frappe = types.ModuleType("frappe")
    frappe._roles = {"Dashboard Studio Viewer"}

    def only_for(roles, message=None):
        if not (set(roles) & frappe._roles):
            raise PermissionError(f"need one of {roles}")

    def get_meta(doctype):
        fields = site.get(doctype, {})

        class _Meta:
            def get_field(self, fieldname):
                raw = fields.get(fieldname)
                return types.SimpleNamespace(**raw) if raw else None

        return _Meta()

    frappe.only_for = only_for
    frappe.whitelist = lambda *a, **k: (lambda fn: fn)
    frappe.get_meta = get_meta
    frappe.db = types.SimpleNamespace(exists=lambda dt, name: name in site)
    return frappe


class TestDeployCheck(unittest.TestCase):
    def setUp(self):
        self._saved = {
            k: v for k, v in sys.modules.items()
            if k == "frappe" or k.startswith("dashboard_studio.api")
        }
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)
        self.site = _site_matching_shipped()
        sys.modules["frappe"] = _fake_frappe(self.site)
        import dashboard_studio.api.deploy as deploy

        self.deploy = deploy

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    def test_a_current_site_reports_no_issues(self):
        result = self.deploy.deploy_check()
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(result["issues"], [])
        self.assertNotIn("bench migrate", result["summary"])
        self.assertIn("19 of 19 DocTypes installed", result["summary"])

    def test_the_real_incident_is_caught(self):
        """The exact gap that caused the live round trip: two DocTypes never
        migrated, and a field added after the last migrate."""
        del self.site["DS Migration Source Query"]
        del self.site["DS Validation Row"]
        del self.site["DS Dashboard"]["subcriterion"]

        result = self.deploy.deploy_check()
        self.assertFalse(result["ok"])
        self.assertIn("DocType not installed: DS Migration Source Query", result["issues"])
        self.assertIn("DocType not installed: DS Validation Row", result["issues"])
        self.assertIn("Field missing: DS Dashboard.subcriterion", result["issues"])
        self.assertIn("17 of 19 DocTypes installed", result["summary"])
        self.assertIn("run bench migrate", result["summary"])

    def test_absent_doctypes_are_reported_before_field_problems(self):
        del self.site["DS Validation Row"]
        del self.site["DS Dashboard"]["subcriterion"]
        issues = self.deploy.deploy_check()["issues"]
        self.assertTrue(issues[0].startswith("DocType not installed"), issues)

    def test_a_changed_fieldtype_is_reported_with_both_values(self):
        self.site["DS Chart"]["pos_x"]["fieldtype"] = "Data"
        issues = self.deploy.deploy_check()["issues"]
        self.assertEqual(len(issues), 1)
        self.assertIn("DS Chart.pos_x.fieldtype", issues[0])
        self.assertIn("ships 'Int'", issues[0])
        self.assertIn("site has 'Data'", issues[0])

    def test_stale_select_options_are_reported(self):
        """The case that silently breaks a write: the site's Select predates a
        new option, so saving the new value fails validation."""
        self.site["DS Chart"]["sort_order"]["options"] = "Ascending\nDescending"
        issues = self.deploy.deploy_check()["issues"]
        self.assertTrue(any("DS Chart.sort_order.options" in i for i in issues), issues)

    def test_a_dropped_reqd_is_reported(self):
        self.site["DS Chart"]["metric"]["reqd"] = 1   # site still has the old constraint
        issues = self.deploy.deploy_check()["issues"]
        self.assertTrue(any("DS Chart.metric.reqd" in i for i in issues), issues)

    def test_fields_absent_from_a_missing_doctype_are_not_double_reported(self):
        del self.site["DS Chart"]
        issues = self.deploy.deploy_check()["issues"]
        self.assertEqual(issues, ["DocType not installed: DS Chart"])

    def test_it_is_read_gated(self):
        sys.modules["frappe"]._roles = set()
        with self.assertRaises(PermissionError):
            self.deploy.deploy_check()


if __name__ == "__main__":
    unittest.main()
