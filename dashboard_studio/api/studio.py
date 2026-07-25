import json

import frappe

# Two-level access model (System Manager always allowed as superuser).
DS_READ_ROLES = ("Dashboard Studio Editor", "Dashboard Studio Viewer", "System Manager")
DS_WRITE_ROLES = ("Dashboard Studio Editor", "System Manager")

# Fields the visual editor is allowed to write back to a DS Chart. Layout plus
# the handful of display properties the diagram editor exposes — never metric
# logic or links, which belong to the metric layer.
_EDITABLE_CHART_FIELDS = {
    "chart_title",
    "chart_type",
    "description",
    "metric",
    "pos_x",
    "pos_y",
    "width",
    "height",
    "drill_down_enabled",
}

# The only keys a DS Chart Filter row may carry when written from the editor.
_FILTER_ROW_FIELDS = ("fieldname", "operator", "value", "filter_type")

# The only keys a DS Canvas Node row may carry when written from the Mapping view.
_CANVAS_NODE_FIELDS = ("node_id", "node_type", "pos_x", "pos_y")

# DS Data Mapping fields the Mapping view may write. The natural key
# (data_source, external_table, external_field) is set separately, never patched.
_MAPPING_VALUE_FIELDS = ("target_doctype", "target_field", "mapping_status")


@frappe.whitelist()
def get_studio_dashboard(dashboard: str):
    """Return a DS Dashboard and its DS Chart records for the visual editor."""
    frappe.only_for(DS_READ_ROLES)
    doc = frappe.get_doc("DS Dashboard", dashboard)
    charts = frappe.get_all(
        "DS Chart",
        filters={"dashboard": dashboard},
        fields=[
            "name", "chart_title", "chart_type", "metric", "section",
            "pos_x", "pos_y", "width", "height", "description", "drill_down_enabled",
        ],
        order_by="pos_y asc, pos_x asc",
    )
    # Attach child filter rows (get_all does not return child tables).
    if charts:
        rows = frappe.get_all(
            "DS Chart Filter",
            filters={"parent": ["in", [c["name"] for c in charts]]},
            fields=["parent", "fieldname", "operator", "value", "filter_type"],
            order_by="idx asc",
        )
        by_parent = {}
        for row in rows:
            by_parent.setdefault(row.pop("parent"), []).append(row)
        for c in charts:
            c["chart_filters"] = by_parent.get(c["name"], [])
    return {"dashboard": doc.as_dict(), "charts": charts}


@frappe.whitelist()
def list_ds_metrics():
    """Metrics the editor may point a chart at (read-only).

    Restricted to what the engine can actually execute today: Approved, and
    calculation_type Count. Offering a Sum/Average metric would let someone
    build a chart that can only fail at render time.
    """
    frappe.only_for(DS_READ_ROLES)
    return frappe.get_all(
        "DS Metric",
        filters={"status": "Approved", "calculation_type": "Count"},
        fields=["name", "metric_name", "calculation_type", "source_doctype"],
        order_by="metric_name asc",
    )


@frappe.whitelist()
def get_migration_project(project: str):
    """Return a DS Migration Project with the mappings and canvas layout it needs.

    Mappings are resolved through the project's data_source, not owned by the
    project — the same mapping is shared by every project on that source (see
    docs/MIGRATION_PROJECT_LIFECYCLE.md). Canvas node positions are per-project.
    """
    frappe.only_for(DS_READ_ROLES)
    doc = frappe.get_doc("DS Migration Project", project)

    mappings = []
    if doc.data_source:
        mappings = frappe.get_all(
            "DS Data Mapping",
            filters={"data_source": doc.data_source},
            fields=[
                "name", "external_table", "external_field", "target_doctype",
                "target_field", "mapping_status", "confidence_score",
            ],
            order_by="external_table asc",
        )

    return {
        "project": doc.as_dict(),
        "mappings": mappings,
        "canvas_nodes": [
            {key: row.get(key) for key in _CANVAS_NODE_FIELDS}
            for row in (doc.get("canvas_nodes") or [])
        ],
    }


