"""The verification gate, removed from the converter on request.

ADR-007 reopened translation on one condition: a converted query carried an
``[UNVERIFIED]`` marker in its TITLE until a person had compared its number
against the report it came from, and a mismatch refused. ADR-008 removed that
condition deliberately — see docs/DECISIONS.md.

Kept because it worked, and because the reasoning inside it is not obvious:
``_THOUSANDS`` in particular exists to stop "12,34" being read as 1234, which
in most of Europe means 12.34 — a hundredfold disagreement passing silently,
inside the one function whose job was catching a disagreement.

Nothing imports this.
"""

import re

UNVERIFIED_PREFIX = "[UNVERIFIED] "

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
