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


def _require_system_manager() -> None:
    """Default permission check: caller must hold Frappe's System Manager role.

    Imported lazily so this module stays importable (and unit-testable) without a
    Frappe site. No new Dashboard Studio roles are introduced here.
    """
    import frappe

    frappe.only_for("System Manager")


def _frappe_count_by_dimension(
    doctype: str, dimension: str, conditions: list[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    """Default fetch: a grouped COUNT run through the permission-aware Frappe ORM.

    The database does the counting (never a raw SQL string), so this never grows
    unbounded in Python. Rows come back as {dimension: value, "count": int}.
    """
    import frappe

    filters = [[c["field"], c["operator"], c.get("value")] for c in conditions]
    return frappe.get_all(
        doctype,
        filters=filters or None,
        fields=[dimension, "count(name) as count"],
        group_by=dimension,
        order_by=f"{dimension} asc",
        limit=limit,
    )


def execute_query_plan(
    plan: dict[str, Any],
    *,
    fetch=None,
    permission_check=None,
) -> list[dict[str, Any]]:
    """Execute a validated plan for the one proven Phase 1 slice.

    Supported: a single source DocType, a single group-by dimension, and a
    ``count`` aggregation (e.g. Student Applicant count grouped by academic_year).
    Joins, multiple dimensions, and any other aggregation are intentionally out of
    scope and raise ``NotImplementedError``.

    Dependency-injected so the full validate -> plan -> execute path is testable
    without a live Bench:

    - ``permission_check()`` raises if the caller lacks access. Default enforces
      Frappe's System Manager role.
    - ``fetch(doctype, dimension, conditions, limit) -> list[dict]`` returns rows
      each carrying the dimension value and an int ``count``. Default runs a
      grouped count via the Frappe ORM.
    """

    aggregation = (plan.get("measure") or {}).get("aggregation")
    group_by = plan.get("group_by") or []
    if aggregation != "count" or len(group_by) != 1:
        raise NotImplementedError(
            "execute_query_plan currently supports only a count aggregation grouped "
            "by exactly one dimension. Joins, multiple dimensions, and other "
            "aggregations are out of scope for this slice."
        )

    (permission_check or _require_system_manager)()

    doctype = plan["source"]["doctype"]
    dimension = group_by[0]
    conditions = plan.get("conditions") or []
    max_groups = (plan.get("limits") or {}).get("max_groups", 500)

    # Safety guard: ask for one row past the ceiling so an overflow is detected and
    # reported, never silently truncated into a wrong count.
    rows = (fetch or _frappe_count_by_dimension)(doctype, dimension, conditions, max_groups + 1)
    if len(rows) > max_groups:
        raise ValueError(
            f"Result exceeded the max_groups safety limit ({max_groups}); refine the metric."
        )

    result = [
        {dimension: row.get(dimension), "count": int(row.get("count") or 0)} for row in rows
    ]
    # Match the legacy Metabase baseline: ORDER BY <dimension> ASC, NULLs last.
    result.sort(key=lambda row: (row[dimension] is None, row[dimension]))
    return result
