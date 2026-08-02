"""Pasted SQL -> the same Insights v3 operations the MBQL path produces.

The card path reads a Metabase question's structure and translates it. This does
the same job from SQL text, so a query that was never a Metabase card — or one
whose card cannot be reached — still lands in Insights as clickable operations
rather than a block of SQL nobody can edit.

**Where the line is, concretely.** `parser.analyze_sql` already draws most of it
and this narrows it further:

  works      single table, WHERE with AND-ed comparisons, GROUP BY, one
             COUNT/SUM/AVG aggregate
  refused    any JOIN, subqueries, multiple joins, OR, UNION, HAVING, CASE,
             DISTINCT, window functions, more than one aggregate, LIKE and IN

**Why joins are refused rather than attempted.** `analyze_sql` hands back a join
condition as unparsed text — ``"b.`ref` = a.`po`"`` — with table aliases still in
it. Turning that into Insights' structured ``{left_column, right_column}`` means
splitting a string on ``=`` and guessing which side belongs to which table. That
is exactly the string surgery that produces a join which runs, returns rows, and
answers a different question. The MBQL path can do joins because Metabase hands
over the two sides already separated; SQL text does not.

**The one thing SQL cannot supply is types**, and Insights needs a ``data_type``
on every dimension and measure. The MBQL path gets them from Metabase's field
metadata. Here they come from Frappe's own DocType metadata — the tables are
``tab<DocType>``, so the site already knows what every column is. That is the
injected ``columns`` argument, and without it nothing is translated: a guessed
type draws a chart that is wrong without saying so.

Everything converted this way is subject to the same verification gate as the
card path. See ADR-007.
"""

from __future__ import annotations

from dashboard_studio.integrations.metabase.mbql import (
    AGGREGATIONS,
    COUNT_COLUMN,
    DEFAULT_DATA_SOURCE,
    DIMENSION_DATA_TYPES,
    MEASURE_DATA_TYPES,
    NUMERIC_ONLY_AGGREGATIONS,
    OPERATORS,
    _filter,
    _source,
    _summarize,
)

# Frappe fieldtype -> Insights data_type. Anything unlisted becomes String,
# which degrades safely: a String dimension is normal, and a String measure is
# refused by name below rather than charted.
FIELDTYPE_TO_DATA_TYPE = {
    "Int": "Integer",
    "Long Int": "Integer",
    "Check": "Integer",
    "Float": "Decimal",
    "Currency": "Decimal",
    "Percent": "Decimal",
    "Date": "Date",
    "Datetime": "Datetime",
    "Time": "Time",
}

# The parser reports SQL functions upper-case; Insights names them lower-case.
SQL_AGGREGATIONS = {"COUNT": "count", "SUM": "sum", "AVG": "avg",
                    "MIN": "min", "MAX": "max"}


def columns_from_meta(meta_fields):
    """Frappe DocType fields -> ``{column_name: data_type}``.

    ``meta_fields`` is ``[(fieldname, fieldtype), …]`` — passed in rather than
    read here, so this module stays Frappe-free and testable.

    `name` is added because every Frappe table has it and no DocType lists it as
    a field; a query grouping by `name` would otherwise look like a typo.
    """
    columns = {"name": "String"}
    for fieldname, fieldtype in meta_fields or []:
        if fieldname:
            columns[fieldname] = FIELDTYPE_TO_DATA_TYPE.get(fieldtype, "String")
    return columns


def _value(raw, data_type):
    """A filter value typed to match its column.

    The parser hands back everything as text, including numbers. Sending "100"
    where Insights expects a number is the kind of thing that compares as a
    string and silently matches nothing.
    """
    if data_type not in MEASURE_DATA_TYPES:
        return raw
    try:
        return int(raw) if data_type == "Integer" else float(raw)
    except (TypeError, ValueError):
        return raw


