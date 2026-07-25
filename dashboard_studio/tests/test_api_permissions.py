"""Role-enforcement tests for the three DS-facing API endpoints.

Proves the two-level model actually gates the API layer (not just DocType
permissions): Viewer can read but not write, Editor can do both, a user with
neither role is rejected. System Manager retains access as superuser.

MOCK-BASED, no live Bench: a minimal fake ``frappe`` is injected into
sys.modules so the endpoint functions run their real ``frappe.only_for`` gate
against a settable current-user role set. This verifies the gating LOGIC, not a
live Frappe site.
"""

import sys
import types
import unittest


class _PermissionError(Exception):
    pass


class _FakeDoc(dict):
    def as_dict(self):
        return dict(self)

    def set(self, key, value):
        self[key] = value

    def save(self):
        self["_saved"] = True


def _make_fake_frappe():
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

    def get_doc(doctype, name):
        if doctype == "DS Metric":
            return _FakeDoc(
                metric_name=name, status="Approved", calculation_type="Count",
                source_doctype="Student Applicant", group_by_field="academic_year",
                value_field="name", allowed_fields="academic_year\nname", metric_filters=[],
            )
        return _FakeDoc(name=name, dashboard_title=name)

    def get_all(doctype, filters=None, **kwargs):
        if doctype in ("DS Chart", "DS Chart Filter"):
            return []
        if doctype == "DS Metric":
            rows = [
                {"name": "M1", "metric_name": "M1", "status": "Approved",
                 "calculation_type": "Count", "source_doctype": "Student Applicant"},
                {"name": "M2-draft", "metric_name": "M2-draft", "status": "Draft",
                 "calculation_type": "Count", "source_doctype": "Student Applicant"},
            ]
            # Honour filters, so endpoints that rely on them are actually tested.
            for key, value in (filters or {}).items():
                rows = [r for r in rows if r.get(key) == value]
            return rows
        # grouped-count fetch shape for the engine
        return [{"academic_year": "2023", "count": 3}]

    def throw(msg):
        raise Exception(msg)

    frappe.only_for = only_for
    frappe.whitelist = whitelist
    frappe.get_doc = get_doc
    frappe.get_all = get_all
    frappe.throw = throw
    return frappe


class TestApiRoleEnforcement(unittest.TestCase):
    def setUp(self):
        self._saved = {k: v for k, v in sys.modules.items() if k == "frappe" or k.startswith("dashboard_studio.api")}
        for k in list(sys.modules):
            if k == "frappe" or k.startswith("dashboard_studio.api"):
                sys.modules.pop(k, None)
        self.frappe = _make_fake_frappe()
        sys.modules["frappe"] = self.frappe
        import dashboard_studio.api.metrics as metrics
        import dashboard_studio.api.studio as studio
        self.metrics = metrics
        self.studio = studio

    def tearDown(self):
        for k in list(sys.modules):
            if k == "frappe" or k.startswith("dashboard_studio.api"):
                sys.modules.pop(k, None)
        sys.modules.update(self._saved)

    def _as(self, *roles):
        self.frappe._roles = set(roles)

    # ---- reads: get_studio_dashboard ----
    def test_viewer_can_read_dashboard(self):
        self._as("Dashboard Studio Viewer")
        self.assertIn("dashboard", self.studio.get_studio_dashboard("D1"))

    def test_editor_can_read_dashboard(self):
        self._as("Dashboard Studio Editor")
        self.assertIn("dashboard", self.studio.get_studio_dashboard("D1"))

    def test_no_role_cannot_read_dashboard(self):
        self._as("Some Other Role")
        with self.assertRaises(_PermissionError):
            self.studio.get_studio_dashboard("D1")

    # ---- writes: save_chart ----
    def test_editor_can_write_chart(self):
        self._as("Dashboard Studio Editor")
        out = self.studio.save_chart("C1", {"chart_title": "New"})
        self.assertTrue(out.get("_saved"))

    def test_viewer_cannot_write_chart(self):
        self._as("Dashboard Studio Viewer")
        with self.assertRaises(_PermissionError):
            self.studio.save_chart("C1", {"chart_title": "New"})

    def test_no_role_cannot_write_chart(self):
        self._as("Some Other Role")
        with self.assertRaises(_PermissionError):
            self.studio.save_chart("C1", {"chart_title": "New"})

    # ---- run_ds_metric (read action) ----
    def test_viewer_can_run_metric(self):
        self._as("Dashboard Studio Viewer")
        self.assertEqual(self.metrics.run_ds_metric("M1"), [{"academic_year": "2023", "count": 3}])

    def test_editor_can_run_metric(self):
        self._as("Dashboard Studio Editor")
        self.assertEqual(self.metrics.run_ds_metric("M1"), [{"academic_year": "2023", "count": 3}])

    def test_no_role_cannot_run_metric(self):
        self._as("Some Other Role")
        with self.assertRaises(_PermissionError):
            self.metrics.run_ds_metric("M1")

    # ---- list_ds_metrics (read) ----
    def test_viewer_can_list_metrics(self):
        self._as("Dashboard Studio Viewer")
        self.assertEqual(self.studio.list_ds_metrics()[0]["metric_name"], "M1")

    def test_list_metrics_excludes_unapproved(self):
        # The picker must only offer metrics the engine will actually run.
        self._as("Dashboard Studio Viewer")
        names = [m["metric_name"] for m in self.studio.list_ds_metrics()]
        self.assertEqual(names, ["M1"], "Draft metrics must not be listed")

    def test_no_role_cannot_list_metrics(self):
        self._as("Some Other Role")
        with self.assertRaises(_PermissionError):
            self.studio.list_ds_metrics()

    # ---- chart_filters sanitization on write ----
    def test_save_chart_sanitizes_filter_rows(self):
        self._as("Dashboard Studio Editor")
        out = self.studio.save_chart("C1", {
            "chart_filters": [
                {"fieldname": "academic_year", "operator": "=", "value": "2023",
                 "filter_type": "Static", "parent": "HACK", "doctype": "Evil", "owner": "x"},
                "not-a-dict-row",
            ],
        })
        self.assertEqual(out["chart_filters"], [
            {"fieldname": "academic_year", "operator": "=", "value": "2023", "filter_type": "Static"},
        ])

    def test_system_manager_superuser_read_and_write(self):
        self._as("System Manager")
        self.assertIn("dashboard", self.studio.get_studio_dashboard("D1"))
        self.assertTrue(self.studio.save_chart("C1", {"chart_title": "X"}).get("_saved"))


if __name__ == "__main__":
    unittest.main()
