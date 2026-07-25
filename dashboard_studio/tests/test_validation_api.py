"""Tests for the Validation Centre endpoints.

The load-bearing ones guard comparison.py's safety rules end to end: Accepted is
never computed, only chosen by a human with a reason; Flagged stays distinct
from Discrepancy; and groups missing from either side are surfaced.

MOCK-BASED for Frappe — endpoint logic only, no live Bench.
"""

import sys
import types
import unittest


class _PermissionError(Exception):
    pass


class _ValidationError(Exception):
    pass


class _FakeDoc:
    def __init__(self, data, store=None, doctype=None):
        object.__setattr__(self, "_data", dict(data))
        object.__setattr__(self, "_store", store)
        object.__setattr__(self, "_doctype", doctype or data.get("doctype"))

    def __getattr__(self, key):
        try:
            return self._data[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self._data[key] = value

    def get(self, key, default=None):
        return self._data.get(key, default)

    def as_dict(self):
        return dict(self._data)

    def _persist(self):
        table = self._store.setdefault(self._doctype, {})
        name = self._data.get("name")
        if not name:
            name = f"{self._doctype}-{len(table) + 1}"
            self._data["name"] = name
        table[name] = dict(self._data)
        return self

    save = _persist
    insert = _persist


def _make_fake_frappe(store):
    frappe = types.ModuleType("frappe")
    frappe.PermissionError = _PermissionError
    frappe._roles = set()
    frappe.session = types.SimpleNamespace(user="reviewer@example.invalid")

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
            return _FakeDoc(doctype, store, doctype.get("doctype"))
        data = store.get(doctype, {}).get(name)
        if data is None:
            raise KeyError(f"{doctype} {name} not found")
        return _FakeDoc(data, store, doctype)

    def get_all(doctype, filters=None, fields=None, order_by=None, limit=None, **kwargs):
        rows = list(store.get(doctype, {}).values())
        for key, value in (filters or {}).items():
            rows = [r for r in rows if r.get(key) == value]
        return [dict(r) for r in rows]

    frappe.only_for = only_for
    frappe.whitelist = whitelist
    frappe.get_doc = get_doc
    frappe.get_all = get_all
    frappe.throw = lambda msg: (_ for _ in ()).throw(_ValidationError(msg))
    frappe.utils = types.SimpleNamespace(today=lambda: "2026-07-25")
    return frappe


class TestValidationApi(unittest.TestCase):
    def setUp(self):
        self._saved = {
            k: v for k, v in sys.modules.items()
            if k == "frappe" or k.startswith("dashboard_studio.api")
        }
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)

        # FIXTURE ONLY — invented chart and counts.
        self.store = {
            "DS Chart": {
                "C1": {"name": "C1", "chart_title": "Applicants by Year", "metric": "M1"},
                "C-nometric": {"name": "C-nometric", "chart_title": "Unlinked", "metric": ""},
            },
            "DS Validation Comparison": {},
        }
        self.frappe = _make_fake_frappe(self.store)
        sys.modules["frappe"] = self.frappe
        import dashboard_studio.api.validation as validation

        self.validation = validation
        self.frappe._roles = {"Dashboard Studio Editor"}

        self.source = [
            {"academic_year": "2022", "count": 2},
            {"academic_year": "2023", "count": 3},
        ]

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    def _comparisons(self):
        return list(self.store["DS Validation Comparison"].values())

    # ---- role gating ----
    def test_viewer_can_read_but_not_run_or_accept(self):
        self.frappe._roles = {"Dashboard Studio Viewer"}
        self.assertEqual(self.validation.list_comparisons(), [])
        with self.assertRaises(_PermissionError):
            self.validation.run_validation("C1", self.source, self.source)
        with self.assertRaises(_PermissionError):
            self.validation.accept_comparison("X", "because")

    # ---- running a comparison ----
    def test_matching_results_record_a_match(self):
        result = self.validation.run_validation("C1", self.source, list(self.source))
        self.assertEqual(result["status"], "Match")
        self.assertEqual(result["summary"], {"matched": 2, "discrepancies": 0, "flagged": 0})
        stored = self._comparisons()[0]
        self.assertEqual(stored["chart"], "C1")
        self.assertEqual(stored["status"], "Match")
        self.assertEqual(stored["original_value"], "5")  # totals, stored as Data
        self.assertEqual(stored["new_value"], "5")

    def test_differing_results_record_a_discrepancy(self):
        target = [{"academic_year": "2022", "count": 2}, {"academic_year": "2023", "count": 9}]
        result = self.validation.run_validation("C1", self.source, target)
        self.assertEqual(result["status"], "Discrepancy")
        self.assertEqual(self._comparisons()[0]["status"], "Discrepancy")

    def test_missing_group_is_flagged_and_surfaced_not_hidden(self):
        target = [{"academic_year": "2022", "count": 2}]  # 2023 missing
        result = self.validation.run_validation("C1", self.source, target)
        self.assertEqual(result["status"], "Flagged", "unknown outranks unequal")
        labels = [row["label"] for row in result["rows"]]
        self.assertIn("2023", labels, "the missing group must still be reported")

    def test_per_group_rows_are_returned_but_not_persisted(self):
        # Documented schema gap: DS Validation Comparison has no group-label field.
        result = self.validation.run_validation("C1", self.source, list(self.source))
        self.assertEqual(len(result["rows"]), 2)
        self.assertFalse(result["persisted_rows"])
        self.assertEqual(len(self._comparisons()), 1, "one record per run, holding totals")

    def test_chart_without_a_metric_is_rejected(self):
        with self.assertRaises(_ValidationError):
            self.validation.run_validation("C-nometric", self.source)

    def test_tolerance_absorbs_small_differences(self):
        target = [{"academic_year": "2022", "count": 2}, {"academic_year": "2023", "count": 3.05}]
        self.assertEqual(
            self.validation.run_validation("C1", self.source, target, tolerance_pct=5)["status"],
            "Match",
        )

    # ---- accepting a difference: the human-only path ----
    def test_accept_requires_a_reason(self):
        run = self.validation.run_validation(
            "C1", self.source, [{"academic_year": "2022", "count": 9}]
        )
        for blank in ("", "   ", None):
            with self.assertRaises(_ValidationError):
                self.validation.accept_comparison(run["comparison"], blank)
        self.assertNotEqual(self._comparisons()[0]["status"], "Accepted")

    def test_accept_records_reason_and_reviewer(self):
        run = self.validation.run_validation(
            "C1", self.source, [{"academic_year": "2022", "count": 9}]
        )
        out = self.validation.accept_comparison(run["comparison"], "  Known legacy rounding  ")
        self.assertEqual(out["status"], "Accepted")
        self.assertEqual(out["accepted_reason"], "Known legacy rounding")
        self.assertEqual(out["reviewed_by"], "reviewer@example.invalid")

    def test_accepted_is_never_produced_by_running_a_comparison(self):
        # The arithmetic must never reach Accepted on its own, whatever the data.
        for target in ([], list(self.source), [{"academic_year": "2022", "count": 99}]):
            self.store["DS Validation Comparison"].clear()
            status = self.validation.run_validation("C1", self.source, target)["status"]
            self.assertIn(status, ("Match", "Discrepancy", "Flagged"))

    def test_matching_comparison_cannot_be_accepted(self):
        run = self.validation.run_validation("C1", self.source, list(self.source))
        with self.assertRaises(_ValidationError):
            self.validation.accept_comparison(run["comparison"], "nothing to accept")


if __name__ == "__main__":
    unittest.main()
