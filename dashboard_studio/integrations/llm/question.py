"""A plain-English question -> SQL, for the existing converter to translate.

**This module must never import frappe, and there is a test that says so.** That
is the structural guarantee that no row of data can reach the model: there is no
path from here to a database. What goes out is a question somebody typed and the
column names, with their types, of the tables the USER confirmed. Sample values
are not withheld by care — they are unreachable.

**Choosing the tables no longer happens here.** It used to: a first pass sent
the question and every DocType name on the site and asked which ones fitted.
That reply was sampled, so the same question produced a different set of tables
on each run — and ADR-023 records that step as the entire defence against the
wrong-table failure. It is now ranked from the schema instead, deterministically
and with its evidence, in `integrations/doctype_rank.py` (ADR-036). Nothing
about a question leaves the site until the tables are settled.

**The model emits SQL, not operations.** Everything downstream then applies
unchanged: the wrapper rules, the allowlists, the type checks and every refusal
built over twenty ADRs. Emitting operations directly would need a second
validator for operation shapes, against a format where an unrecognised key is
dropped silently — rebuilding what already exists, worse.

Nothing here executes anything. The SQL is parsed, never run, exactly as pasted
SQL is.

The HTTP call is INJECTED (`call`), so the whole path is testable without a
network route — there is none from this repo — and so this file has no
credential in it to leak.
"""

from __future__ import annotations

# The narrow shape the converter can translate, told to the model up front.
# Asking for SQL it cannot translate wastes a round trip and produces a refusal
# the user reads as a failure of the feature rather than of the question.
_SUPPORTED = """\
- ONE table, or tables joined each on a single `a.column = b.column` equality
- WHERE with comparisons (=, !=, >, >=, <, <=), either all AND-ed or all OR-ed
- GROUP BY plain columns
- COUNT, SUM, AVG, MIN, MAX, and arithmetic over them
- year(), month(), quarter(), day() of a date column
- CASE WHEN <column or date part> = <literal> THEN <literal> ... END
- ORDER BY a column the query produces, and LIMIT

Write it in THIS dialect. The reader is a parser with the subset above, not a
person, and idiomatic SQL that a person would prefer is refused:
- Every column BACKTICKED and qualified by its table:
  `tabSales Invoice`.`posting_date`. A short table alias is fine
  (`si`.`posting_date`), but a BARE column name is not — `si.posting_date`
  and `posting_date` are both refused.
- Every ORDER BY and every GROUP BY names a column the SELECT list PRODUCES,
  spelled exactly — never a SELECT-list alias. After a GROUP BY the produced
  columns are the grouped columns and the aggregates, and the aggregates are
  named `sum_of_<column>`, `avg_of_<column>`, `min_of_<column>`,
  `max_of_<column>` and `count`. So `ORDER BY `sum_of_sales_income` DESC`,
  not `ORDER BY `total` DESC`.

NOT supported, do not use: subqueries, UNION, HAVING, DISTINCT, LIKE, IN,
BETWEEN, IS NULL, window functions, CROSS joins, joining the same table twice,
AND and OR mixed in one WHERE, DAYOFWEEK, WEEK, CAST to an integer type."""

_SYSTEM = """\
You translate a business question into ONE MySQL SELECT statement against a \
Frappe database. Tables are named `tab<DocType>`, e.g. `tabSales Invoice`.

Rules:
- Use ONLY the columns listed for you. Never invent one.
- Reply with the SQL and nothing else. No explanation, no code fences.
- If the question cannot be answered from the columns given, reply with exactly \
CANNOT: followed by one short sentence saying what is missing.

The statement must fit this subset:
""" + _SUPPORTED

# Read out of OpenAI's own `openai-python` SDK at main rather than recalled:
#
#   _client.py                      base_url is https://api.openai.com/v1
#   README.md                       the chat example is
#                                   chat.completions.create(model="gpt-5.5",
#                                     messages=[{"role": "developer", ...},
#                                               {"role": "user", ...}])
#   types/chat/completion_create_params.py
#                                   `max_tokens` is deprecated in favour of
#                                   `max_completion_tokens`
#   types/chat/chat_completion.py   the reply is choices[].message
#
# The instruction message is role "developer", not "system". Both exist in
# `chat_completion_message_param.py`; developer is what the current chat
# example uses.
API_URL = "https://api.openai.com/v1/chat/completions"

