"""Convert a GUI-built Metabase card into a real Insights v3 query.

Where the SQL path hands Insights a block of text nobody can click, this hands
it an Operations list — Select Source, Join Table, Filter Rows, Group &
Summarize — which is what makes a migrated report maintainable afterwards.

**Nothing here is trustworthy until a person says it is.** ADR-006 rejected
translation once, and it is reopened on one condition: a converted query
carries an ``[UNVERIFIED]`` marker until somebody has compared its number
against the Metabase card it came from. That marker is in the TITLE on purpose
— it travels into Insights, so a person who finds the query there without ever
having seen Studio still sees that nobody has checked it.

The reason the gate exists, stated plainly because it is easy to erode: a
translation that disagrees with Metabase does not fail, it returns a different
number. `docs/SOPHIA_FAULT_PATTERN.md` — *"they do not fail, they disagree."*
Every refusal in `integrations/metabase/mbql.py` and every step of this gate is
paying for that.

Read-only against Metabase throughout: one GET for the card, one per table.
Studio never executes anything, here or anywhere else.
"""

import frappe

from dashboard_studio.api.insights import (
    BASE_TYPE_TO_DATA_TYPE,
    MAX_TITLE_LENGTH,
    QUERY_DOCTYPE,
    SITE_DB,
    _require_insights,
    _resolve_workbook,
    clamp_title,
)
from dashboard_studio.api.studio import DS_WRITE_ROLES
from dashboard_studio.integrations.metabase.card import _scan_sources
from dashboard_studio.integrations.metabase.client import fetch_card, fetch_table_metadata
from dashboard_studio.integrations.metabase.mbql import translate_card

# Carried in the title so it travels with the record. A person who opens this
# query in Insights next month, having never seen Studio, still learns that its
# number has not been checked against the card it was converted from.
#
# ponytail: the marker IS the state — no new DocType, no parallel table to drift
# from the record it describes. The ceiling: someone can rename the title in
# Insights and erase the marker by hand. That is a deliberate action rather than
# a silent default, which is the line this gate is drawn at.
UNVERIFIED_PREFIX = "[UNVERIFIED] "


def build_metadata(card, fetch=None):
    """Metabase ids -> the names and types the translator needs.

    ``fetch`` is the injection seam: production passes nothing and one GET per
    table happens; tests pass a dict-backed fake and no network is touched.
    """
    fetch = fetch or fetch_table_metadata
    table_ids, _cards = _scan_sources(card.get("dataset_query"))
    metadata = {"tables": {}, "fields": {}, "table_columns": {}}
    for table_id in sorted(table_ids):
        table = fetch(table_id) or {}
        name = str(table.get("name") or "").strip()
        if not name:
            continue
        metadata["tables"][table_id] = {"name": name}
        columns = []
        for field in table.get("fields") or []:
            if not isinstance(field, dict):
                continue
            field_name = str(field.get("name") or "").strip()
            if not field_name:
                continue
            columns.append(field_name)
            if field.get("id") is not None:
                metadata["fields"][field["id"]] = {
                    "name": field_name,
                    "data_type": BASE_TYPE_TO_DATA_TYPE.get(
                        str(field.get("base_type") or ""), "String"),
                }
        metadata["table_columns"][table_id] = columns
    return metadata


@frappe.whitelist()
def preview_conversion(card_id):
    """What the conversion WOULD produce, without writing anything.

    Returns ``{supported, reasons, operations, title, card_id}``. An unsupported
    card comes back with reasons rather than a refusal, because the caller wants
    to show them next to the card — "this question uses a custom column" is
    something to read, not an error.
    """
    frappe.only_for(DS_WRITE_ROLES)
    card = fetch_card(card_id)
    result = translate_card(card, build_metadata(card))
    result["card_id"] = card.get("id")
    result["title"] = clamp_title(
        str(card.get("name") or "").strip() or f"Metabase card {card.get('id')}")
    return result


