"""The SHAPE a metric refusal reaches the browser in.

The engine raises plain Python exceptions. Frappe turns those into a 500 with a
traceback and shows its own error dialog, which a frontend .catch cannot
suppress. ``frappe.throw`` makes the same refusal a 417 carrying the same
sentence, which the chart card renders.

So every test here asserts two things together: the call still REFUSES, and the
message is byte-identical to what the engine raises. A wrapper that softened a
refusal would pass the first assertion and fail the second.

MOCK-BASED for Frappe — no live Bench. The fake models the exception classes
real Frappe uses (DoesNotExistError from a missing record or DocType,
ValidationError from throw), because the point of these tests is exception type.
"""

import sys
import types
import unittest


class _PermissionError(Exception):
    pass


class _ValidationError(Exception):
    """Stands in for frappe.ValidationError — what frappe.throw raises (417)."""


class _DoesNotExistError(Exception):
    """Stands in for frappe.DoesNotExistError — a missing record or DocType."""


class _FakeDoc(dict):
    """Attribute access like Frappe's Document — the endpoints read doc.status."""

    def as_dict(self):
        return dict(self)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)


APPROVED = {
    "metric_name": "Applicants by year", "status": "Approved", "calculation_type": "Count",
    "source_doctype": "Student Applicant", "group_by_field": "academic_year",
    "value_field": "", "allowed_fields": "academic_year", "metric_filters": [],
}


def _make_fake_frappe(metrics, doctypes):
    frappe = types.ModuleType("frappe")
    frappe.PermissionError = _PermissionError
    frappe.ValidationError = _ValidationError
    frappe.DoesNotExistError = _DoesNotExistError
    frappe._roles = {"Dashboard Studio Editor", "Dashboard Studio QA Approver"}

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
        record = metrics.get(name)
        if record is None:
            # Real Frappe raises DoesNotExistError here, not KeyError. A fake that
            # raised KeyError would have shown this wrapper doing nothing.
            raise _DoesNotExistError(f"{doctype} {name} not found")
        return _FakeDoc(record)

    def get_all(doctype, **kwargs):
        if doctype not in doctypes:
            # What a renamed or deleted source DocType actually produces.
            raise _DoesNotExistError(f"DocType {doctype} not found")
        return [{"academic_year": "2023", "count": 3}]

    def throw(msg):
        raise _ValidationError(msg)

    frappe.only_for = only_for
    frappe.whitelist = whitelist
    frappe.get_doc = get_doc
    frappe.get_all = get_all
    frappe.throw = throw
    return frappe


class _Base(unittest.TestCase):
    metrics = {"M-ok": APPROVED}
    doctypes = {"Student Applicant"}

    def setUp(self):
        self._saved = {
            k: v for k, v in sys.modules.items()
            if k == "frappe" or k.startswith("dashboard_studio.")
        }
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        self.frappe = _make_fake_frappe(dict(self.metrics), set(self.doctypes))
        sys.modules["frappe"] = self.frappe
        import dashboard_studio.api.metrics as api_metrics
        from dashboard_studio.analytics.query_engine import build_plan_from_ds_metric

        self.api = api_metrics
        self._build = build_plan_from_ds_metric

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    def refusal(self, fn, *args, **kwargs):
        """Assert it refuses as a 417, and return the message it refused with."""
        with self.assertRaises(_ValidationError) as caught:
            fn(*args, **kwargs)
        return str(caught.exception)

    def engine_message(self, metric, **kwargs):
        """What the engine says when called directly — the text that must survive."""
        try:
            self._build(dict(metric), **kwargs)
        except Exception as exc:                      # noqa: BLE001
            return str(exc)
        raise AssertionError("the engine did not refuse this metric at all")


