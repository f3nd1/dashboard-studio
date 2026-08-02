import json

import frappe

from dashboard_studio.edutrust import SUBCRITERIA, describe

# Access model (System Manager always allowed as superuser).
#
# QA Approver can READ everything — approving work you cannot see is meaningless
# — but is deliberately NOT in the write set: it approves and publishes, it does
# not edit. That separation is the reason the role exists.
DS_READ_ROLES = (
    "Dashboard Studio Editor",
    "Dashboard Studio Viewer",
    "Dashboard Studio QA Approver",
    "System Manager",
)
DS_WRITE_ROLES = ("Dashboard Studio Editor", "System Manager")

# Fields the visual editor is allowed to write back to a DS Chart. Layout plus
# the handful of display properties the diagram editor exposes — never metric
# logic or links, which belong to the metric layer.
_EDITABLE_CHART_FIELDS = {
    "chart_title",
    "chart_type",
    "description",
    "metric",
    "section",
    "pos_x",
    "pos_y",
    "width",
    "height",
    "drill_down_enabled",
    "sort_order",
}

# The only keys a DS Chart Filter row may carry when written from the editor.
_FILTER_ROW_FIELDS = ("fieldname", "operator", "value", "filter_type")

# The only keys a DS Canvas Node row may carry when written from the Mapping view.
_CANVAS_NODE_FIELDS = ("node_id", "node_type", "pos_x", "pos_y")

# DS Data Mapping fields the Mapping view may write. The natural key
# (data_source, external_table, external_field) is set separately, never patched.
_MAPPING_VALUE_FIELDS = ("target_doctype", "target_field", "mapping_status")


@frappe.whitelist()
def list_dashboards():
    """Dashboards the editor can open, most recently changed first.

    This is what lets the editor open on real records instead of mock data when
    it is loaded without a dashboard in the route.
    """
    frappe.only_for(DS_READ_ROLES)
    return frappe.get_all(
        "DS Dashboard",
        fields=["name", "dashboard_title", "status", "modified"],
        order_by="modified desc",
    )


@frappe.whitelist()
def create_dashboard(dashboard_title: str):
    """Create an empty Draft dashboard and return enough for the editor to open it."""
    frappe.only_for(DS_WRITE_ROLES)
    title = (dashboard_title or "").strip()
    if not title:
        frappe.throw("A dashboard needs a title.")
    doc = frappe.get_doc(
        {"doctype": "DS Dashboard", "dashboard_title": title, "status": "Draft"}
    ).insert()
    return {"name": doc.name, "dashboard_title": title, "status": "Draft"}


@frappe.whitelist()
def set_dashboard_scope(dashboard: str, subcriterion: str = None):
    """Set (or clear) a dashboard's EduTrust subcriterion.

    Narrow on purpose: scope is the only DS Dashboard field the Builder writes,
    and a general patch endpoint would expose status and published_on, which the
    governance workflow owns.

    Only the code is stored. Titles are resolved for display, so a retitle on the
    receiving platform never strands records against stale text.
    """
    frappe.only_for(DS_WRITE_ROLES)
    code = (subcriterion or "").strip()
    if code and code not in SUBCRITERIA:
        frappe.throw(f"Unknown EduTrust subcriterion: {code}")
    frappe.db.set_value("DS Dashboard", dashboard, "subcriterion", code)
    return {"dashboard": dashboard, "subcriterion": code, "scope": describe(code)}