# `gpt-5.4-mini`, read off the SDK's `types/shared/chat_model.py` `ChatModel`
# literal rather than recalled — it is there beside its dated twin
# `gpt-5.4-mini-2026-03-17`, and the undated name is the one that keeps working.
#
# It is a DELIBERATE step down from `gpt-5.5` to cut cost, made knowing the
# risk it lands on. The one decision this converter cannot verify is which
# TABLE a question is about (ADR-023): a real question about recruitment agents
# was answered from ERPNext's sales-commission tables, every column real and
# every type right, with a more expensive model. A cheaper one does not make
# that worse in a way anything here can detect — the referential checks pass
# either way — so the DocType confirm step is what carries it, and spot-checking
# real questions is the way back up a tier.
MODEL = "gpt-5.4-mini"

# `GET /models`, from `resources/models.py`: `self._get_api_list("/models",
# page=SyncPage[Model], ... security={"bearer_auth": True})`. The envelope is
# `SyncPage` — `{object: str, data: [...]}` (pagination.py) — and each entry is
# `Model` = `{id, created, object: "model", owned_by}` (types/model.py). Read,
# not guessed; `id` is the string the chat endpoint wants.
MODELS_URL = "https://api.openai.com/v1/models"
MAX_TOKENS = 1024


def _message(system: str, user: str, model: str = None) -> dict:
    """`model` empty means MODEL, so a blank field behaves as it always did.

    Free text on purpose: model names change, and a dropdown of them goes stale
    where a blank box cannot.
    """
    return {"model": (model or "").strip() or MODEL,
            "max_completion_tokens": MAX_TOKENS,
            "messages": [{"role": "developer", "content": system},
                         {"role": "user", "content": user}]}


def _text_of(response) -> str:
    """The assistant's text, or "" — never an exception on an odd shape."""
    if not isinstance(response, dict):
        return ""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    return str(message.get("content") or "").strip()


def write_sql_request(question: str, schema: dict, model: str = None,
                      previous_sql: str = "", refusal: str = "") -> dict:
    """Step two: the SQL. `schema` is ``{DocType: {column: data_type}}``.

    That mapping is the same one the converter itself types columns from, so
    what the model is told and what the validator checks against cannot drift
    apart — they are one value.

    `previous_sql` + `refusal` (both or neither) turn the request into a
    CORRECTION: the converter's own refusal text is handed back so the model
    can fix what it names. This extends no new trust — the reply goes through
    the same validation as a first attempt — and it adds no new egress: the
    previous SQL is text the model itself wrote, and the refusal is composed
    by our converter from that SQL and the schema already sent above. No row
    of data exists on this path to leak (this module cannot reach a database).
    """
    if not isinstance(question, str):
        raise TypeError("question must be a string")
    if not isinstance(schema, dict):
        raise TypeError("schema must be a dict")
    blocks = []
    for doctype in sorted(schema):
        columns = schema[doctype] or {}
        listing = ", ".join(f"{name} ({columns[name]})" for name in sorted(columns))
        blocks.append(f"`tab{doctype}`\n  {listing}")
    tables = "\n\n".join(blocks)
    user = f"Question: {question}\n\nTables and columns:\n\n{tables}"
    if previous_sql and refusal:
        user += (
            "\n\nA previous attempt was refused by the SQL validator."
            f"\n\nPrevious SQL:\n{previous_sql}"
            f"\n\nRefused because:\n{refusal}"
            "\n\nWrite a corrected statement answering the same question, "
            "fixing exactly what the refusal names. All rules above still apply."
        )
    return _message(_SYSTEM, user, model)


def sql_from_response(response) -> tuple[str, str]:
    """``(sql, refusal)`` — exactly one is truthy.

    A model that says CANNOT is doing the right thing, and its sentence is a
    better message than anything this could invent, so it is passed through.
    """
    text = _text_of(response)
    if not text:
        return "", "The model returned nothing this could read as SQL."
    if text.upper().startswith("CANNOT"):
        return "", text[len("CANNOT"):].lstrip(": ").strip() or "It could not answer that."
    # Fences are asked against, and arrive anyway often enough to be worth
    # stripping rather than refusing over.
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    if not text.upper().lstrip("( ").startswith("SELECT"):
        return "", "The model replied with something that is not a SELECT statement."
    return text, ""
