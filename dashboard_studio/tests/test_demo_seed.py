"""Tests for the demo/seed data script.

The four safety properties are the point, so each is asserted directly:
only DS DocTypes written, everything demo-marked, idempotent, and a removal that
will not touch an unmarked record. Path A reaching Published is checked through
the real ``advance_status`` gate, not by reading the field back.

MOCK-BASED for Frappe — no live Bench.
"""

import datetime
import sys
import types
import unittest

# One fixed clock. The publish gate compares comparison_date >= chart.modified,
# so a fake whose saves left `modified` unset would pass for the wrong reason.
NOW = "2026-07-26 09:00:00"
TODAY = "2026-07-26"


class _PermissionError(Exception):
    pass


class _ValidationError(Exception):
    pass


class _FakeDoc:
    def __init__(self, data, store, doctype):
        object.__setattr__(self, "_data", dict(data))
        object.__setattr__(self, "_store", store)
        object.__setattr__(self, "_doctype", doctype)

    def __getattr__(self, key):
        try:
            return self._data[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self._data[key] = value

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def append(self, key, value):
        self._data.setdefault(key, []).append(dict(value))

    def as_dict(self):
        return dict(self._data)

    def _persist(self):
        table = self._store.setdefault(self._doctype, {})
        name = self._data.get("name")
        if not name:
            keyed = _AUTONAME.get(self._doctype)
            name = self._data.get(keyed) if keyed else None
        if not name:
            name = f"{self._doctype}-{len(table) + 1}"
        self._data["name"] = name
        # Real Frappe stamps this on every write. Without it the gate's
        # "validated since the last edit" rule has nothing to compare against.
        self._data["modified"] = NOW
        table[name] = dict(self._data)
        return self

    save = _persist
    insert = _persist


# autoname: field:x — the record's primary key IS that field.
_AUTONAME = {
    "DS Dashboard": "dashboard_title",
    "DS Metric": "metric_name",
    "DS Migration Project": "project_name",
    "DS Data Source": "source_name",
}


def _make_fake_frappe(store):
    frappe = types.ModuleType("frappe")
    frappe.PermissionError = _PermissionError
    frappe._roles = {"System Manager"}

    def only_for(roles, message=None):
        if isinstance(roles, str):
            roles = (roles,)
        if not (set(roles) & frappe._roles):
            raise _PermissionError(f"need one of {roles}")

    def whitelist(*a, **k):
        def deco(fn):
            return fn

        return deco

    def get_doc(doctype, name=None):
        if isinstance(doctype, dict):
            payload = dict(doctype)
            return _FakeDoc(payload, store, payload.pop("doctype"))
        data = store.get(doctype, {}).get(name)
        if data is None:
            raise KeyError(f"{doctype} {name} not found")
        return _FakeDoc(data, store, doctype)

    def get_all(doctype, filters=None, fields=None, order_by=None, limit=None, **kwargs):
        rows = list(store.get(doctype, {}).values())
        for key, value in (filters or {}).items():
            if isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == "in":
                rows = [r for r in rows if r.get(key) in value[1]]
            else:
                rows = [r for r in rows if r.get(key) == value]
        return [dict(r) for r in rows][: limit or None]

    def exists(doctype, name):
        if doctype == "DocType":
            return name in _DOCTYPES_PRESENT
        return name in store.get(doctype, {})

    def delete_doc(doctype, name):
        store.get(doctype, {}).pop(name, None)

    def getdate(value):
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        return datetime.date.fromisoformat(str(value).split(" ")[0])

    frappe.only_for = only_for
    frappe.whitelist = whitelist
    frappe.get_doc = get_doc
    frappe.get_all = get_all
    frappe.delete_doc = delete_doc
    frappe.get_roles = lambda: list(frappe._roles)
    frappe.throw = lambda msg: (_ for _ in ()).throw(_ValidationError(msg))
    frappe.db = types.SimpleNamespace(
        exists=exists, count=lambda dt, f=None: len(get_all(dt, f)), commit=lambda: None
    )
    frappe.utils = types.SimpleNamespace(now=lambda: NOW, getdate=getdate, today=lambda: TODAY)
    return frappe


_DOCTYPES_PRESENT = {"User", "ToDo"}   # deliberately NOT Student Applicant


class TestDemoSeed(unittest.TestCase):
    def setUp(self):
        self._saved = {
            k: v for k, v in sys.modules.items()
            if k == "frappe" or k.startswith("dashboard_studio.")
        }
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        self.store = {}
        self.frappe = _make_fake_frappe(self.store)
        sys.modules["frappe"] = self.frappe
        import dashboard_studio.demo as demo

        self.demo = demo

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    def _names(self):
        return {dt: sorted(rows) for dt, rows in self.store.items() if rows}

    # ---------------------------------------------------------------- seeding
    def test_seeds_only_ds_doctypes(self):
        self.demo.seed_demo_data()
        stray = [dt for dt in self.store if not dt.startswith("DS ")]
        self.assertEqual(stray, [], f"seed wrote outside the app's own DocTypes: {stray}")

    def test_every_seeded_record_is_demo_marked(self):
        self.demo.seed_demo_data()
        for doctype, field in self.demo._DEMO_MARK.items():
            for name, row in self.store.get(doctype, {}).items():
                self.assertTrue(
                    str(row.get(field) or "").startswith(self.demo.DEMO_PREFIX),
                    f"{doctype} {name} is not demo-marked on {field}",
                )

    def test_seeding_twice_does_not_duplicate(self):
        self.demo.seed_demo_data()
        first = self._names()
        self.demo.seed_demo_data()
        self.assertEqual(self._names(), first)

    def test_comparison_rows_are_replaced_not_appended(self):
        self.demo.seed_demo_data()
        self.demo.seed_demo_data()
        rows = [r for r in self.store["DS Validation Comparison"].values()][0]["comparison_rows"]
        self.assertEqual(len(rows), 3)

    def test_falls_back_to_a_doctype_that_exists(self):
        # Student Applicant is absent from this site, so the seed must not link to it.
        result = self.demo.seed_demo_data()
        self.assertEqual(result["source_doctype"], "User")

    # ------------------------------------------------------------- path A / B
    def test_path_a_reaches_published_through_the_gate(self):
        result = self.demo.seed_demo_data()
        self.assertEqual(result["path_a_status"], "Published")
        import dashboard_studio.api.governance as governance

        readiness = governance.publish_readiness(result["path_a_dashboard"])
        self.assertTrue(readiness["publishable"], readiness["blockers"])

    def test_path_a_would_not_publish_without_its_validation(self):
        """The gate is real: remove the Match comparison and publishing refuses."""
        result = self.demo.seed_demo_data()
        self.store["DS Validation Comparison"].clear()
        import dashboard_studio.api.governance as governance

        readiness = governance.publish_readiness(result["path_a_dashboard"])
        self.assertFalse(readiness["publishable"])
        self.assertEqual([b["rule"] for b in readiness["blockers"]], ["chart_not_validated"])

    def test_path_b_reports_two_real_blockers(self):
        result = self.demo.seed_demo_data()
        self.assertEqual(
            sorted(result["path_b_blockers"]),
            sorted(["1 chart with no metric", "1 chart not validated since the last edit"]),
        )

    def test_path_b_metric_is_still_draft(self):
        self.demo.seed_demo_data()
        metric = self.store["DS Metric"][self.demo.DEMO_PREFIX + "Survey responses"]
        self.assertEqual(metric["status"], "Draft")

    # --------------------------------------------------------------- removal
    def test_removal_deletes_every_demo_record(self):
        self.demo.seed_demo_data()
        self.demo.remove_demo_data()
        left = {dt: list(rows) for dt, rows in self.store.items() if rows}
        self.assertEqual(left, {})

    def test_removal_refuses_records_that_are_not_demo_marked(self):
        self.demo.seed_demo_data()
        # A real dashboard, and a real chart on it, sitting alongside the demo data.
        self.store["DS Dashboard"]["Real Intake"] = {
            "name": "Real Intake", "dashboard_title": "Real Intake", "status": "Published",
        }
        self.store["DS Chart"]["real-1"] = {
            "name": "real-1", "chart_title": "Real chart", "dashboard": "Real Intake",
        }
        report = self.demo.remove_demo_data()
        self.assertIn("Real Intake", self.store["DS Dashboard"])
        self.assertIn("real-1", self.store["DS Chart"])
        self.assertNotIn(
            "Real Intake", [d["name"] for d in report["deleted"]],
        )

    def test_dry_run_deletes_nothing(self):
        self.demo.seed_demo_data()
        before = self._names()
        report = self.demo.remove_demo_data(dry_run=True)
        self.assertEqual(self._names(), before)
        self.assertTrue(report["dry_run"])
        self.assertTrue(report["deleted"], "dry run must still report what it would delete")


if __name__ == "__main__":
    unittest.main()
