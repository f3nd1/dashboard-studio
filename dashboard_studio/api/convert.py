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
    QUERY_DOCTYPE,
    SITE_DB,
    _require_insights,
    _resolve_workbook,
    clamp_title,
)
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

    The table's REAL column list comes from the database, not from the DocType:
    Frappe's `_user_tags`, `_comments`, `_assign` and `_liked_by` are optional
    and are NOT on every table. Assuming them produced a query that converted
    here and then failed in Insights with "Column '_comments' is not found in
    table" — the schema is the only thing that knows, so the schema is asked.
    """
    if not frappe.db.exists("DocType", doctype):
        frappe.throw(
            f"There is no DocType called '{doctype}' on this site, so the columns "
            "of that table cannot be typed. Check the table name in the query."
        )
    meta = frappe.get_meta(doctype)
    fields = [(f.fieldname, f.fieldtype) for f in meta.fields]
    # getattr rather than a version check: older Frappe has no get_table_columns,
    # and falling back to the unconditional columns is the safe direction.
    read_columns = getattr(frappe.db, "get_table_columns", None)
    if not read_columns:
        return columns_from_meta(fields)
    try:
        return columns_from_meta(fields, read_columns(doctype))
    except Exception:
        # A DocType with no table of its own — a Single, most likely. Named,
        # rather than surfacing a raw traceback from the schema layer.
        frappe.throw(
            f"'{doctype}' has no table on this site, so its columns cannot be "
            "read. A Single DocType has no rows to query."
        )


@frappe.whitelist()
def convert_sql(sql: str, title: str = None, workbook: str = None):
    """Translate pasted SQL into Insights operations and file it in Insights.

    Refuses outright rather than returning reasons, because this writes: a
    partial conversion is a query that answers a different question.
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

    return {
        "name": doc.name,
        "title": name,
        "workbook": workbook,
        "data_source": SITE_DB,
        "operations": result["operations"],
        "insights_url": f"/insights/workbook/{workbook}/query/{doc.name}",
    }
