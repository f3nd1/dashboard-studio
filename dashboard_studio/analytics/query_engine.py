from __future__ import annotations

import re
from typing import Any

from dashboard_studio.analytics.validators import DefinitionValidationError, validate_metric_config


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


_DS_STATIC = "Static"
_DS_APPROVED = "Approved"


def build_plan_from_ds_metric(
    metric: dict[str, Any], *, allow_draft: bool = False
) -> dict[str, Any]:
    """Adapter: turn a DS Metric record into the config the generic engine already runs.

    Connects the DS Metric schema to the proven slice — a single source DocType,
    single group-by dimension, ``Count``. It does NOT expand capability: any
    calculation_type other than Count, a missing group_by_field, a Dynamic filter,
    or an unsupported operator is rejected with a clear error.

    Pure and Frappe-free so it stays unit-testable without a live Bench. Pass a
    plain dict (``frappe.get_doc(...).as_dict()`` shape); child rows in
    ``metric_filters`` are dicts too.

    ``allow_draft`` relaxes ONLY the approval check, for the preview path — an
    approver has to see what a metric produces before signing it off, or approval
    is a formality. Every other guard still applies: the field allowlist,
    block-by-default, count-only, and the field-name syntax rule. A named
    argument rather than a caller faking ``status``, so the bypass is greppable
    and a future Approved-only rule is not silently relaxed with it.

    FIELD ALLOWLIST (block-by-default): the metric's ``allowed_fields`` (newline-
    or comma-separated) constrains which fields it may reference. If it is empty,
    the metric is REFUSED — no allowlist means no execution, closing the gap where
    the old path's Dataset allowlist had no DS equivalent. When set, every
    referenced field (dimension, filter fields, and an explicit value_field) must
    be listed. The one exemption: a pure count's default measure ``name`` (the
    docname / count mechanism, not business data) is auto-allowed so count metrics
    need not list it.
    """

    status = (metric.get("status") or "").strip()
    if status != _DS_APPROVED and not allow_draft:
        raise ValueError(
            f"DS Metric '{metric.get('metric_name') or '<unnamed>'}' is {status or 'unset'}; "
            f"only {_DS_APPROVED} metrics can be executed."
        )

    calc = (metric.get("calculation_type") or "").strip().lower()
    if calc != "count":
        raise NotImplementedError(
            f"DS Metric execution currently supports only calculation_type 'Count', not "
            f"'{metric.get('calculation_type') or '<blank>'}'."
        )

    source_doctype = (metric.get("source_doctype") or "").strip()
    if not source_doctype:
        raise ValueError("DS Metric is missing source_doctype")

    dimension = (metric.get("group_by_field") or "").strip()
    if not dimension:
        raise ValueError("DS Metric is missing group_by_field (required for the count-by-group slice)")

    conditions = []
    for row in metric.get("metric_filters") or []:
        filter_type = (row.get("filter_type") or _DS_STATIC).strip()
        if filter_type != _DS_STATIC:
            raise NotImplementedError(
                f"Dynamic metric filters are not supported yet (field '{row.get('fieldname')}'). "
                "Use Static filters for now."
            )
        field = (row.get("fieldname") or "").strip()
        if not field:
            raise ValueError("A metric filter is missing its fieldname")
        conditions.append(
            {"field": field, "operator": (row.get("operator") or "").strip(), "value": row.get("value")}
        )

    allowed_fields = _split_allowed_fields(metric.get("allowed_fields"))
    if not allowed_fields:
        raise ValueError(
            f"DS Metric '{metric.get('metric_name') or '<unnamed>'}' has no allowed_fields; "
            "refusing to execute (block-by-default). List the fields it may reference."
        )

    value_field = (metric.get("value_field") or "").strip()
    measure = value_field or "name"
    # A pure count's measure is Frappe's docname ("name"), the count mechanism —
    # not business data — so exempt just that one field from the allowlist rather
    # than making every count metric list "name". Only when value_field is unset;
    # an explicit value_field must still be allowlisted.
    effective_allowed = list(allowed_fields)
    if not value_field and "name" not in effective_allowed:
        effective_allowed.append("name")

    metric_config = {
        "dimension": dimension,
        "measure": measure,
        "aggregation": "count",
        "conditions": conditions,
    }
    dataset_config = {
        "source_doctype": source_doctype,
        "allowed_fields": effective_allowed,
        "restricted_fields": [],
    }
    try:
        return build_query_plan(metric_config, dataset_config)
    except DefinitionValidationError as exc:
        # Enrich the allowlist-rejection message so a typo (in the field name OR
        # in the allowlist entry) is obvious by comparison. Field-existence
        # validation against real DocType metadata is deferred (needs a live Bench).
        if "not allowlisted" in str(exc):
            raise ValueError(
                f"{exc}. This metric's allowed_fields: {allowed_fields or '(none)'}. "
                "Check for a typo — the referenced field must match an allowlist entry exactly."
            ) from exc
        raise


def _split_allowed_fields(value: Any) -> list[str]:
    """Parse DS Metric.allowed_fields (newline- or comma-separated) into a list."""
    if not value:
        return []
    parts = re.split(r"[,\n]", str(value))
    return [p.strip() for p in parts if p.strip()]


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
    try:
        result.sort(key=lambda row: (row[dimension] is None, row[dimension]))
    except TypeError:
        # Mixed-type dimension values (e.g. int and str years) are not mutually
        # comparable; fall back to string order rather than crashing.
        result.sort(key=lambda row: (row[dimension] is None, str(row[dimension])))
    return result
