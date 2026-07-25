"""Validation Centre: compare a source result against this app's result.

Wires analytics/comparison.py to DS Validation Comparison records.

SCHEMA NOTE — deliberately not worked around: compare_result_sets reports one
row per group, but DS Validation Comparison has no field for a group label, so
per-group rows cannot be persisted without inventing one. Each run therefore
stores ONE record per chart holding the totals (which the schema fits exactly)
and returns the full per-group breakdown for the UI to display live. Persisting
per-group detail needs a schema decision, not a workaround here.

The three safety rules from comparison.py are preserved end to end:
- "Accepted" is never computed. Only accept_comparison() sets it, and only with
  a reason and a named reviewer.
- Flagged is distinct from Discrepancy — unknown is not the same as wrong.
- Groups missing from either side are reported, never dropped.
"""

import json

import frappe

from dashboard_studio.analytics.comparison import compare_result_sets
from dashboard_studio.api.studio import DS_READ_ROLES, DS_WRITE_ROLES


@frappe.whitelist()
def run_validation(chart: str, source_rows, target_rows=None, tolerance_pct=0):
    """Compare a source result against the chart's result and record the outcome.

    ``source_rows`` is the reference result (e.g. exported from the legacy
    system). ``target_rows`` may be supplied directly; when omitted the chart's
    linked metric is executed to produce it.
    """
    frappe.only_for(DS_WRITE_ROLES)
    source_rows = _as_rows(source_rows, "source_rows")

    chart_doc = frappe.get_doc("DS Chart", chart)
    if target_rows is None:
        if not chart_doc.metric:
            frappe.throw("This chart has no metric, so there is nothing to compare against.")
        from dashboard_studio.api.metrics import run_ds_metric

        target_rows = run_ds_metric(chart_doc.metric)
    else:
        target_rows = _as_rows(target_rows, "target_rows")

    result = compare_result_sets(
        source_rows, target_rows, tolerance_pct=float(tolerance_pct or 0)
    )
    totals = result["totals"]

    doc = frappe.get_doc(
        {
            "doctype": "DS Validation Comparison",
            "chart": chart,
            "comparison_date": frappe.utils.today(),
            "original_value": _as_text(totals.get("original_value")),
            "new_value": _as_text(totals.get("new_value")),
            "difference_pct": totals.get("difference_pct"),
            # Overall status, worst-first: a Flagged group outranks a Discrepancy.
            "status": result["status"],
        }
    ).insert()

    return {
        "comparison": doc.name,
        "status": result["status"],
        "summary": result["summary"],
        # Per-group detail is returned for display but not persisted (see module note).
        "rows": result["rows"],
        "totals": totals,
        "persisted_rows": False,
    }


@frappe.whitelist()
def list_comparisons(chart: str = None, migration_project: str = None):
    """Recorded comparisons, newest first."""
    frappe.only_for(DS_READ_ROLES)
    filters = {}
    if chart:
        filters["chart"] = chart
    if migration_project:
        filters["migration_project"] = migration_project
    return frappe.get_all(
        "DS Validation Comparison",
        filters=filters or None,
        fields=[
            "name", "chart", "migration_project", "comparison_date",
            "original_value", "new_value", "difference_pct", "status",
            "accepted_reason", "reviewed_by",
        ],
        order_by="comparison_date desc, modified desc",
        limit=100,
    )


@frappe.whitelist()
def accept_comparison(comparison: str, accepted_reason: str):
    """Accept a known difference. Requires a reason and records who accepted it.

    This is the ONLY path to the Accepted status — the arithmetic never produces
    it, because accepting a difference is a human judgement.
    """
    frappe.only_for(DS_WRITE_ROLES)
    reason = (accepted_reason or "").strip()
    if not reason:
        frappe.throw("A reason is required to accept a difference.")

    doc = frappe.get_doc("DS Validation Comparison", comparison)
    if doc.status == "Match":
        frappe.throw("This comparison already matches; there is no difference to accept.")

    doc.status = "Accepted"
    doc.accepted_reason = reason
    doc.reviewed_by = frappe.session.user
    doc.save()
    return doc.as_dict()


def _as_rows(value, label):
    if isinstance(value, str):
        value = json.loads(value)
    if value is None:
        return []
    if not isinstance(value, list):
        frappe.throw(f"{label} must be a JSON array of result rows")
    return [row for row in value if isinstance(row, dict)]


def _as_text(value):
    """DS Validation Comparison stores values as Data."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
