"""Result-parity arithmetic for DS Validation Comparison.

Given a source result (e.g. from the legacy Metabase query) and the target
result produced by this app's engine, work out what differs and how badly.

Pure and Frappe-free, so the logic is testable without a live Bench. This module
decides only Match / Discrepancy / Flagged. It never returns ``Accepted`` —
accepting a known difference is a reviewer's judgement, not arithmetic.
"""

from __future__ import annotations

from typing import Any

MATCH = "Match"
DISCREPANCY = "Discrepancy"
FLAGGED = "Flagged"

# Reported when a value cannot be compared at all, as opposed to comparing
# unequal — the two need different handling by a reviewer.
MISSING = "missing"


def _as_number(value: Any) -> float | None:
    """Parse a value that may arrive as a string (the DocType stores Data)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def compare_values(original: Any, new: Any, *, tolerance_pct: float = 0.0) -> dict[str, Any]:
    """Compare one pair of values.

    Returns ``difference`` (new - original), ``difference_pct`` relative to the
    original, and a status. Anything that cannot be read as a number is
    ``Flagged`` rather than guessed at — a blank or unparsable figure is not the
    same as a zero.
    """
    left = _as_number(original)
    right = _as_number(new)

    if left is None or right is None:
        return {
            "original_value": original,
            "new_value": new,
            "difference": None,
            "difference_pct": None,
            "status": FLAGGED,
            "reason": MISSING if (original is None or new is None) else "not numeric",
        }

    difference = right - left
    if left == 0:
        # No meaningful percentage against a zero baseline; 0 -> 0 still matches.
        difference_pct = 0.0 if difference == 0 else None
    else:
        difference_pct = (difference / abs(left)) * 100.0

    within_tolerance = (
        difference == 0
        or (difference_pct is not None and abs(difference_pct) <= tolerance_pct)
    )
    return {
        "original_value": original,
        "new_value": new,
        "difference": difference,
        "difference_pct": difference_pct,
        "status": MATCH if within_tolerance else DISCREPANCY,
        "reason": "",
    }


def _index(rows: list[dict[str, Any]], value_key: str) -> dict[str, Any]:
    """Index result rows by their dimension value.

    Rows look like ``{<dimension>: label, "count": n}``; the dimension field is
    whichever key is not the value key, matching what the engine returns.
    """
    indexed = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        label = None
        for key, value in row.items():
            if key != value_key:
                label = value
                break
        indexed[str(label)] = row.get(value_key)
    return indexed


def compare_result_sets(
    source_rows: list[dict[str, Any]],
    target_rows: list[dict[str, Any]],
    *,
    value_key: str = "count",
    tolerance_pct: float = 0.0,
) -> dict[str, Any]:
    """Compare two grouped result sets group by group.

    Every group on either side is reported, so a group present in one result and
    absent from the other is surfaced as ``Flagged`` rather than quietly dropped
    — a missing group is exactly the kind of migration error this exists to
    catch.

    The overall status is the worst seen, where Flagged outranks Discrepancy: a
    group that could not be compared is a bigger problem than one that compared
    unequal, because its true state is unknown.
    """
    source = _index(source_rows, value_key)
    target = _index(target_rows, value_key)

    labels = list(source.keys()) + [label for label in target if label not in source]
    rows = []
    for label in labels:
        comparison = compare_values(
            source.get(label), target.get(label), tolerance_pct=tolerance_pct
        )
        comparison["label"] = label
        rows.append(comparison)

    summary = {
        "matched": sum(1 for row in rows if row["status"] == MATCH),
        "discrepancies": sum(1 for row in rows if row["status"] == DISCREPANCY),
        "flagged": sum(1 for row in rows if row["status"] == FLAGGED),
    }
    if summary["flagged"]:
        status = FLAGGED
    elif summary["discrepancies"]:
        status = DISCREPANCY
    else:
        status = MATCH

    totals = compare_values(
        sum(v for v in (_as_number(x) for x in source.values()) if v is not None),
        sum(v for v in (_as_number(x) for x in target.values()) if v is not None),
        tolerance_pct=tolerance_pct,
    )

    return {"status": status, "summary": summary, "rows": rows, "totals": totals}
