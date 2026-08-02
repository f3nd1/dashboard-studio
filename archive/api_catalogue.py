"""Data & DocTypes workspace: what records exist and how they relate.

Everything here is derived from the DS schema and real records — no invented
metadata. Notably absent, because nothing backs them:

- Field *types* for the safe-field catalogue would need frappe.get_meta on each
  source DocType; that is deferred with the rest of the live-Bench work.
- A "restricted fields" list. DS Metric has allowed_fields only; the allowlist is
  block-by-default, which is stricter than a denylist. There is no restricted
  concept to report, so none is reported.
"""

import json
import os

import frappe

from dashboard_studio.api.studio import DS_READ_ROLES

# The DS DocTypes this workspace reports on, in a sensible reading order.
_DS_DOCTYPES = (
    "DS Dashboard",
    "DS Dashboard Section",
    "DS Chart",
    "DS Metric",
    "DS Data Source",
    "DS Data Mapping",
    "DS Migration Project",
    "DS Validation Comparison",
)

# One representative summary field per DocType, so each card can show something
# more useful than a bare count.
_TITLE_FIELD = {
    "DS Dashboard": "dashboard_title",
    "DS Dashboard Section": "section_title",
    "DS Chart": "chart_title",
    "DS Metric": "metric_name",
    "DS Data Source": "source_name",
    "DS Migration Project": "project_name",
}

# DocTypes carrying a status field worth breaking down on the card.
_STATUS_DOCTYPES = ("DS Dashboard", "DS Metric", "DS Migration Project", "DS Validation Comparison")


@frappe.whitelist()
def get_catalogue():
    """Record counts, per-status breakdowns and the real relationship graph."""
    frappe.only_for(DS_READ_ROLES)
    return {
        "doctypes": [_summarise(name) for name in _DS_DOCTYPES],
        "relationships": get_schema_relationships(),
    }


def _summarise(doctype):
    total = frappe.db.count(doctype)
    entry = {"doctype": doctype, "count": total, "recent": [], "statuses": {}}

    title_field = _TITLE_FIELD.get(doctype)
    if title_field and total:
        entry["recent"] = [
            row.get(title_field)
            for row in frappe.get_all(
                doctype, fields=[title_field], order_by="modified desc", limit=3
            )
        ]

    if doctype in _STATUS_DOCTYPES and total:
        for row in frappe.get_all(doctype, fields=["status"]):
            key = row.get("status") or "Unset"
            entry["statuses"][key] = entry["statuses"].get(key, 0) + 1
    return entry


@frappe.whitelist()
def get_schema_relationships():
    """Read the real Link/Table edges between DS DocTypes from their schema files.

    Read from the shipped JSON rather than frappe.get_meta so the graph is the
    schema as committed, and so this stays testable without a live site.
    """
    doctype_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "dashboard_studio",
        "doctype",
    )
    return relationships_from_schema_dir(doctype_dir)


def relationships_from_schema_dir(doctype_dir):
    """Pure helper: DS-to-DS Link/Table edges found in a doctype directory."""
    edges = []
    for folder in sorted(os.listdir(doctype_dir)):
        if not folder.startswith("ds_"):
            continue
        path = os.path.join(doctype_dir, folder, folder + ".json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as handle:
            schema = json.load(handle)
        for field in schema.get("fields", []):
            target = field.get("options") or ""
            if field.get("fieldtype") not in ("Link", "Table") or not target.startswith("DS "):
                continue
            edges.append(
                {
                    "source": schema["name"],
                    "target": target,
                    "fieldname": field["fieldname"],
                    # A Table field is a child relationship (one-to-many); a Link
                    # points at one parent record.
                    "kind": "child" if field["fieldtype"] == "Table" else "link",
                    "self_reference": target == schema["name"],
                }
            )
    return edges


@frappe.whitelist()
def get_field_catalogue():
    """Which fields each DS Metric is allowed to reference.

    This is the real safe-field concept in this app: allowed_fields is
    block-by-default, so a metric with none cannot execute at all. Field types
    and any notion of "restricted" fields are deliberately not reported — see the
    module docstring.
    """
    frappe.only_for(DS_READ_ROLES)
    metrics = frappe.get_all(
        "DS Metric",
        fields=["name", "metric_name", "status", "source_doctype", "allowed_fields"],
        order_by="metric_name asc",
    )
    catalogue = []
    for metric in metrics:
        fields = _split_allowed(metric.get("allowed_fields"))
        catalogue.append(
            {
                "metric": metric.get("name"),
                "metric_name": metric.get("metric_name"),
                "status": metric.get("status"),
                "source_doctype": metric.get("source_doctype"),
                "fields": fields,
                # No allowlist means the engine refuses to run it — worth
                # surfacing here rather than only at execution time.
                "executable": bool(fields),
            }
        )
    return catalogue


def _split_allowed(value):
    if not value:
        return []
    parts = str(value).replace(",", "\n").split("\n")
    return [part.strip() for part in parts if part.strip()]
