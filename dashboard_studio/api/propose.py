"""A plain-English question -> a PROPOSED Insights setup. Creates nothing.

**There is no write path in this module.** Not a flag defaulting to false — no
call that inserts a record, anywhere in the file, and a test that greps for one.
Creation stays where it already was, in `convert.convert_sql`, which the user
reaches by pressing a button after reading the proposal.

**What the safety argument is, and what it is NOT.** The existing validation is
REFERENTIAL: it checks a column exists on the real table and is the right kind
of thing. It cannot check the model picked the column you meant. `sales_income`,
`net_income` and `commission_amount` all exist and are all numeric; so do
`posting_date`, `transaction_date` and `creation`. A confidently wrong proposal
passes every check this has. Pasted SQL carried a human's choices out of
Metabase; a proposal carries a model's.

So the gate is the READ-BACK, and it only works if the summary describes what
will actually run. That is why **the model's own prose is never returned from
here** — only the SQL it wrote and the operations that SQL translated into. The
summary is composed in `studio_core.js` from the operations. If the model wrote
both, its summary would describe its intention while the operations did
something else, and reading it would check nothing.

**Egress.** A question somebody typed, DocType names, and column names with
their types. Never a row, never a sample value — see the note in
`integrations/llm/question.py`, which cannot reach a database at all.
"""

from __future__ import annotations

import frappe

from dashboard_studio.api.convert import _table_columns
from dashboard_studio.integrations.llm.question import (
    API_URL,
    API_VERSION,
    doctypes_from_response,
    pick_doctypes_request,
    sql_from_response,
    write_sql_request,
)
from dashboard_studio.integrations.metabase.parser import analyze_sql
from dashboard_studio.integrations.metabase.sql_ops import (
    MEASURE_DATA_TYPES,
    operations_from_sql,
    rows_multiplied_by,
)
from dashboard_studio.roles import DS_WRITE_ROLES

# What the validation strip must say alongside its green tick. A strip that
# reports "checked" without saying what it did NOT check implies an assurance
# nobody can give, and that is worse than no strip: it invites the one thing
# this feature cannot survive, which is somebody not reading the proposal.
NOT_CHECKED = (
    "Not checked: whether these are the columns you meant. Existence and type "
    "are all that can be verified here — a different column of the right type "
    "returns a different number and passes every check above."
)


def _api_key(api_key: str = None) -> str:
    """The request's key first, then site_config. Never repeated back.

    A key typed into the page is used for THAT call and nothing else: it is not
    written to a record, a file, a log or a cache, and it does not outlive the
    request. Falling back to `llm_api_key` in site_config keeps the arrangement
    a site can already have — same handling as the Metabase key.

    The failure message names the field and the setting, never the value: a
    thrown message travels to the browser in `_server_messages`.
    """
    key = (api_key or "").strip() or frappe.conf.get("llm_api_key")
    if not key:
        frappe.throw(
            "No LLM API key. Paste one into the key field on the Ask a question "
            "tab — it is kept in the page for this browser session only and is "
            "never saved — or set `llm_api_key` in site_config.json for the "
            "whole site. Pasting SQL does not need a key."
        )
    return key


@frappe.whitelist()
def llm_key_is_configured():
    """Whether the SITE has a key, so the page can hide the field when it does.

    Returns a boolean and nothing else. It must never return the key, or any
    part of it, or its length.
    """
    frappe.only_for(DS_WRITE_ROLES)
    return {"configured": bool(frappe.conf.get("llm_api_key"))}


