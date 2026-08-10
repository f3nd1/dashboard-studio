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
    MODEL,
    MODELS_URL,
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
            "No LLM API key. Paste one into the API key tab — it is kept in the "
            "page for this browser session only and is never saved — or set "
            "`llm_api_key` in site_config.json for the whole site. Pasting SQL "
            "does not need a key."
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


@frappe.whitelist()
def propose_tables(question: str, api_key: str = None, model: str = None):
    """Which DocTypes a question is about. **Proposes only; creates nothing.**

    This step existed already and was INVISIBLE, which is how a question about
    recruitment agents was answered from ERPNext's sales-commission tables:
    every column existed, every type checked, and the referential validator had
    nothing to object to. The choice of table is the one decision this
    converter can never verify, so it is the one decision a person has to make.

    Returns NAMES ONLY. No rationale from the model — a sentence explaining why
    it picked a table would describe its intention, and it is the choice, not
    the reasoning, that has to be checked. Same rule as the summary.
    """
    frappe.only_for(DS_WRITE_ROLES)
    question = (question or "").strip()
    if not question:
        frappe.throw("Type a question first.")
    model = _model(model)
    names = frappe.get_all("DocType", pluck="name")
    return {"doctypes": doctypes_from_response(
        _ask(pick_doctypes_request(question, names, model), api_key), names)}


@frappe.whitelist()
def list_models(api_key: str = None):
    """The models this key can see — ids only, for the Model field's picker.

    `{available, models, problem}` rather than a throw, because "no key yet" is
    an ordinary state of the page and not an error: the button says so instead
    of firing a request that would only come back 401.

    Read-only against OpenAI, and it sends the question, the schema and the row
    data of exactly nothing — a GET with a key and no body.
    """
    frappe.only_for(DS_WRITE_ROLES)
    key = (api_key or "").strip() or frappe.conf.get("llm_api_key")
    if not key:
        return {"available": False, "models": [], "problem":
                "No API key yet. Paste one into the API key tab first — browsing "
                "the models needs it, and it is never saved."}
    try:
        body, problem = _get_models(key)
    except Exception as error:  # noqa: BLE001
        # The exception's TYPE, never its text. An exception's message is
        # arbitrary — a library is free to quote whatever it was given — and
        # this reply goes to a browser. Every sentence returned from here is one
        # this module wrote. The type still says the useful thing: a
        # ConnectionError and an SSLError are different problems.
        body, problem = None, ("The models could not be listed "
                               f"({type(error).__name__}).")
    if problem:
        return {"available": False, "models": [], "problem": problem}
    models = sorted(str(item.get("id") or "") for item in (body.get("data") or [])
                    if isinstance(item, dict) and item.get("id"))
    if not models:
        return {"available": False, "models": [],
                "problem": "That key returned no models."}
    return {"available": True, "models": models, "default": MODEL}


def _get_models(key: str):
    """``(body, problem)`` — the one GET that leaves this app.

    Same structural shape as `_ask` below: exactly one `requests.get` in this
    file, its URL checked at the call site, so a second endpoint cannot be
    added without editing the check too. `MODELS_URL` is read-only — it lists
    what a key can see and changes nothing.
    """
    import requests

    if MODELS_URL != "https://api.openai.com/v1/models":
        frappe.throw("Refusing to call anything but the models endpoint.")
    response = requests.get(
        MODELS_URL,
        headers={"authorization": "Bearer " + key},
        timeout=30,
    )
    if response.status_code != 200:
        # The status ALONE, and returned rather than thrown so the picker can
        # show it in place. A 401 body can quote the request, and "helpful"
        # context is how a key reaches `_server_messages` and a browser.
        return None, f"The LLM provider returned HTTP {response.status_code}."
    return response.json(), None


def _model(model: str = None):
    """Request value, then site_config, then the module default."""
    return (model or "").strip() or frappe.conf.get("llm_model") or None


