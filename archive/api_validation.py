"""Validation Centre: compare a source result against this app's result.

Wires analytics/comparison.py to DS Validation Comparison records.

One DS Validation Comparison record is one comparison RUN: it holds the totals,
the overall status and the acceptance decision, with per-group detail in its
comparison_rows child table. A run is the unit that gets accepted, so acceptance
lives on the parent and the child rows carry no Accepted status.

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
            "comparison_rows": [_row_for_storage(row) for row in result["rows"]],
        }
    ).insert()

    return {
        "comparison": doc.name,
        "status": result["status"],
        "summary": result["summary"],
        "rows": result["rows"],
        "totals": totals,
        "persisted_rows": True,
    }


def _row_for_storage(row):
    """One comparison row as a DS Validation Row child.

    Blanks stay blank: a group that could not be compared has no difference, and
    writing 0 would turn "unknown" into "identical".
    """
    return {
        "group_label": _as_text(row.get("label")),
        "original_value": _as_text(row.get("original_value")),
        "new_value": _as_text(row.get("new_value")),
        "difference": _as_text(row.get("difference")),
        "difference_pct": _as_text(row.get("difference_pct")),
        "status": row.get("status"),
        "reason": row.get("reason") or "",
    }


@frappe.whitelist()
def get_comparison(comparison: str):
    """One comparison run with its full per-group breakdown."""
    frappe.only_for(DS_READ_ROLES)
    doc = frappe.get_doc("DS Validation Comparison", comparison)
    data = doc.as_dict()
    data["comparison_rows"] = [
        {
            key: row.get(key)
            for key in (
                "group_label", "original_value", "new_value",
                "difference", "difference_pct", "status", "reason",
            )
        }
        for row in (doc.get("comparison_rows") or [])
    ]
    return data


@frappe.whitelist()
def list_comparisons(chart: str = None, migration_project: str = None):
    """Recorded comparisons, newest first."""
    frappe.only_for(DS_READ_ROLES)
    filters = {}
    if chart:
        filters["chart"] = chart
    if migration_project:
        filters["migration_project"] = migration_project
    rows = frappe.get_all(
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
    # DS Chart has no autoname, so `chart` is a hash. Displaying it put
    # "thu5c209k3" in the Validation table where every other view shows the
    # chart's title. One batched read, not one per row — the same shape
    # publish_readiness uses for the same reason.
    linked = sorted({r["chart"] for r in rows if r.get("chart")})
    if linked:
        titles = {
            c["name"]: c["chart_title"]
            for c in frappe.get_all(
                "DS Chart", filters={"name": ["in", linked]}, fields=["name", "chart_title"]
            )
        }
        for row in rows:
            # Falls back to the hash rather than blank: a deleted chart still has
            # to be identifiable in its own comparison row.
            row["chart_title"] = titles.get(row.get("chart")) or row.get("chart")
    return rows


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