@frappe.whitelist()
def list_subcriteria():
    """The EduTrust codes a dashboard may be scoped to, with their titles."""
    frappe.only_for(DS_READ_ROLES)
    return [describe(code) for code in sorted(SUBCRITERIA)]


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
            "sort_order",
        ],
        order_by="pos_y asc, pos_x asc",
    )
    # Why the linked metric's status travels with the chart: the Builder renders
    # a card by CALLING run_ds_metric, and the engine refuses a metric that is
    # not Approved. That refusal is correct, but as a bare exception it reaches
    # the browser as Frappe's raw traceback dialog. Knowing the status here means
    # the card can say so without making a call that is certain to fail — which
    # is the only thing that stops the dialog, since a frontend catch runs after
    # Frappe has already raised it.
    #
    # Read-only, and NOT a relaxation: run_ds_metric still refuses.
    if charts:
        linked = sorted({c["metric"] for c in charts if c.get("metric")})
        known = {
            m["name"]: m
            for m in (frappe.get_all(
                "DS Metric",
                filters={"name": ["in", linked]},
                fields=["name", "status", "calculation_type"],
            ) if linked else [])
        }
        for c in charts:
            found = known.get(c.get("metric")) if c.get("metric") else None
            c["metric_status"] = found["status"] if found else None
            c["metric_calculation"] = found["calculation_type"] if found else None
            # A chart can outlive the metric it points at: Frappe does not clear
            # a Link when the target is deleted if the delete was forced.
            c["metric_missing"] = bool(c.get("metric") and not found)

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

    sections = frappe.get_all(
        "DS Dashboard Section",
        filters={"dashboard": dashboard},
        fields=["name", "section_title", "sort_order", "is_collapsed_default"],
        order_by="sort_order asc, section_title asc",
    )
    # Deferred import: governance imports DS_READ_ROLES from this module.
    from dashboard_studio.api.governance import publish_readiness

    # Resolved here, not stored: the record holds only the code.
    return {
        "dashboard": doc.as_dict(),
        "scope": describe(doc.get("subcriterion") or ""),
        "charts": charts,
        "sections": sections,
        # The publish rules, evaluated for display. Same function the gate throws
        # on — see publish_readiness's docstring for why there is only one.
        "readiness": publish_readiness(dashboard),
    }


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
        # group_by_field/value_field are what the properties panel shows as the
        # metric's dimension and measure. Read here rather than through a new
        # endpoint — this list is already fetched once per session.
        fields=[
            "name", "metric_name", "calculation_type", "source_doctype",
            "group_by_field", "value_field",
        ],
        order_by="metric_name asc",
    )


# The only DS Dashboard Section fields the editor may write.
_EDITABLE_SECTION_FIELDS = ("section_title", "is_collapsed_default")


@frappe.whitelist()
def create_section(dashboard: str, section_title: str):
    """Add a section to a dashboard, ordered after the existing ones."""
    frappe.only_for(DS_WRITE_ROLES)
    title = (section_title or "").strip()
    if not title:
        frappe.throw("Section title is required.")

    orders = [
        row.sort_order or 0
        for row in frappe.get_all(
            "DS Dashboard Section", filters={"dashboard": dashboard}, fields=["sort_order"]
        )
    ]
    doc = frappe.get_doc(
        {
            "doctype": "DS Dashboard Section",
            "dashboard": dashboard,
            "section_title": title,
            "sort_order": (max(orders) if orders else 0) + 1,
        }
    ).insert()
    return doc.as_dict()


@frappe.whitelist()
def update_section(section: str, patch):
    """Rename a section or change its default collapsed state."""
    frappe.only_for(DS_WRITE_ROLES)
    if isinstance(patch, str):
        patch = json.loads(patch)
    if not isinstance(patch, dict):
        frappe.throw("patch must be a JSON object")

    doc = frappe.get_doc("DS Dashboard Section", section)
    for key, value in patch.items():
        if key not in _EDITABLE_SECTION_FIELDS:
            continue
        if key == "section_title":
            value = str(value or "").strip()
            if not value:
                frappe.throw("Section title cannot be empty.")
        doc.set(key, value)
    doc.save()
    return doc.as_dict()


@frappe.whitelist()
def reorder_sections(dashboard: str, order):
    """Reassign sort_order from a full ordered list of section names.

    Applied in one call rather than per-section so the ordering can never be
    left half-updated with duplicate positions.
    """
    frappe.only_for(DS_WRITE_ROLES)
    if isinstance(order, str):
        order = json.loads(order)
    if not isinstance(order, list):
        frappe.throw("order must be a JSON array of section names")

    owned = {
        row.name
        for row in frappe.get_all(
            "DS Dashboard Section", filters={"dashboard": dashboard}, fields=["name"]
        )
    }
    unknown = [name for name in order if name not in owned]
    if unknown:
        frappe.throw(f"Not sections of this dashboard: {', '.join(unknown)}")

    for position, name in enumerate(order, start=1):
        frappe.db.set_value("DS Dashboard Section", name, "sort_order", position)
    return {"reordered": len(order)}