def _confirmed(doctypes) -> list[str]:
    """The DocTypes the user settled on, each one real.

    A name typed by hand that is not a DocType refuses here rather than
    reaching `_table_columns`, where it would come back as a true message about
    the wrong thing.
    """
    if isinstance(doctypes, str):
        doctypes = [part.strip() for part in doctypes.replace("\n", ",").split(",")]
    out = []
    for name in doctypes or []:
        name = str(name).strip()
        if not name or name in out:
            continue
        if not frappe.db.exists("DocType", name):
            frappe.throw(f"There is no DocType called '{name}' on this site.")
        out.append(name)
    return out


def _ask(payload: dict, api_key: str = None) -> dict:
    """The one HTTP call in this app, and the only one that leaves the server.

    Structural, in the shape `metabase_export_sql.py` uses: exactly one
    `requests.post` in the file, its URL checked at the call site, so a second
    endpoint cannot be added without the check being edited too.
    """
    import requests

    if API_URL != "https://api.openai.com/v1/chat/completions":
        frappe.throw("Refusing to call anything but the chat completions endpoint.")
    response = requests.post(
        API_URL,
        headers={"authorization": "Bearer " + _api_key(api_key),
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


def _refused(reasons, doctypes, sql: str = "") -> dict:
    """One shape for every refusal, so the reply keys cannot drift apart."""
    return {"supported": False, "sql": sql, "doctypes": list(doctypes),
            "operations": [], "reasons": list(reasons), "checked": [],
            "not_checked": NOT_CHECKED, "multiplied": []}


@frappe.whitelist()
def propose_from_question(question: str, doctypes, api_key: str = None,
                         model: str = None, previous_sql: str = None,
                         refusal: str = None):
    """Propose an Insights setup, over DocTypes the USER confirmed. Creates nothing.

    `doctypes` is required and is the whole point: the tables are settled by a
    person before a query is built, whether they came from `propose_tables` and
    were confirmed, or were typed by hand. There is no path here that picks a
    table on its own.

    `api_key`, when the page supplies one, is used for this request's outbound
    calls and then goes out of scope. It is never stored, logged or echoed.
    `model` resolves the same way — the request's value, then site_config's
    `llm_model`, then the default — and is likewise not stored anywhere.

    `previous_sql` + `refusal` make this call a RETRY: the page sends back the
    SQL the last call returned and the refusal it came with, and the model is
    asked to correct it. The loop lives in the page, bounded there, so each
    retry is one ordinary request through this same function — same
    validation, same allowlists, same widening check. A retry extends no new
    trust and skips nothing.
    """
    frappe.only_for(DS_WRITE_ROLES)
    question = (question or "").strip()
    if not question:
        frappe.throw("Type a question first.")
    chosen = _confirmed(doctypes)
    if not chosen:
        frappe.throw("Choose at least one DocType before building a query.")

    model = _model(model)
    columns = {doctype: _table_columns(doctype) for doctype in chosen}
    sql, cannot = sql_from_response(
        _ask(write_sql_request(question, columns, model,
                               previous_sql=(previous_sql or "").strip(),
                               refusal=(refusal or "").strip()), api_key))
    if cannot:
        return _refused([cannot], chosen)

    analysis = analyze_sql(sql)
    if not analysis["supported"]:
        return _refused(analysis["reasons"], chosen, sql)

    # The SQL may name a table it was never given. Before, this typed whatever
    # the query mentioned — so a model that widened past the confirmed set was
    # accepted, which is exactly the failure the confirm step exists to stop.
    # Widening now refuses by name instead of being quietly honoured.
    widened = [doctype for doctype in (analysis.get("doctypes") or [])
               if doctype not in chosen]
    if widened:
        return _refused(
            [f"the query reads {', '.join(sorted(widened))}, which "
             f"{'is' if len(widened) == 1 else 'are'} not among the tables you "
             f"chose ({', '.join(chosen)}). Add it above if you meant it."],
            chosen, sql)

    result = operations_from_sql(analysis, columns)
    if not result["supported"]:
        return _refused(result["reasons"], chosen, sql)

    children = {doctype for doctype in columns
                if getattr(frappe.get_meta(doctype), "istable", 0)}
    return {
        "supported": True,
        "sql": sql,
        "doctypes": chosen,
        "operations": result["operations"],
        "reasons": [],
        "checked": _checked(result["operations"], columns),
        "not_checked": NOT_CHECKED,
        "multiplied": rows_multiplied_by(result["operations"], children),
    }