@frappe.whitelist()
def convert_metabase_card(card_id, workbook: str = None):
    """Translate a card and file it in Insights as an UNVERIFIED query.

    Refuses outright — rather than returning reasons — because this one writes.
    A partial conversion is a query that answers a different question, and the
    caller has ``preview_conversion`` for the read-only look.
    """
    frappe.only_for(DS_WRITE_ROLES)
    _require_insights()

    card = fetch_card(card_id)
    result = translate_card(card, build_metadata(card))
    if not result["supported"]:
        frappe.throw(
            "This card cannot be converted: " + "; ".join(result["reasons"]) +
            ". Its SQL can still be copied across by hand."
        )

    workbook = _resolve_workbook(workbook)
    title = str(card.get("name") or "").strip() or f"Metabase card {card.get('id')}"
    # Clamped AFTER the prefix, so the marker is never the part that gets cut.
    title = UNVERIFIED_PREFIX + clamp_title(title)[: MAX_TITLE_LENGTH - len(UNVERIFIED_PREFIX)]

    doc = frappe.get_doc({
        "doctype": QUERY_DOCTYPE,
        "workbook": workbook,
        "title": title,
        "is_builder_query": 1,
        "use_live_connection": 1,
        "operations": frappe.as_json(result["operations"]),
    }).insert()

    return {
        "name": doc.name,
        "title": title,
        "workbook": workbook,
        "data_source": SITE_DB,
        "verified": False,
        "card_id": card.get("id"),
        "operations": result["operations"],
        "insights_url": f"/insights/workbook/{workbook}/query/{doc.name}",
    }


# A number with commas as THOUSANDS separators: 1,234 / 1,234,567 / 1,234.50.
# Anything else keeps its commas.
#
# This pattern is load-bearing, and the reason is a 100x error. Stripping every
# comma before parsing treats "12,34" as 1234 — but in most of Europe that
# string means 12.34, so a genuine hundredfold disagreement would have passed
# verification silently. Inside the one function whose entire job is catching a
# disagreement.
_THOUSANDS = __import__("re").compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")


def _as_number(text):
    """``text`` as a float, or None if it is not unambiguously one."""
    candidate = text.replace(",", "") if _THOUSANDS.match(text) else text
    try:
        return float(candidate)
    except ValueError:
        return None


def verification_matches(metabase_value, insights_value):
    """Do the two numbers agree — ``(matches, reason)``.

    Compared as NUMBERS when both parse unambiguously, so "1,234" and "1234"
    and "1234.0" agree — thousands separators and trailing zeros are formatting.
    Compared as exact text otherwise, which is the safe direction: a string this
    cannot read as a number has to match character for character rather than be
    guessed at.
    """
    left = str(metabase_value or "").strip()
    right = str(insights_value or "").strip()
    if not left or not right:
        return False, "Enter the number from both Metabase and Insights."

    left_number, right_number = _as_number(left), _as_number(right)
    if left_number is not None and right_number is not None:
        if left_number == right_number:
            return True, None
    elif left == right:
        return True, None

    return False, (
        f"Those do not match: Metabase says {left}, Insights says {right}. The "
        "conversion stays unverified. A difference here is the whole reason this "
        "check exists — compare the filters and the grouping before trusting it."
    )


@frappe.whitelist()
def verify_converted_query(query: str, metabase_value: str, insights_value: str):
    """Record that a person compared the two numbers, and clear the marker.

    Refuses when they differ. There is deliberately no "verify anyway": the
    marker is the only thing telling a later reader that this number was ever
    checked, and a mismatched pair is precisely when it must stay.
    """
    frappe.only_for(DS_WRITE_ROLES)
    _require_insights()

    matches, reason = verification_matches(metabase_value, insights_value)
    if not matches:
        frappe.throw(reason)

    doc = frappe.get_doc(QUERY_DOCTYPE, query)
    title = str(doc.get("title") or "")
    if not title.startswith(UNVERIFIED_PREFIX):
        # Already verified, or never converted. Not an error — someone clicking
        # twice should not be told off — but say which, so it is not mistaken
        # for the check having just passed.
        return {"name": query, "title": title, "verified": True, "already": True}

    doc.title = title[len(UNVERIFIED_PREFIX):]
    doc.save()
    return {"name": query, "title": doc.title, "verified": True, "already": False}
