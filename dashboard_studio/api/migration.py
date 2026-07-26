import frappe

from dashboard_studio.api.studio import DS_READ_ROLES
from dashboard_studio.integrations.metabase.parser import analyze_sql


@frappe.whitelist()
def supported_features():
    frappe.only_for("System Manager")
    return {
        "implemented": [
            "paste_sql",
            "source_mapping",
            "result_comparison",   # the Validation Centre — api/validation.py
            "metric_generation",   # confirmed mapping -> Draft DS Metric
        ],
        "planned": [
            "metabase_dashboard_inventory",
            "saved_question_resolution",
            "chart_generation",
            "publish_to_sophia",
        ],
        "status": "partial",
    }


@frappe.whitelist()
def analyze_migration_sql(sql: str):
    """Parse pasted Metabase SQL into a structured description plus suggested mappings.

    Read-only: this parses the string the caller supplied and writes nothing.
    Nothing is executed — the analyzer never runs the SQL.

    When the query is outside what can be safely translated, ``supported`` is
    False and ``reasons`` explains why; suggestions are withheld in that case so
    an unsupported query cannot quietly seed mappings (flag-don't-guess).
    """
    frappe.only_for(DS_READ_ROLES)
    if not isinstance(sql, str) or not sql.strip():
        frappe.throw("Paste a SQL query to analyze.")

    analysis = analyze_sql(sql)
    return {
        "analysis": analysis,
        "suggested_mappings": _suggest_mappings(analysis) if analysis["supported"] else [],
    }


def _suggest_mappings(analysis):
    """Identity suggestions: `tab<DocType>` -> <DocType>, which is what the
    table-name mapper already resolves. Left as Suggested for a human to confirm;
    confidence_score is deliberately unset — there is no honest basis to score a
    rename the parser did deterministically.
    """
    return [
        {
            "external_table": "tab" + doctype,
            "target_doctype": doctype,
            "mapping_status": "Suggested",
        }
        for doctype in analysis.get("doctypes") or []
    ]