def _ask(payload: dict, api_key: str = None) -> dict:
    """The one HTTP call in this app, and the only one that leaves the server.

    Structural, in the shape `metabase_export_sql.py` uses: exactly one
    `requests.post` in the file, its URL checked at the call site, so a second
    endpoint cannot be added without the check being edited too.
    """
    import requests

    if API_URL != "https://api.anthropic.com/v1/messages":
        frappe.throw("Refusing to call anything but the messages endpoint.")
    response = requests.post(
        API_URL,
        headers={"x-api-key": _api_key(api_key), "anthropic-version": API_VERSION,
                 "content-type": "application/json"},
        json=payload,
        timeout=60,
    )
    if response.status_code != 200:
        # The body may quote the request; the key is a header and is not in it,
        # but the status alone is what gets reported rather than risking that.
        frappe.throw(f"The LLM provider returned HTTP {response.status_code}.")
    return response.json()


def _checked(operations, columns) -> list[str]:
    """The columns the validator actually verified, said by name.

    Read out of `columns`, which IS what the checks ran against, rather than
    re-derived from the operations — a second derivation could agree with the
    proposal and disagree with what was checked.
    """
    out = []
    for doctype in sorted(columns):
        for column in sorted(columns[doctype] or {}):
            data_type = columns[doctype][column]
            if column in _referenced_names(operations):
                numeric = " (numeric)" if data_type in MEASURE_DATA_TYPES else ""
                out.append(f"{column}{numeric}")
    return out


def _referenced_names(operations) -> set:
    """Every column name that appears anywhere in the operations."""
    names = set()

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "column" and node.get("column_name"):
                names.add(str(node["column_name"]))
            for key in ("column_name", "measure_name", "dimension_name"):
                if node.get(key):
                    names.add(str(node[key]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(operations)
    return names


@frappe.whitelist()
def propose_from_question(question: str, api_key: str = None):
    """Propose an Insights setup for a question. **Creates nothing.**

    Returns the SQL the model wrote, the operations it translated into, what the
    validator verified, what it did not, and any join that multiplies rows. The
    caller renders the summary from the operations.

    `api_key`, when the page supplies one, is used for this request's outbound
    calls and then goes out of scope. It is never stored, logged or echoed.
    """
    frappe.only_for(DS_WRITE_ROLES)
    question = (question or "").strip()
    if not question:
        frappe.throw("Type a question first.")

    names = frappe.get_all("DocType", pluck="name")
    chosen = doctypes_from_response(
        _ask(pick_doctypes_request(question, names), api_key), names)
    if not chosen:
        return {"supported": False, "sql": "", "operations": [],
                "reasons": ["No table on this site looks like it answers that. "
                            "Try naming the record type you mean."],
                "checked": [], "not_checked": NOT_CHECKED, "multiplied": []}

    columns = {doctype: _table_columns(doctype) for doctype in chosen}
    sql, refusal = sql_from_response(
        _ask(write_sql_request(question, columns), api_key))
    if refusal:
        return {"supported": False, "sql": "", "operations": [], "reasons": [refusal],
                "checked": [], "not_checked": NOT_CHECKED, "multiplied": []}

    analysis = analyze_sql(sql)
    if not analysis["supported"]:
        return {"supported": False, "sql": sql, "operations": [],
                "reasons": analysis["reasons"], "checked": [],
                "not_checked": NOT_CHECKED, "multiplied": []}

    # The DocTypes the SQL actually reads may not be the ones it was given —
    # so they are typed from the query, exactly as the paste path does it.
    columns = {doctype: _table_columns(doctype)
               for doctype in (analysis.get("doctypes") or [])}
    result = operations_from_sql(analysis, columns)
    if not result["supported"]:
        return {"supported": False, "sql": sql, "operations": [],
                "reasons": result["reasons"], "checked": [],
                "not_checked": NOT_CHECKED, "multiplied": []}

    children = {doctype for doctype in columns
                if getattr(frappe.get_meta(doctype), "istable", 0)}
    return {
        "supported": True,
        "sql": sql,
        "operations": result["operations"],
        "reasons": [],
        "checked": _checked(result["operations"], columns),
        "not_checked": NOT_CHECKED,
        "multiplied": rows_multiplied_by(result["operations"], children),
    }