@frappe.whitelist()
def delete_section(section: str):
    """Delete a section, keeping its charts.

    Charts are un-assigned first so they fall back to Ungrouped — deleting a
    grouping must never destroy the things it grouped.
    """
    frappe.only_for(DS_WRITE_ROLES)
    charts = frappe.get_all("DS Chart", filters={"section": section}, fields=["name"])
    for chart in charts:
        frappe.db.set_value("DS Chart", chart.name, "section", "")
    frappe.delete_doc("DS Dashboard Section", section)
    return {"deleted": section, "unassigned_charts": len(charts)}


@frappe.whitelist()
def list_migration_projects():
    """Migration projects and the data sources one can be created against.

    Both in one call because they fill one form: the Source Mapping workspace
    opened without ?project= has to offer "pick an existing one" and "make a new
    one" together, and two round trips for one panel is silly.

    A DS Migration Project is NOT a DS Dashboard — different record, different
    purpose — which is exactly the confusion this endpoint exists to end.
    """
    frappe.only_for(DS_READ_ROLES)
    return {
        "projects": frappe.get_all(
            "DS Migration Project",
            fields=["name", "project_name", "data_source", "status", "modified"],
            order_by="modified desc",
        ),
        "data_sources": frappe.get_all(
            "DS Data Source", fields=["name", "source_name"], order_by="source_name asc"
        ),
    }


@frappe.whitelist()
def create_migration_project(project_name: str, data_source: str):
    """Create a migration project from inside the workspace.

    ``data_source`` is REQUIRED — DS Migration Project.data_source is reqd, and
    save_migration_mapping_set refuses a project without one. It may name a
    DS Data Source that does not exist yet, in which case it is created.

    ponytail: creating the data source implicitly writes a second record. It is
    defensible only because a project cannot exist without one and a site may
    have none, so the alternative is sending someone to a different list view —
    the exact problem this endpoint removes. The response says which records were
    created, so nothing is silent. Split it into its own step if data sources
    ever grow fields worth filling in properly.
    """
    frappe.only_for(DS_WRITE_ROLES)
    title = (project_name or "").strip()
    source = (data_source or "").strip()
    if not title:
        frappe.throw("A migration project needs a name.")
    if not source:
        frappe.throw("A migration project needs a data source — it is where mappings are saved.")

    created_source = False
    if not frappe.db.exists("DS Data Source", source):
        frappe.get_doc({"doctype": "DS Data Source", "source_name": source, "is_active": 1}).insert()
        created_source = True

    doc = frappe.get_doc({
        "doctype": "DS Migration Project",
        "project_name": title,
        "data_source": source,
        "status": "Not Started",
    }).insert()
    return {
        "name": doc.name,
        "project_name": title,
        "data_source": source,
        "status": doc.status,
        "created_data_source": created_source,
    }


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

    metrics = _metrics_from_confirmed_mappings(doc, mappings)

    return {
        "saved_mappings": saved,
        "recorded_queries": recorded,
        "status": doc.status,
        "metrics": metrics,
    }