class TestRunDsMetric(_Base):
    metrics = {
        "M-ok": APPROVED,
        "M-draft": dict(APPROVED, metric_name="Survey responses", status="Draft"),
        "M-gone-doctype": dict(APPROVED, source_doctype="Student Applicant Renamed"),
        "M-no-allowlist": dict(APPROVED, allowed_fields=""),
        "M-sum": dict(APPROVED, calculation_type="Sum", value_field="fee"),
        "M-dynamic": dict(APPROVED, metric_filters=[
            {"fieldname": "academic_year", "operator": "=", "value": "x",
             "filter_type": "Dynamic"}]),
        "M-unallowlisted": dict(APPROVED, group_by_field="nationality"),
    }

    def test_the_happy_path_is_unchanged(self):
        self.assertEqual(self.api.run_ds_metric("M-ok"), [{"academic_year": "2023", "count": 3}])

    def test_draft_still_refuses_with_the_same_words(self):
        message = self.refusal(self.api.run_ds_metric, "M-draft")
        self.assertEqual(message, self.engine_message(self.metrics["M-draft"]))
        self.assertIn("only Approved metrics can be executed", message)

    def test_a_renamed_or_deleted_source_doctype_refuses_cleanly(self):
        """The live example that started this: the DocType is gone mid-session."""
        message = self.refusal(self.api.run_ds_metric, "M-gone-doctype")
        self.assertIn("Student Applicant Renamed", message)
        self.assertIn("not found", message)

    def test_a_deleted_metric_record_refuses_cleanly(self):
        message = self.refusal(self.api.run_ds_metric, "M-vanished")
        self.assertIn("DS Metric", message)
        self.assertIn("not found", message)

    def test_block_by_default_still_refuses(self):
        message = self.refusal(self.api.run_ds_metric, "M-no-allowlist")
        self.assertEqual(message, self.engine_message(self.metrics["M-no-allowlist"]))
        self.assertIn("no allowed_fields", message)

    def test_non_count_calculation_still_refuses(self):
        message = self.refusal(self.api.run_ds_metric, "M-sum")
        self.assertEqual(message, self.engine_message(self.metrics["M-sum"]))

    def test_dynamic_filter_still_refuses(self):
        message = self.refusal(self.api.run_ds_metric, "M-dynamic")
        self.assertEqual(message, self.engine_message(self.metrics["M-dynamic"]))

    def test_unallowlisted_field_still_refuses_with_its_hint(self):
        message = self.refusal(self.api.run_ds_metric, "M-unallowlisted")
        self.assertEqual(message, self.engine_message(self.metrics["M-unallowlisted"]))
        self.assertIn("not allowlisted", message)

    def test_a_permission_failure_is_still_a_permission_failure(self):
        """403 must not be rewritten as a validation message."""
        self.frappe._roles = set()
        with self.assertRaises(_PermissionError):
            self.api.run_ds_metric("M-ok")

    def test_nothing_raises_a_bare_python_exception(self):
        """Whatever the reason, the browser must never get a 500 from this path."""
        for name in self.metrics:
            if name == "M-ok":
                continue
            try:
                self.api.run_ds_metric(name)
            except _ValidationError:
                continue
            except Exception as exc:                  # noqa: BLE001
                self.fail(f"{name} escaped as {type(exc).__name__}: {exc}")


class TestPreviewDsMetric(_Base):
    metrics = {
        "M-draft": dict(APPROVED, status="Draft"),
        "M-no-allowlist": dict(APPROVED, status="Draft", allowed_fields=""),
        "M-gone-doctype": dict(APPROVED, status="Draft",
                               source_doctype="Student Applicant Renamed"),
        "M-dynamic": dict(APPROVED, status="Draft", metric_filters=[
            {"fieldname": "academic_year", "operator": "=", "value": "x",
             "filter_type": "Dynamic"}]),
    }

    def test_preview_still_runs_a_draft_metric(self):
        """The whole point of preview — this must NOT start refusing."""
        result = self.api.preview_ds_metric("M-draft")
        self.assertEqual(result["status"], "Draft")
        self.assertEqual(result["rows"], [{"academic_year": "2023", "count": 3}])

    def test_block_by_default_still_refuses_in_preview(self):
        message = self.refusal(self.api.preview_ds_metric, "M-no-allowlist")
        self.assertEqual(
            message, self.engine_message(self.metrics["M-no-allowlist"], allow_draft=True)
        )

    def test_renamed_source_doctype_refuses_cleanly_in_preview(self):
        self.assertIn("not found", self.refusal(self.api.preview_ds_metric, "M-gone-doctype"))

    def test_dynamic_filter_refuses_cleanly_in_preview(self):
        self.assertIn("Dynamic", self.refusal(self.api.preview_ds_metric, "M-dynamic"))

    def test_a_permission_failure_is_still_a_permission_failure(self):
        self.frappe._roles = {"Dashboard Studio Viewer"}
        with self.assertRaises(_PermissionError):
            self.api.preview_ds_metric("M-draft")


class TestOldPath(_Base):
    """run_metric / build_metric_plan serve the frozen placeholder DocTypes."""

    metrics = {
        "OLD": {"dataset": "DS-1", "dimension_field": "academic_year",
                "measure_field": "name", "aggregation": "count", "conditions_json": ""},
        "DS-1": {"source_doctype": "Student Applicant",
                 "allowed_fields_json": '["academic_year", "name"]', "restricted_fields_json": ""},
        "OLD-bad": {"dataset": "DS-bad", "dimension_field": "nationality",
                    "measure_field": "name", "aggregation": "count", "conditions_json": ""},
        "DS-bad": {"source_doctype": "Student Applicant",
                   "allowed_fields_json": '["academic_year"]', "restricted_fields_json": ""},
    }

    def setUp(self):
        super().setUp()
        self.frappe._roles = {"System Manager"}

    def test_old_path_happy_case_is_unchanged(self):
        self.assertEqual(self.api.run_metric("OLD"), [{"academic_year": "2023", "count": 3}])

    def test_old_path_refuses_cleanly(self):
        self.assertIn("not allowlisted", self.refusal(self.api.run_metric, "OLD-bad"))

    def test_old_path_missing_record_refuses_cleanly(self):
        self.assertIn("not found", self.refusal(self.api.build_metric_plan, "OLD-missing"))


if __name__ == "__main__":
    unittest.main()
