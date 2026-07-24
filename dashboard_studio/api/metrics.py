import json

import frappe

from dashboard_studio.analytics.query_engine import (
    build_plan_from_ds_metric,
    build_query_plan,
    execute_query_plan,
)


@frappe.whitelist()
def build_metric_plan(metric_name: str):
    frappe.only_for("System Manager")
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
    metric = frappe.get_doc("DS Metric", metric_name)
    plan = build_plan_from_ds_metric(metric.as_dict())
    # Authorization already enforced above by the endpoint's role check; the
    # engine's default check would re-require System Manager and lock out
    # Editor/Viewer, so pass an explicit no-op here.
    return execute_query_plan(plan, permission_check=lambda: None)


def _load_json(value, default):
    if not value:
        return default
    return json.loads(value)
