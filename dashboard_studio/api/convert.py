"""Convert a pasted SQL query into a real Insights v3 query.

Instead of a block of text nobody can click, Insights gets an Operations list —
Select Source, Join Table, Filter Rows, Group & Summarize — which is what makes
a migrated report maintainable afterwards.

**Nothing checks that a converted query counts the same rows.** ADR-007 made
that a person's job, behind an ``[UNVERIFIED]`` marker and a number comparison;
ADR-008 removed both, on request. What is left standing in their place is the
refusal table in `integrations/metabase/sql_ops.py`: anything this cannot
translate with certainty refuses BY NAME and writes nothing, because a
translation that disagrees with the original does not fail, it returns a
different number — `docs/SOPHIA_FAULT_PATTERN.md`, *"they do not fail, they
disagree."* Those refusals are now the only thing paying for that risk, so do
not soften one to make a query go through.

Studio never executes anything, here or anywhere else — it reads DocType
metadata and writes an Insights record, and that is all.
"""

import frappe

from dashboard_studio.api.insights import (
    CHART_DOCTYPE,
    QUERY_DOCTYPE,
    SITE_DB,
    _require_insights,
    _resolve_workbook,
    clamp_title,
)
from dashboard_studio.integrations.metabase.chart_config import chart_config_from_card
from dashboard_studio.integrations.metabase.parser import analyze_sql
from dashboard_studio.integrations.metabase.sql_ops import (
    columns_from_meta,
    operations_from_sql,
)
from dashboard_studio.roles import DS_WRITE_ROLES


def _table_columns(doctype):
    """``{column_name: data_type}`` for a DocType, from Frappe's own metadata.

    The types SQL text cannot supply. Insights needs a data_type on every
    grouping and measure, and this site already knows what every column is —
    which is why pasted SQL can reach structured output without anybody
    guessing, and why a join's column names can be checked rather than trusted.

    The table's REAL column list comes from the database, NEVER from the DocType.
    A DocType's fields and its table's columns drift apart — Frappe's
    `_user_tags`/`_comments`/`_assign`/`_liked_by` are optional and not on every
    table, and a field can outlive the column it used to have. Both directions
    have already shipped a query that converted cleanly and then failed on open:
    "Column '_comments' is not found in table", then "Column 'corrective_action'
    is not found in table".

    So there is NO fallback to DocType fields. If the schema cannot be read the
    conversion refuses, because a guessed column list is precisely what produces
    a query that fails the moment somebody opens it.
    """
    if not frappe.db.exists("DocType", doctype):
        frappe.throw(
            f"There is no DocType called '{doctype}' on this site, so the columns "
            "of that table cannot be typed. Check the table name in the query."
        )
    meta = frappe.get_meta(doctype)
    fields = [(f.fieldname, f.fieldtype) for f in meta.fields]
    # Two APIs, because the name has moved between Frappe versions and losing the
    # schema read must not quietly downgrade to guessing.
    for read, argument in ((getattr(frappe.db, "get_table_columns", None), doctype),
                           (getattr(frappe.db, "get_db_table_columns", None), "tab" + doctype)):
        if not read:
            continue
        try:
            valid = read(argument)
        except Exception:
            continue
        if valid:
            return columns_from_meta(fields, list(valid))
    frappe.throw(
        f"The columns of '{doctype}' could not be read from the database on this "
        "site, so this query cannot be converted. Its DocType fields are not a "
        "safe substitute — they drift from the real table, and a query built "
        "from them fails the moment it is opened in Insights."
    )


@frappe.whitelist()
def convert_sql(sql: str, title: str = None, workbook: str = None, card=None):
    """Translate pasted SQL into Insights operations and file it in Insights.

    Refuses outright rather than returning reasons, because this writes: a
    partial conversion is a query that answers a different question.

    `card` is the sidecar `metabase_export_sql.py` wrote beside the exported
    `.sql` — the source card's `series_settings`, its `display` and its id. Given
    one, the chart is built with each series' type and label as Metabase had
    them; given nothing, or anything ambiguous, only the query is created and
    the result says why. **Studio makes no network call to get it**: the sidecar
    is exported in the same pass as the SQL, which is what guarantees the two
    correspond. Nothing here fetches, and nothing here may start.
    """
    frappe.only_for(DS_WRITE_ROLES)
    _require_insights()

    if not isinstance(sql, str) or not sql.strip():
        frappe.throw("Paste a SQL query first.")

    analysis = analyze_sql(sql)
    doctypes = [d for d in (analysis.get("doctypes") or []) if d]
    source = analysis.get("source_doctype") or (doctypes[0] if doctypes else None)
    # Types for EVERY table the query touches — a join needs both sides typed,
    # and both join columns checked against real DocType metadata. Only fetched
    # once the analysis itself is clean, so a query refused for a subquery says
    # so rather than "there is no DocType called '(SELECT'".
    columns = {d: _table_columns(d) for d in doctypes} if analysis.get("supported") else {}
    result = operations_from_sql(analysis, columns)
    if not result["supported"]:
        frappe.throw(
            "This query cannot be converted to operations: "
            + "; ".join(result["reasons"])
            + ". You can still build it in Insights by hand."
        )

    workbook = _resolve_workbook(workbook)
    name = clamp_title((title or "").strip() or f"{source} query")

    doc = frappe.get_doc({
        "doctype": QUERY_DOCTYPE,
        "workbook": workbook,
        "title": name,
        "is_builder_query": 1,
        "use_live_connection": 1,
        "operations": frappe.as_json(result["operations"]),
    }).insert()

    chart, chart_reason = _chart_from(card, result["operations"], workbook, doc.name, name)

    return {
        "name": doc.name,
        "title": name,
        "workbook": workbook,
        "data_source": SITE_DB,
        "operations": result["operations"],
        "chart": chart,
        "chart_not_built": chart_reason,
        "insights_url": f"/insights/workbook/{workbook}/query/{doc.name}",
    }


def _chart_from(card, operations, workbook, query, title):
    """``(chart, reason)`` — an Insights chart from the card's own settings.

    Never raises and never blocks the conversion: the query is already written
    by the time this runs, and a chart that could not be built is an ordinary
    outcome that the result reports. `chart_config_from_card` carries the
    argument for why this degrades where the rest of the converter refuses.
    """
    if not card:
        return None, ("no Metabase chart settings were supplied, so the chart "
                      "is Insights' default — check it by hand")
    if isinstance(card, str):
        # Frappe hands a whitelisted argument through as text when the caller
        # sent JSON. Unreadable text is not a chart to guess at.
        try:
            card = frappe.parse_json(card)
        except Exception:
            return None, "the Metabase chart settings could not be read"
    config, chart_type, reason = chart_config_from_card(card, operations)
    if not config:
        return None, reason
    chart = frappe.get_doc({
        "doctype": CHART_DOCTYPE,
        "workbook": workbook,
        "query": query,
        "title": clamp_title(title),
        "chart_type": chart_type,
        "config": frappe.as_json(config),
    }).insert()
    return {"name": chart.name, "chart_type": chart_type,
            "series": [{"name": s.get("name"), "type": s.get("type"),
                        "align": s.get("align"),
                        "measure_name": (s.get("measure") or {}).get("measure_name")}
                       for s in config["y_axis"]["series"]],
            "insights_url": f"/insights/workbook/{workbook}/chart/{chart.name}"}, None
