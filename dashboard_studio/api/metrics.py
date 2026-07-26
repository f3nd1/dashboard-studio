import json
from contextlib import contextmanager

import frappe

from dashboard_studio.analytics.query_engine import (
    build_plan_from_ds_metric,
    build_query_plan,
    execute_query_plan,
)
from dashboard_studio.analytics.validators import DefinitionValidationError


@contextmanager
def _clean_refusal():
    """Turn the engine's refusals into refusals the browser can render.

    NOT a relaxation. Every guard still refuses, with the identical message.
    What changes is the shape it arrives in: the engine raises plain Python
    exceptions, Frappe turns those into a 500 with a traceback and shows its own
    error dialog, and a frontend .catch cannot suppress a dialog Frappe raised
    first. frappe.throw makes it a 417 carrying the same sentence, which the
    chart card already knows how to display.

    A context manager rather than a decorator on purpose: frappe.call unwraps
    __wrapped__ before invoking a whitelisted method, so a functools.wraps
    decorator would be stepped over at runtime and this would silently do
    nothing — passing every fixture test while changing nothing live.

    ponytail: catches the exception TYPES the engine refuses with, so an
    unexpected ValueError from elsewhere in the stack now also presents as a
    polite refusal instead of a traceback. The ceiling is that a genuine bug in
    this path reads as a refusal; the trade is deliberate, because the refusals
    are the common case by a wide margin. Narrow it to a dedicated
    MetricRefused exception if a real bug ever hides here.
    """
    try:
        yield
    except (
        ValueError,
        NotImplementedError,
        DefinitionValidationError,
        frappe.DoesNotExistError,
    ) as exc:
        frappe.throw(str(exc))


@frappe.whitelist()
def build_metric_plan(metric_name: str):
    frappe.only_for("System Manager")
    with _clean_refusal():
        metric = frappe.get_doc("Metric Definition", metric_name)
        dataset = frappe.get_doc("Dataset Definition", metric.dataset)

        metric_config = {
            "dimension": metric.dimension_field,
            "measure": metric.measure_field,
            "aggregation": metric.aggregation,
            "conditions": _load_json(metric.conditions_json, []),
        }
        dataset_config = {
            "source_doctype": dataset.source_doctype,
            "allowed_fields": _load_json(dataset.allowed_fields_json, []),
            "restricted_fields": _load_json(dataset.restricted_fields_json, []),
        }
        return build_query_plan(metric_config, dataset_config)


@frappe.whitelist()
def run_metric(metric_name: str):
    """Build and execute a metric plan in one whitelisted call.

    Only the count-by-single-dimension slice is supported today; anything else
    raises NotImplementedError from execute_query_plan. build_metric_plan already
    enforces System Manager and validates the config before this runs.
    """
    plan = build_metric_plan(metric_name)
    with _clean_refusal():
        return execute_query_plan(plan)


@frappe.whitelist()
def run_ds_metric(metric_name: str):
    """Execute a DS Metric record by name (count-by-single-dimension slice).

    Separate from run_metric, which serves the older Metric Definition schema.
    Reads the DS Metric doc, adapts it to the engine config, and runs it through
    the same safety cap already in place. Running a metric is a read action, so
    Editor or Viewer (or System Manager) may execute it. Only Approved metrics
    run; see build_plan_from_ds_metric for the scope guards.
    """
    frappe.only_for(("Dashboard Studio Editor", "Dashboard Studio Viewer", "System Manager"))
    # The role check stays OUTSIDE: a PermissionError must remain a 403, not be
    # rewritten into a validation message.
    with _clean_refusal():
        metric = frappe.get_doc("DS Metric", metric_name)
        plan = build_plan_from_ds_metric(metric.as_dict())
        # Authorization already enforced above by the endpoint's role check; the
        # engine's default check would re-require System Manager and lock out
        # Editor/Viewer, so pass an explicit no-op here.
        return execute_query_plan(plan, permission_check=lambda: None)


@frappe.whitelist()
def preview_ds_metric(metric_name: str):
    """Run a metric that has NOT been approved yet, so approval is a real decision.

    Deliberately separate from run_ds_metric, and deliberately NOT reflected in
    list_ds_metrics: the Approved-only filter stays everywhere a chart is built
    for real. This path exists so someone can look at the numbers before signing
    off, and nowhere else.

    Gated tighter than run_ds_metric. Running an Approved metric is a read any DS
    user may do, because approval is the control that made it safe; an
    unapproved one has passed nobody, and the engine's fetch uses frappe.get_all
    (which ignores DocType permissions), so a Viewer could otherwise count rows
    in a DocType they cannot read. Authors and approvers only.
    """
    frappe.only_for((
        "Dashboard Studio Editor",
        "Dashboard Studio QA Approver",
        "System Manager",
    ))
    with _clean_refusal():
        metric = frappe.get_doc("DS Metric", metric_name)
        plan = build_plan_from_ds_metric(metric.as_dict(), allow_draft=True)
        rows = execute_query_plan(plan, permission_check=lambda: None)
    return {
        "metric": metric_name,
        "status": metric.status,
        "source_doctype": metric.source_doctype,
        "group_by_field": metric.group_by_field,
        "rows": rows,
    }


def _load_json(value, default):
    if not value:
        return default
    return json.loads(value)
