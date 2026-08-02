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
        if doctype == "DS Chart":
            frappe._chart_reads = getattr(frappe, "_chart_reads", 0) + 1
        rows = list(store.get(doctype, {}).values())
        for key, value in (filters or {}).items():
            # TEST-FAKE GAP, fixed: this only understood equality, so a batched
            # ["in", [...]] read matched NOTHING and the caller silently saw an
            # empty result. Same gap that hid the readiness batch read.
            if isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == "in":
                rows = [r for r in rows if r.get(key) in value[1]]
            else:
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

    # ---- the chart column ----
    def test_list_comparisons_carries_the_chart_title(self):
        """DS Chart has no autoname, so `chart` is a hash — unreadable on its own."""
        self.validation.run_validation("C1", self.source, self.source)
        row = self.validation.list_comparisons()[0]
        self.assertEqual(row["chart_title"], "Applicants by Year")
        # The raw link is still carried: it is what accept_comparison and the
        # readiness gate key on.
        self.assertEqual(row["chart"], "C1")

    def test_a_deleted_chart_still_identifies_its_comparison(self):
        self.validation.run_validation("C1", self.source, self.source)
        del self.store["DS Chart"]["C1"]
        row = self.validation.list_comparisons()[0]
        self.assertEqual(row["chart_title"], "C1", "a blank cell would identify nothing")

    def test_one_read_regardless_of_row_count(self):
        """Per-row title lookups would be N+1 on a page that loads on every visit."""
        self.validation.run_validation("C1", self.source, self.source)
        self.validation.run_validation("C1", self.source, self.source)
        self.validation.run_validation("C-nometric", self.source, self.source)
        self.frappe._chart_reads = 0
        rows = self.validation.list_comparisons()
        self.assertEqual(len(rows), 3)
        self.assertEqual(self.frappe._chart_reads, 1)

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

    def test_per_group_rows_are_persisted_as_child_rows(self):
        result = self.validation.run_validation("C1", self.source, list(self.source))
        self.assertTrue(result["persisted_rows"])
        self.assertEqual(len(self._comparisons()), 1, "one record per RUN")
        rows = self._comparisons()[0]["comparison_rows"]
        self.assertEqual([r["group_label"] for r in rows], ["2022", "2023"])
        self.assertEqual(rows[0]["original_value"], "2")
        self.assertEqual(rows[0]["status"], "Match")

    def test_incomparable_group_stores_blank_difference_not_zero(self):
        # The whole point of comparison.py: unknown must never become 0.
        target = [{"academic_year": "2022", "count": 2}]  # 2023 missing
        self.validation.run_validation("C1", self.source, target)
        rows = {r["group_label"]: r for r in self._comparisons()[0]["comparison_rows"]}
        self.assertEqual(rows["2023"]["status"], "Flagged")
        self.assertEqual(rows["2023"]["difference"], "", "blank, not 0")
        self.assertEqual(rows["2023"]["difference_pct"], "", "blank, not 0")
        self.assertEqual(rows["2023"]["new_value"], "", "missing value stays missing")
        self.assertTrue(rows["2023"]["reason"], "a reason is recorded")

    def test_child_rows_never_carry_an_accepted_status(self):
        # Acceptance is a decision about the RUN, recorded on the parent.
        self.validation.run_validation(
            "C1", self.source, [{"academic_year": "2022", "count": 9}]
        )
        for row in self._comparisons()[0]["comparison_rows"]:
            self.assertIn(row["status"], ("Match", "Discrepancy", "Flagged"))

    def test_get_comparison_returns_the_breakdown(self):
        run = self.validation.run_validation("C1", self.source, list(self.source))
        detail = self.validation.get_comparison(run["comparison"])
        self.assertEqual(len(detail["comparison_rows"]), 2)
        self.assertEqual(detail["comparison_rows"][1]["group_label"], "2023")

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