def operations_from_sql(analysis, columns, data_source=DEFAULT_DATA_SOURCE):
    """``analyze_sql`` output + column types -> Insights operations.

    Returns ``{supported, operations, reasons}``. As everywhere in this
    integration, an unsupported query hands back NO operations: a partial list
    is a query that answers a different question.
    """
    if not isinstance(analysis, dict):
        raise TypeError("analysis must be the dict analyze_sql returns")
    reasons = list(analysis.get("reasons") or [])
    columns = columns or {}

    if analysis.get("join") or len(analysis.get("doctypes") or []) > 1:
        reasons.append(
            "this query joins tables, and a join condition arrives here as text "
            "rather than as two named columns — converting it would mean guessing "
            "which side is which. Build the join in Insights, or convert the "
            "Metabase card instead"
        )
    doctypes = [d for d in (analysis.get("doctypes") or []) if d]
    if not doctypes:
        reasons.append("no table found in this query")
    if not columns:
        reasons.append(
            "the columns of that table are not known here, so nothing can be "
            "typed — Insights needs a data type on every grouping and measure"
        )
    if reasons:
        return {"supported": False, "operations": [], "reasons": reasons}

    operations = [_source("tab" + doctypes[0], data_source)]

    for rule in analysis.get("filters") or []:
        column = str(rule.get("field") or "").strip()
        operator = OPERATORS.get(str(rule.get("operator") or "").strip())
        if not operator:
            reasons.append(
                f"filter operator '{rule.get('operator')}' is not one this converter "
                "translates — it handles =, !=, >, >=, < and <="
            )
            continue
        if column not in columns:
            reasons.append(f"'{column}' is not a column of {doctypes[0]}")
            continue
        operations.append(_filter(column, operator, _value(rule.get("value"), columns[column])))

    aggregations = analysis.get("aggregations") or []
    group_by = [g for g in (analysis.get("group_by") or []) if g]
    if len(aggregations) > 1:
        reasons.append(
            f"this query has {len(aggregations)} aggregates — only one is translated"
        )
    elif aggregations:
        measures, dimensions = _measures(aggregations[0], columns, reasons), []
        for column in group_by:
            if column not in columns:
                reasons.append(f"'{column}' is not a column of {doctypes[0]}")
                continue
            if columns[column] not in DIMENSION_DATA_TYPES:
                reasons.append(
                    f"'{column}' is {columns[column]}, and Insights groups only by "
                    "text, a date or a time"
                )
                continue
            dimensions.append({"dimension_name": column, "column_name": column,
                               "data_type": columns[column]})
        if measures:
            operations.append(_summarize(measures, dimensions))
    elif group_by:
        reasons.append("this query groups without aggregating, which has no chart to draw")

    if reasons:
        return {"supported": False, "operations": [], "reasons": reasons}
    return {"supported": True, "operations": operations, "reasons": []}


def _measures(aggregation, columns, reasons):
    function = str(aggregation.get("function") or "").upper()
    name = SQL_AGGREGATIONS.get(function)
    if not name or name not in AGGREGATIONS.values():
        reasons.append(f"aggregation '{function or 'unknown'}' is not translated")
        return []
    argument = str(aggregation.get("argument") or "").strip().strip("`")

    # COUNT(*) has no column. Insights' own count measure names it "count".
    if name == "count" and (not argument or argument == "*"):
        return [{"measure_name": COUNT_COLUMN, "column_name": COUNT_COLUMN,
                 "data_type": "Integer", "aggregation": "count"}]
    if argument not in columns:
        reasons.append(f"'{argument}' is not a column this query can aggregate")
        return []
    if name in NUMERIC_ONLY_AGGREGATIONS and columns[argument] not in MEASURE_DATA_TYPES:
        reasons.append(
            f"'{argument}' is {columns[argument]}, and only a number can be {function}'d"
        )
        return []
    return [{
        "measure_name": f"{name}_of_{argument}",
        "column_name": argument,
        "data_type": "Integer" if name == "count" else columns[argument],
        "aggregation": name,
    }]
