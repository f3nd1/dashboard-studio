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
            # The batched read uses ["in", [...]]; a fake that only knew equality
            # would have quietly matched nothing and reported everything unchecked.
            if isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == "in":
                rows = [r for r in rows if r.get(key) in value[1]]
            else:
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
    # getdate mirrors frappe.utils.getdate: parse a date or datetime string to a
    # date, so "newer than last edit" is compared the same way the real gate does.
    def getdate(value):
        import datetime
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        return datetime.date.fromisoformat(str(value).split(" ")[0])

    frappe.utils = types.SimpleNamespace(now=lambda: "2026-07-25 10:00:00", getdate=getdate)
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
                "C1": {"name": "C1", "dashboard": "D1", "chart_title": "A", "metric": "M-shared",
                       "modified": "2026-07-20 09:00:00"},
                "C2": {"name": "C2", "dashboard": "D1", "chart_title": "B", "metric": "M-solo",
                       "modified": "2026-07-20 09:00:00"},
                # A chart on ANOTHER dashboard using the same metric — that is
                # what makes M-shared shared.
                "C3": {"name": "C3", "dashboard": "D2", "chart_title": "C", "metric": "M-shared"},
            },
            "DS Dashboard Section": {
                "S1": {"name": "S1", "dashboard": "D1", "section_title": "Intake"},
            },
            # Both D1 charts validated after their last edit, so the publish path
            # can be tested; each refusal has its own test below.
            "DS Validation Comparison": {
                "V-C1": {"name": "V-C1", "chart": "C1", "status": "Match",
                         "comparison_date": "2026-07-24"},
                "V-C2": {"name": "V-C2", "chart": "C2", "status": "Accepted",
                         "comparison_date": "2026-07-24"},
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

    # ---- charts must be linked and checked to publish ----
    #
    # Both refuse rather than exclude. A dashboard published with the offending
    # charts silently dropped looks complete and is not, which on audit evidence
    # is worse than a visible refusal.
    def _ready_to_publish(self):
        self.store["DS Dashboard"]["D1"]["status"] = "QA Approval"
        self._as("Dashboard Studio QA Approver")

    def test_metric_less_chart_blocks_publishing_and_is_named(self):
        self.store["DS Chart"]["C2"]["metric"] = ""
        self._ready_to_publish()
        with self.assertRaises(_ValidationError) as caught:
            self.gov.advance_status("D1", "Published")
        self.assertIn("B", str(caught.exception), "the offending chart is named")
        self.assertEqual(self._status(), "QA Approval")

    def test_chart_with_no_comparison_blocks_publishing_and_is_named(self):
        del self.store["DS Validation Comparison"]["V-C2"]
        self._ready_to_publish()
        with self.assertRaises(_ValidationError) as caught:
            self.gov.advance_status("D1", "Published")
        self.assertIn("B", str(caught.exception))
        self.assertNotIn("A", str(caught.exception), "the validated chart is not named")
        self.assertEqual(self._status(), "QA Approval")

    def test_comparison_older_than_the_last_edit_does_not_count(self):
        """A pass from before the chart changed proves nothing about it now."""
        self.store["DS Chart"]["C1"]["modified"] = "2026-07-25 09:00:00"
        self.store["DS Validation Comparison"]["V-C1"]["comparison_date"] = "2026-07-24"
        self._ready_to_publish()
        with self.assertRaises(_ValidationError) as caught:
            self.gov.advance_status("D1", "Published")
        self.assertIn("A", str(caught.exception))

    def test_same_day_comparison_counts(self):
        self.store["DS Chart"]["C1"]["modified"] = "2026-07-24 18:00:00"
        self.store["DS Validation Comparison"]["V-C1"]["comparison_date"] = "2026-07-24"
        self._ready_to_publish()
        self.assertEqual(self.gov.advance_status("D1", "Published")["status"], "Published")

    def test_discrepancy_and_flagged_do_not_count_as_checked(self):
        for status in ("Discrepancy", "Flagged"):
            with self.subTest(status=status):
                self.store["DS Validation Comparison"]["V-C2"]["status"] = status
                self.store["DS Dashboard"]["D1"]["status"] = "QA Approval"
                self._as("Dashboard Studio QA Approver")
                with self.assertRaises(_ValidationError):
                    self.gov.advance_status("D1", "Published")

    def test_another_dashboards_unvalidated_chart_does_not_block(self):
        self.store["DS Chart"]["C9"] = {"name": "C9", "dashboard": "D2",
                                        "chart_title": "Elsewhere", "metric": "",
                                        "modified": "2026-07-20 09:00:00"}
        self._ready_to_publish()
        self.assertEqual(self.gov.advance_status("D1", "Published")["status"], "Published")

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

    # ---- the same rules, evaluated for display ----
    #
    # The load-bearing property is that these are not a second implementation:
    # a readiness indicator that disagreed with the gate would show "ready" and
    # then refuse. Each test below pairs a display assertion with the gate's
    # behaviour on the identical fixture.
    def test_a_publishable_dashboard_reports_ready(self):
        self._as("Dashboard Studio Viewer")
        readiness = self.gov.publish_readiness("D1")
        self.assertTrue(readiness["publishable"])
        self.assertEqual(readiness["blockers"], [])
        self.assertEqual(readiness["charts_ready"], 2)
        self.assertEqual(readiness["charts_total"], 2)

    def test_display_and_gate_agree_on_every_blocker(self):
        """Whatever the display names, the gate refuses on — and vice versa."""
        cases = {
            "scope": lambda: self.store["DS Dashboard"]["D1"].update({"subcriterion": ""}),
            "scope_unknown": lambda: self.store["DS Dashboard"]["D1"].update(
                {"subcriterion": "9.9.9"}),
            "chart_without_metric": lambda: self.store["DS Chart"]["C2"].update({"metric": ""}),
            "chart_not_validated": lambda: self.store["DS Validation Comparison"].pop("V-C2"),
        }
        for rule, break_it in cases.items():
            with self.subTest(rule=rule):
                self.setUp()
                break_it()
                self._as("Dashboard Studio QA Approver", "Dashboard Studio Viewer")
                readiness = self.gov.publish_readiness("D1")
                self.assertFalse(readiness["publishable"])
                self.assertIn(rule, [b["rule"] for b in readiness["blockers"]])

                self.store["DS Dashboard"]["D1"]["status"] = "QA Approval"
                with self.assertRaises(_ValidationError) as caught:
                    self.gov.advance_status("D1", "Published")
                # The refusal text IS the display text — not a parallel wording.
                for blocker in readiness["blockers"]:
                    self.assertIn(blocker["message"], str(caught.exception))

    def test_every_blocker_names_the_charts_responsible(self):
        self.store["DS Chart"]["C2"]["metric"] = ""
        self._as("Dashboard Studio Viewer")
        blocker = [b for b in self.gov.publish_readiness("D1")["blockers"]
                   if b["rule"] == "chart_without_metric"][0]
        self.assertEqual(blocker["charts"], ["B"])

    def test_an_unlinked_chart_is_not_also_reported_as_unvalidated(self):
        """One problem, named once. Two entries would read as two faults."""
        self.store["DS Chart"]["C2"]["metric"] = ""
        del self.store["DS Validation Comparison"]["V-C2"]
        self._as("Dashboard Studio Viewer")
        rules = [b["rule"] for b in self.gov.publish_readiness("D1")["blockers"]]
        self.assertIn("chart_without_metric", rules)
        self.assertNotIn("chart_not_validated", rules)

    def test_charts_ready_counts_only_linked_and_currently_validated(self):
        self.store["DS Chart"]["C1"]["modified"] = "2026-07-25 09:00:00"  # newer than its pass
        self.store["DS Chart"]["C2"]["metric"] = ""
        self._as("Dashboard Studio Viewer")
        readiness = self.gov.publish_readiness("D1")
        self.assertEqual(readiness["charts_ready"], 0)
        self.assertEqual(readiness["charts_total"], 2)

    def test_all_blockers_are_reported_together_not_one_at_a_time(self):
        """Fixing one and rediscovering the next is the problem being fixed."""
        self.store["DS Dashboard"]["D1"]["subcriterion"] = ""
        self.store["DS Chart"]["C2"]["metric"] = ""
        del self.store["DS Validation Comparison"]["V-C1"]
        self._as("Dashboard Studio Viewer")
        rules = [b["rule"] for b in self.gov.publish_readiness("D1")["blockers"]]
        self.assertEqual(rules, ["scope", "chart_without_metric", "chart_not_validated"])

    def test_readiness_is_read_gated(self):
        self._as()
        with self.assertRaises(_PermissionError):
            self.gov.publish_readiness("D1")

    def test_the_comparison_read_is_batched(self):
        """Three queries whatever the chart count — it now runs on every load."""
        calls = []
        inner = self.frappe.get_all
        self.frappe.get_all = lambda dt, **kw: (calls.append(dt), inner(dt, **kw))[1]
        for i in range(20):
            self.store["DS Chart"][f"X{i}"] = {
                "name": f"X{i}", "dashboard": "D1", "chart_title": f"X{i}",
                "metric": "M-solo", "modified": "2026-07-20 09:00:00",
            }
        self._as("Dashboard Studio Viewer")
        self.gov.publish_readiness("D1")
        self.assertEqual(calls.count("DS Validation Comparison"), 1, calls)

    # ---- native version history, not a bespoke one ----
    def test_version_history_comes_from_frappe_version_records(self):
        self._as("Dashboard Studio Viewer")
        versions = self.gov.get_version_history("D1")
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["owner"], "editor@example.invalid")


if __name__ == "__main__":
    unittest.main()