def _metrics_from_confirmed_mappings(doc, mappings):
    """Create the DS Metric each confirmed mapping's query already describes.

    Confirming a mapping is the moment someone says "this source table really is
    that DocType". Until then the analysis describes nothing anyone has agreed
    to, so nothing is written.

    Always Draft — see metric_builder for why a parser cannot approve a metric.
    The metric name is derived, and DS Metric is ``autoname: field:metric_name``,
    so re-analysing the same query resolves to the record that already exists
    instead of creating a second one.

    Returns one entry per source query, each either created/existing or skipped
    with the reason, because a silent skip here is a metric someone thinks they
    have.
    """
    from dashboard_studio.integrations.metabase.metric_builder import metric_from_analysis
    from dashboard_studio.integrations.metabase.parser import analyze_sql

    confirmed = {
        str(row.get("target_doctype") or "").strip()
        for row in mappings
        if row.get("mapping_status") == "Confirmed"
    }
    if not confirmed:
        return []

    out = []
    for row in doc.get("source_queries") or []:
        sql = (row.get("source_sql") or "").strip()
        if not sql:
            continue
        # Re-parsed here rather than trusting a structure posted by the client:
        # this decides what a metric measures, so it reads the SQL itself.
        analysis = analyze_sql(sql)
        fields, reason = metric_from_analysis(analysis)
        if not fields:
            out.append({"sql": sql, "skipped": reason})
            continue
        if fields["source_doctype"] not in confirmed:
            out.append({
                "sql": sql,
                "skipped": f"{fields['source_doctype']} has no confirmed mapping yet",
            })
            continue

        name = fields["metric_name"]
        if frappe.db.exists("DS Metric", name):
            out.append({"sql": sql, "metric": name, "created": False})
            continue
        frappe.get_doc(dict(fields, doctype="DS Metric")).insert()
        out.append({"sql": sql, "metric": name, "created": True})
    return out


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


def _chart_type_options():
    """Valid DS Chart types, read from the DocType so there is one source of truth."""
    field = frappe.get_meta("DS Chart").get_field("chart_type")
    return [line for line in (field.options or "").split("\n") if line]


def _next_free_row(dashboard: str):
    """First grid row below everything already on the dashboard."""
    bottom = 0
    for row in frappe.get_all(
        "DS Chart", filters={"dashboard": dashboard}, fields=["pos_y", "height"]
    ):
        bottom = max(bottom, (row.get("pos_y") or 0) + (row.get("height") or 1))
    return bottom


@frappe.whitelist()
def create_chart(
    dashboard: str, chart_type: str = "KPI Card", copy_from: str = None, metric: str = None
):
    """Add a chart to a dashboard, or duplicate one that is already on it.

    Both paths land the new card on the first free row rather than on top of an
    existing one, so nothing is ever hidden behind what was just created.

    ``copy_from`` carries the source chart's metric, description, layout size and
    filters over. It is restricted to the same dashboard: duplicating across
    dashboards would silently move a chart's metric into a different governance
    scope.

    ``metric`` links the new chart to a DS Metric on creation, which is what the
    Source Mapping workspace uses after generating one. Deliberately no status
    check: DS Chart.metric is a Link with no status constraint, a chart may be
    built before its metric is approved, and the engine still refuses to RUN an
    unapproved one. Adding a check here would be a second, weaker copy of the
    gate that already exists.
    """
    frappe.only_for(DS_WRITE_ROLES)
    source = frappe.get_doc("DS Chart", copy_from) if copy_from else None
    if source and source.dashboard != dashboard:
        frappe.throw("A chart can only be duplicated within its own dashboard.")

    resolved_type = source.chart_type if source else chart_type
    if resolved_type not in _chart_type_options():
        frappe.throw(f"Unknown chart type: {resolved_type}")

    doc = frappe.get_doc(
        {
            "doctype": "DS Chart",
            "dashboard": dashboard,
            "chart_type": resolved_type,
            "chart_title": (
                f"{source.chart_title} (copy)" if source else f"New {resolved_type}"
            ),
            "section": (source.section if source else None),
            "metric": (source.metric if source else (metric or None)),
            "description": (source.description if source else ""),
            "pos_x": 0,
            "pos_y": _next_free_row(dashboard),
            "width": (source.width if source else 4),
            "height": (source.height if source else 4),
            "chart_filters": (
                [
                    {k: row.get(k) for k in _FILTER_ROW_FIELDS}
                    for row in (source.get("chart_filters") or [])
                ]
                if source
                else []
            ),
        }
    ).insert()
    return doc.as_dict()


@frappe.whitelist()
def delete_chart(chart: str):
    """Remove one chart. Its metric is left alone — metrics outlive the charts
    that draw them, and may be shared with other dashboards."""
    frappe.only_for(DS_WRITE_ROLES)
    dashboard = frappe.db.get_value("DS Chart", chart, "dashboard")
    frappe.delete_doc("DS Chart", chart)
    return {"deleted": chart, "dashboard": dashboard}


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
