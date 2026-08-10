"""Compare two result sets: the card's own SQL against our translation.

Every test in this repo proves SHAPE — it converts, it opens, the operations
are the expected ones. None of them proves the converted query returns the same
NUMBERS. One report (QIPI) has had its figures eyeballed by a person. This is
the pure half of the harness that checks the rest: given two result sets it says
whether they agree, and where they do not.

**Frappe-free on purpose**, like `parser.py` and `sql_ops.py`: the comparison is
the part with the subtle mistakes in it, so it is unit-testable without a site.
`scripts/reconcile_numbers.py` does the I/O and hands the rows here.

**What a match here does and does not prove.** It proves our operations compute
what the card's SQL computes. It does NOT prove the card is right: if the card
itself fans out a one-to-many join, or never filtered `docstatus`, we reproduce
that faithfully and both sides agree. Those are card-fidelity questions and need
a different instrument — see the note in the script.
"""

from __future__ import annotations

import datetime
import math
from decimal import Decimal

from dashboard_studio.integrations.metabase.parser import _insights_name

# Why two tolerances rather than one.
#
# MySQL's AVG() over an exact-value column returns DECIMAL with the column's
# scale PLUS FOUR, so an average of integers comes back rounded to 4 decimal
# places: 3.3333. Insights computes through ibis/pandas in float64 and returns
# 3.3333333333333335. That is a formatting difference, not a disagreement, and
# it lands at about 1e-5 relative — so a relative tolerance tight enough to be
# useful would flag every average in the corpus as a finding. `ABS_TOL` absorbs
# exactly that rounding and nothing wider.
#
# `REL_TOL` then covers large values, where 1e-4 absolute is far too tight.
# Both are orders of magnitude below any real fault: a fan-out doubles a
# number, a swapped column changes its magnitude, integer division truncates.
# Nothing this is meant to catch hides under 1e-6.
#
# The report carries the largest delta seen per column EVEN WHEN IT PASSES, so
# the tolerance argues with itself: if the corpus lands at 1e-5 the reasoning
# above holds, and if it lands at 1e-2 that is a finding wearing a pass.
REL_TOL = 1e-6
ABS_TOL = 1e-4

# Stop recording individual differences past this many per card. The count is
# still reported in full — a query that disagrees on every row of 5,000 is one
# finding, not five thousand, and printing all of them buries the next card.
MAX_RECORDED = 20


