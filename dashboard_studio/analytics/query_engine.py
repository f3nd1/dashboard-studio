from __future__ import annotations

from typing import Any

from dashboard_studio.analytics.validators import validate_metric_config


def build_query_plan(metric_config: dict[str, Any], dataset_config: dict[str, Any]) -> dict[str, Any]:
    """Build a validated, non-executable query plan.

    Phase 1 intentionally stops at a query plan. Database execution must be implemented
    inside Frappe with permission checks, row limits, and focused tests.
    """

    validated = validate_metric_config(metric_config, dataset_config)
    return {
        "version": 1,
        "source": {"doctype": validated["source_doctype"]},
        "group_by": [validated["dimension"]] if validated["dimension"] else [],
        "measure": {
            "field": validated["measure"],
            "aggregation": validated["aggregation"],
        },
        "conditions": validated["conditions"],
        "limits": {"max_groups": 500, "max_drilldown_rows": 200},
        "executable": False,
    }


def execute_query_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    raise NotImplementedError(
        "Production execution is intentionally not implemented in the starter scaffold. "
        "Add a Frappe permission-aware executor with tests before enabling previews."
    )
