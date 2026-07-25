"""Tests for the four-stage governance workflow.

The load-bearing property is separation of duties: an Editor can move work up to
QA Approval but cannot publish it. That is the whole reason the QA Approver role
was added, so it is tested from both directions.

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

    def save(self):
        self._store.setdefault(self._doctype, {})[self._data["name"]] = dict(self._data)
        return self


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

    def get_doc(doctype, name=None):
        data = store.get(doctype, {}).get(name)
        if data is None:
            raise KeyError(f"{doctype} {name} not found")
        return _FakeDoc(data, store, doctype)

    def get_all(doctype, filters=None, fields=None, order_by=None, limit=None, **kwargs):
        rows = list(store.get(doctype, {}).values())
        for key, value in (filters or {}).items():
            rows = [r for r in rows if r.get(key) == value]
        return [dict(r) for r in rows][: limit or None]

    def count(doctype, filters=None):
        return len(get_all(doctype, filters))

    frappe.only_for = only_for
    frappe.whitelist = whitelist
    frappe.get_doc = get_doc
    frappe.get_all = get_all
    frappe.get_roles = lambda: list(frappe._roles)
    frappe.throw = lambda msg: (_ for _ in ()).throw(_ValidationError(msg))
    frappe.db = types.SimpleNamespace(count=count)
    frappe.utils = types.SimpleNamespace(now=lambda: "2026-07-25 10:00:00")
    return frappe


class TestGovernanceApi(unittest.TestCase):
    def setUp(self):
        self._saved = {
            k: v for k, v in sys.modules.items()
            if k == "frappe" or k.startswith("dashboard_studio.api")
        }
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)

        # FIXTURE ONLY — invented dashboard and charts.
        self.store = {
            "DS Dashboard": {
                # Scoped, so the publish path can be tested; the unscoped refusal has
                # its own tests below.
                "D1": {"name": "D1", "dashboard_title": "Admission (MOCK)",
                       "status": "Draft", "subcriterion": "4.1.1"},
            },
            "DS Chart": {
                "C1": {"name": "C1", "dashboard": "D1", "chart_title": "A", "metric": "M-shared"},
                "C2": {"name": "C2", "dashboard": "D1", "chart_title": "B", "metric": "M-solo"},
                # A chart on ANOTHER dashboard using the same metric — that is
                # what makes M-shared shared.
                "C3": {"name": "C3", "dashboard": "D2", "chart_title": "C", "metric": "M-shared"},
            },
            "DS Dashboard Section": {
                "S1": {"name": "S1", "dashboard": "D1", "section_title": "Intake"},
            },
            "Version": {
                "V1": {"name": "V1", "ref_doctype": "DS Dashboard", "docname": "D1",
                       "owner": "editor@example.invalid", "creation": "2026-07-25 09:00:00"},
            },
        }
        self.frappe = _make_fake_frappe(self.store)
        sys.modules["frappe"] = self.frappe
        import dashboard_studio.api.governance as governance

        self.gov = governance

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    def _as(self, *roles):
        self.frappe._roles = set(roles)

    def _status(self):
        return self.store["DS Dashboard"]["D1"]["status"]

    # ---- the four stages ----
    def test_stages_are_the_four_stage_workflow(self):
        self._as("Dashboard Studio Viewer")
        self.assertEqual(
            self.gov.get_governance("D1")["stages"],
            ["Draft", "Technical Review", "QA Approval", "Published"],
        )

    def test_editor_moves_draft_up_to_qa_approval(self):
        self._as("Dashboard Studio Editor")
        self.gov.advance_status("D1", "Technical Review")
        self.assertEqual(self._status(), "Technical Review")
        self.gov.advance_status("D1", "QA Approval")
        self.assertEqual(self._status(), "QA Approval")

    # ---- separation of duties: the reason the QA role exists ----
    def test_editor_cannot_publish(self):
        self.store["DS Dashboard"]["D1"]["status"] = "QA Approval"
        self._as("Dashboard Studio Editor")
        with self.assertRaises(_ValidationError):
            self.gov.advance_status("D1", "Published")
        self.assertEqual(self._status(), "QA Approval", "status unchanged after refusal")

    def test_qa_approver_can_publish(self):
        self.store["DS Dashboard"]["D1"]["status"] = "QA Approval"
        self._as("Dashboard Studio QA Approver")
        result = self.gov.advance_status("D1", "Published")
        self.assertEqual(result["status"], "Published")
        self.assertTrue(self.store["DS Dashboard"]["D1"]["published_on"])

    # ---- scope is required to publish ----
    #
    # Sophia resolves an unknown subcriterion by falling back to the criterion's
    # default section, so a wrong or missing code renders the wrong data under
    # the right heading with no error. Publishing is where that gets refused.
    def test_unscoped_dashboard_cannot_be_published(self):
        self.store["DS Dashboard"]["D1"]["status"] = "QA Approval"
        self.store["DS Dashboard"]["D1"]["subcriterion"] = ""
        self._as("Dashboard Studio QA Approver")
        with self.assertRaises(_ValidationError):
            self.gov.advance_status("D1", "Published")
        self.assertEqual(self._status(), "QA Approval", "the move did not apply")

    def test_unknown_subcriterion_cannot_be_published_and_is_named(self):
        self.store["DS Dashboard"]["D1"]["status"] = "QA Approval"
        self.store["DS Dashboard"]["D1"]["subcriterion"] = "9.9.9"
        self._as("Dashboard Studio QA Approver")
        with self.assertRaises(_ValidationError) as caught:
            self.gov.advance_status("D1", "Published")
        self.assertIn("9.9.9", str(caught.exception), "the rejected code is named")
        self.assertEqual(self._status(), "QA Approval")

    def test_scope_is_not_required_for_earlier_stages(self):
        """A dashboard must stay authorable and reviewable before it is scoped."""
        self.store["DS Dashboard"]["D1"]["subcriterion"] = ""
        self._as("Dashboard Studio Editor")
        self.gov.advance_status("D1", "Technical Review")
        self.assertEqual(self._status(), "Technical Review")
        self.gov.advance_status("D1", "QA Approval")
        self.assertEqual(self._status(), "QA Approval")

    def test_system_manager_may_publish_as_superuser(self):
        self.store["DS Dashboard"]["D1"]["status"] = "QA Approval"
        self._as("System Manager")
        self.assertEqual(self.gov.advance_status("D1", "Published")["status"], "Published")

    def test_viewer_cannot_move_anything(self):
        self._as("Dashboard Studio Viewer")
        with self.assertRaises(_ValidationError):
            self.gov.advance_status("D1", "Technical Review")

    # ---- illegal jumps ----
    def test_cannot_skip_stages(self):
        self._as("Dashboard Studio QA Approver", "Dashboard Studio Editor")
        for target in ("QA Approval", "Published"):
            with self.assertRaises(_ValidationError, msg=target):
                self.gov.advance_status("D1", target)  # still in Draft
        self.assertEqual(self._status(), "Draft")

    def test_return_for_correction_is_allowed_from_review_stages(self):
        self.store["DS Dashboard"]["D1"]["status"] = "QA Approval"
        self._as("Dashboard Studio QA Approver")
        self.gov.advance_status("D1", "Draft")
        self.assertEqual(self._status(), "Draft")

    # ---- what the UI is told ----
    def test_transitions_report_what_this_user_may_do(self):
        self.store["DS Dashboard"]["D1"]["status"] = "QA Approval"
        self._as("Dashboard Studio Editor")
        moves = {t["to"]: t for t in self.gov.get_governance("D1")["transitions"]}
        self.assertFalse(moves["Published"]["allowed"], "editor may not publish")
        self.assertIn("Dashboard Studio QA Approver", moves["Published"]["requires"])
        # Disallowed moves are still listed, so the UI can explain rather than hide.
        self.assertTrue(moves["Draft"]["allowed"])

    # ---- change impact, from real Link fields ----
    def test_impact_counts_and_shared_metrics(self):
        self._as("Dashboard Studio Viewer")
        impact = self.gov.get_change_impact("D1")
        self.assertEqual(impact["charts"], 2)
        self.assertEqual(impact["sections"], 1)
        self.assertEqual(impact["metrics"], 2)
        # M-shared is on a chart in another dashboard too; M-solo is not.
        self.assertEqual(impact["shared_metrics"], [{"metric": "M-shared", "used_by_charts": 2}])

    # ---- native version history, not a bespoke one ----
    def test_version_history_comes_from_frappe_version_records(self):
        self._as("Dashboard Studio Viewer")
        versions = self.gov.get_version_history("D1")
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["owner"], "editor@example.invalid")


if __name__ == "__main__":
    unittest.main()