def normalise(value):
    """One comparable form per value, across two very different drivers.

    `frappe.db.sql` hands back `Decimal`, `datetime.date` and `None`; ibis hands
    back numpy floats, pandas `Timestamp` (a `datetime` subclass) and `NaN`.
    Comparing those raw reports differences that are only the driver talking.

    Strings are NOT case-folded: MySQL compares them case-insensitively under
    most collations and ibis does not, which is one of the semantic drifts this
    harness exists to find. Folding here would hide it.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, datetime.datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return value.total_seconds()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return float(value)
    return str(value)


def _is_number(value):
    return isinstance(value, float) and not isinstance(value, bool)


def _delta(expected, actual):
    """Relative difference, or absolute when the expected value is ~0."""
    if expected == actual:
        return 0.0
    scale = max(abs(expected), abs(actual))
    return abs(expected - actual) / scale if scale else abs(expected - actual)


def match_columns(expected_columns, actual_columns, column_map=None):
    """``(pairs, only_expected, only_actual)`` — never a positional guess.

    Three ways a column pairs up, in order: a mapping the operator supplied, an
    exact name, then the same name under Insights' own `sanitize_name` (ADR-033
    slugs every computed alias with it, so `Exit  Qn. 7` in the card's SQL is
    `exit__qn__7` in ours — the same column, spelled as the engine spells it).

    What is deliberately NOT here is pairing the leftovers by position. The
    card's `AVG(x) AS avg` is our `avg_of_x`, and those will not match by name —
    so they are REPORTED as unmatched and the script prints a ready-to-fill
    `column_map`. A positional pairing would silently compare two columns
    nobody checked were the same, which produces both false differences and,
    worse, false agreement.
    """
    column_map = dict(column_map or {})
    remaining = list(actual_columns)
    pairs, only_expected = [], []
    for name in expected_columns:
        chosen = None
        for candidate in (column_map.get(name), name):
            if candidate is not None and candidate in remaining:
                chosen = candidate
                break
        if chosen is None:
            slug = _insights_name(name)
            for candidate in remaining:
                if _insights_name(candidate) == slug:
                    chosen = candidate
                    break
        if chosen is None:
            only_expected.append(name)
            continue
        remaining.remove(chosen)
        pairs.append((name, chosen))
    return pairs, only_expected, remaining


def _sorted_rows(rows, columns):
    """Rows in a canonical order, so an unordered query is not a wall of noise.

    A query with no ORDER BY may return its rows in any order, and comparing
    position by position would then report every row as different. The question
    this harness asks is "the same rows with the same values", so both sides are
    sorted by their own values first. Whether the two ORIGINAL orders agreed is
    reported separately — an ORDER BY that failed to translate is a real
    finding, just not a value one.
    """
    def one(value):
        # A three-part key so numbers sort AS NUMBERS. Sorting them by their
        # text is consistent right up until it is not: 10.0 keys as "10.0" and
        # its float64 twin 9.9999999 as "9.99…", which lands the other side of
        # a row worth 9.5 — so the two sides sort into different orders and
        # every row is then compared against the wrong one.
        #
        # And the number is rounded to 6 significant figures first, because the
        # two sides legitimately differ in the last places: MySQL's AVG returns
        # DECIMAL at 4 decimal places where ibis returns full float64. Two rows
        # that this collapses are within a millionth of each other, so either
        # pairing of them compares values that agree anyway.
        if value is None:
            return (0, 0.0, "")
        if _is_number(value):
            return (1, float("%.6g" % value), "")
        return (2, 0.0, str(value))

    return sorted(rows, key=lambda row: tuple(one(row.get(c)) for c in columns))


def compare_results(expected, actual, column_map=None,
                    rel_tol=REL_TOL, abs_tol=ABS_TOL):
    """Does our translation return what the card's SQL returns?

    `expected` is the card's SQL result, `actual` ours; each is
    ``{"columns": [...], "rows": [{column: value}, ...]}``.

    Row COUNT is checked first and short-circuits the value comparison: when
    the counts differ the rows do not correspond, and pairing them anyway would
    report dozens of value differences that are all one fault. A differing row
    count is the signature of the faults worth finding — a join translated with
    the wrong type, a filter that did not survive, a grouping that collapsed.
    """
    expected_rows = [{k: normalise(v) for k, v in row.items()}
                     for row in expected.get("rows") or []]
    actual_rows = [{k: normalise(v) for k, v in row.items()}
                   for row in actual.get("rows") or []]
    pairs, only_expected, only_actual = match_columns(
        expected.get("columns") or [], actual.get("columns") or [], column_map)

    report = {
        "match": False,
        "inconclusive": False,
        "row_count": {"expected": len(expected_rows), "actual": len(actual_rows)},
        "columns": {"paired": pairs, "only_expected": only_expected,
                    "only_actual": only_actual},
        "differences": [],
        "difference_count": 0,
        "max_delta": {},
        "order_differs": False,
        "notes": [],
    }
    if not expected_rows and not actual_rows:
        # Two empty results agree, and prove nothing. This matters most on a
        # database that is not the one the report was written against — an
        # empty or partially-populated copy makes every card "agree", and a
        # column of green ticks is exactly how a harness stops being read.
        report["inconclusive"] = True
        report["notes"].append(
            "both sides returned NO ROWS — they agree, and that is not "
            "evidence of anything. Check this card against a database that "
            "holds the data it reports on")
        return report
    if only_expected or only_actual:
        report["notes"].append(
            "columns could not be paired by name: "
            f"{only_expected or '-'} on the card's side, "
            f"{only_actual or '-'} on ours. Supply a column_map to compare them "
            "— they are NOT paired by position, because a guessed pairing can "
            "agree as easily as it can disagree")
    if len(expected_rows) != len(actual_rows):
        report["notes"].append(
            f"row counts differ ({len(expected_rows)} vs {len(actual_rows)}) — "
            "values not compared, because the rows do not correspond and every "
            "column would report a difference that is really this one")
        return report
    if not pairs:
        report["notes"].append("no columns could be paired, so nothing was compared")
        return report

    left = _sorted_rows(expected_rows, [p[0] for p in pairs])
    right = _sorted_rows(actual_rows, [p[1] for p in pairs])
    report["order_differs"] = (
        [tuple(row.get(c) for c, _ in pairs) for row in expected_rows]
        != [tuple(row.get(c) for _, c in pairs) for row in actual_rows])

    for index, (row_e, row_a) in enumerate(zip(left, right)):
        for name_e, name_a in pairs:
            value_e, value_a = row_e.get(name_e), row_a.get(name_a)
            if _is_number(value_e) and _is_number(value_a):
                delta = _delta(value_e, value_a)
                previous = report["max_delta"].get(name_e, 0.0)
                report["max_delta"][name_e] = max(previous, delta)
                if math.isclose(value_e, value_a, rel_tol=rel_tol, abs_tol=abs_tol):
                    continue
            elif value_e == value_a:
                continue
            else:
                delta = None
            report["difference_count"] += 1
            if len(report["differences"]) < MAX_RECORDED:
                report["differences"].append(
                    {"row": index, "column": name_e, "as_column": name_a,
                     "expected": value_e, "actual": value_a, "delta": delta})

    report["match"] = (report["difference_count"] == 0
                       and not only_expected and not only_actual)
    if report["difference_count"] > len(report["differences"]):
        report["notes"].append(
            f"{report['difference_count']} differing values in total; the first "
            f"{MAX_RECORDED} are listed")
    return report


def describe(report, card=""):
    """The report as lines a person reads, worst news first."""
    counts = report["row_count"]
    head = f"card {card}: " if card else ""
    if report["inconclusive"]:
        return [f"{head}INCONCLUSIVE — no rows on either side"] + [
            f"   note: {note}" for note in report["notes"]]
    if report["match"]:
        worst = max(report["max_delta"].values(), default=0.0)
        return [f"{head}MATCH — {counts['actual']} rows, "
                f"largest relative delta {worst:.2g}"
                + (" (ROW ORDER DIFFERS)" if report["order_differs"] else "")]
    lines = [f"{head}DIFFERS — {counts['expected']} rows from the card's SQL, "
             f"{counts['actual']} from ours"]
    for note in report["notes"]:
        lines.append(f"   note: {note}")
    for difference in report["differences"]:
        delta = "" if difference["delta"] is None else f"  (delta {difference['delta']:.3g})"
        lines.append(f"   row {difference['row']} {difference['column']}: "
                     f"card={difference['expected']!r} ours={difference['actual']!r}{delta}")
    return lines