@frappe.whitelist()
def save_migration_mapping_set(project: str, mappings=None, canvas_nodes=None, source_queries=None):
    """Persist the Mapping view's one save action: mappings + canvas layout.

    Mappings are upserted against the natural key
    (data_source, external_table, external_field). Only table-level mappings
    exist today — the view sends no external_field — so field-level behaviour is
    deliberately not invented here.

    Canvas nodes are replaced wholesale from sanitized copies (the client always
    sends the full set), the same pattern save_chart uses for child rows.

    Analyzed SQL is APPENDED rather than replaced — it is evidence of what was
    examined, especially for queries the parser routed to manual review, so it
    accumulates instead of being overwritten. Identical SQL is not recorded twice.

    Performs the one automatic lifecycle transition: Not Started -> Mapping on
    the first successful save. Every later transition is a manual user action.
    """
    frappe.only_for(DS_WRITE_ROLES)
    mappings = _as_row_list(mappings, "mappings")
    canvas_nodes = _as_row_list(canvas_nodes, "canvas_nodes")

    doc = frappe.get_doc("DS Migration Project", project)
    if not doc.data_source:
        frappe.throw("Set a Data Source on this migration project before saving mappings.")

    saved = 0
    for row in mappings:
        external_table = str(row.get("external_table") or "").strip()
        if not external_table:
            continue
        external_field = str(row.get("external_field") or "").strip()
        values = {key: row.get(key) for key in _MAPPING_VALUE_FIELDS}
        values["mapping_status"] = values.get("mapping_status") or "Suggested"

        existing = frappe.db.get_value(
            "DS Data Mapping",
            {
                "data_source": doc.data_source,
                "external_table": external_table,
                # A blank Data field may be stored as NULL or "" depending on how
                # the row was created; SQL's `= ''` would not match NULL, which
                # would duplicate the row instead of updating it.
                "external_field": ["in", ["", None]] if not external_field else external_field,
            },
        )
        if existing:
            mapping_doc = frappe.get_doc("DS Data Mapping", existing)
            for key, value in values.items():
                mapping_doc.set(key, value)
            mapping_doc.save()
        else:
            frappe.get_doc(
                dict(
                    doctype="DS Data Mapping",
                    data_source=doc.data_source,
                    external_table=external_table,
                    external_field=external_field,
                    **values,
                )
            ).insert()
        saved += 1

    doc.set(
        "canvas_nodes",
        [
            {key: row.get(key) for key in _CANVAS_NODE_FIELDS}
            for row in canvas_nodes
            if str(row.get("node_id") or "").strip()
        ],
    )

    recorded = _append_source_queries(doc, _as_row_list(source_queries, "source_queries"))

    if saved and doc.status == "Not Started":
        doc.status = "Mapping"
    doc.save()

    return {"saved_mappings": saved, "recorded_queries": recorded, "status": doc.status}


def _append_source_queries(doc, rows):
    """Append analyzed SQL as evidence, skipping any already on record."""
    existing = doc.get("source_queries") or []
    seen = {(row.get("source_sql") or "").strip() for row in existing}
    added = 0
    for row in rows:
        sql = str(row.get("source_sql") or "").strip()
        if not sql or sql in seen:
            continue
        seen.add(sql)
        reasons = row.get("reasons")
        doc.append(
            "source_queries",
            {
                "source_sql": sql,
                "supported": 1 if row.get("supported") else 0,
                # Reasons arrive as a list from the analyzer; store them readable.
                "reasons": "; ".join(reasons) if isinstance(reasons, list) else (reasons or ""),
            },
        )
        added += 1
    return added


def _as_row_list(value, label):
    """Accept a JSON string (from frappe.call) or a list; keep only dict rows."""
    if isinstance(value, str):
        value = json.loads(value)
    if value is None:
        return []
    if not isinstance(value, list):
        frappe.throw(f"{label} must be a JSON array")
    return [row for row in value if isinstance(row, dict)]


@frappe.whitelist()
def save_chart(chart: str, patch):
    """Persist an editor patch to one DS Chart. Only allowlisted fields are written.

    ``patch`` is a JSON object (string or dict) of field -> value. Unknown fields
    are ignored rather than trusted.
    """
    frappe.only_for(DS_WRITE_ROLES)
    if isinstance(patch, str):
        patch = json.loads(patch)
    if not isinstance(patch, dict):
        frappe.throw("patch must be a JSON object")

    doc = frappe.get_doc("DS Chart", chart)
    for key, value in patch.items():
        if key == "chart_filters" and isinstance(value, list):
            # Child rows are rebuilt from sanitized copies — only the four
            # filter fields survive; parent/doctype/etc. from the client do not.
            doc.set(
                "chart_filters",
                [
                    {k: row.get(k) for k in _FILTER_ROW_FIELDS}
                    for row in value
                    if isinstance(row, dict)
                ],
            )
        elif key in _EDITABLE_CHART_FIELDS:
            doc.set(key, value)
    doc.save()
    return doc.as_dict()
