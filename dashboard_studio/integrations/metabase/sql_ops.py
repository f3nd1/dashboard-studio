"""Pasted SQL -> the same Insights v3 operations the MBQL path produces.

The card path reads a Metabase question's structure and translates it. This does
the same job from SQL text, so a query that was never a Metabase card — or one
whose card cannot be reached — still lands in Insights as clickable operations
rather than a block of SQL nobody can edit.

**Where the line is, concretely.** `parser.analyze_sql` already draws most of it
and this narrows it further:

  works      one table, or two joined on a single `a.col = b.col` equality;
             WHERE with AND-ed comparisons, GROUP BY, one COUNT/SUM/AVG
             aggregate
  refused    subqueries, more than one join, CROSS and self joins, an ON clause
             that is anything but a single equality of two qualified columns,
             OR, UNION, HAVING, CASE, DISTINCT, window functions, more than one
             aggregate, LIKE and IN

**How a join is translated, and where it stops.** `analyze_sql` reads the ON
clause into two *named, table-oriented* columns — ``source_column`` always
belongs to the FROM table and ``join_column`` to the joined one — which is
exactly what Insights' ``join_condition`` means. Both names are then checked
against the real columns of their DocType here, so a column that does not exist
refuses rather than being written into a query that runs and answers something
else. Everything the orientation cannot be certain about (an unqualified side, a
compound ON, a self join) refuses back in the parser, by name.

**The one thing SQL cannot supply is types**, and Insights needs a ``data_type``
on every dimension and measure. The MBQL path gets them from Metabase's field
metadata. Here they come from Frappe's own DocType metadata — the tables are
``tab<DocType>``, so the site already knows what every column is. That is the
injected ``columns`` argument — ``{DocType: {column: data_type}}``, one entry per
table the query touches — and without it nothing is translated: a guessed type
draws a chart that is wrong without saying so. It doubles as the check that
makes joins safe: every column name read out of the SQL has to be one the
DocType really has.

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
    _join,
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


def _type_of(reference, available, tables):
    """A column reference -> ``(data_type, reason)``, exactly one of them set.

    ``reference`` is ``{"field", "table"}`` as the parser returns it: ``table``
    is set when the SQL qualified the column and None when it did not. An
    unqualified name that exists in BOTH joined tables refuses — after a join
    every Frappe table contributes a `name`, and picking one of them is picking
    which rows the filter keeps.
    """
    column = str(reference.get("field") or "").strip()
    table = reference.get("table")
    owners = available.get(column) or {}
    if table:
        if table not in owners:
            return None, f"'{column}' is not a column of {table}"
        return owners[table], None
    if not owners:
        return None, f"'{column}' is not a column of {' or '.join(tables)}"
    if len(owners) > 1:
        return None, (
            f"'{column}' is a column of both {' and '.join(owners)}, and the SQL does "
            "not say which one is meant — qualify it with its table"
        )
    return next(iter(owners.values())), None


def operations_from_sql(analysis, columns, data_source=DEFAULT_DATA_SOURCE):
    """``analyze_sql`` output + column types -> Insights operations.

    ``columns`` is ``{DocType: {column: data_type}}``, one entry per table the
    query touches. Returns ``{supported, operations, reasons}``. As everywhere in
    this integration, an unsupported query hands back NO operations: a partial
    list is a query that answers a different question.
    """
    if not isinstance(analysis, dict):
        raise TypeError("analysis must be the dict analyze_sql returns")
    reasons = list(analysis.get("reasons") or [])
    columns = columns or {}
    doctypes = [d for d in (analysis.get("doctypes") or []) if d]
    source = analysis.get("source_doctype") or (doctypes[0] if doctypes else None)
    join = analysis.get("join")

    if not source:
        reasons.append("no table found in this query")
    missing = [d for d in doctypes if not columns.get(d)]
    # Only when nothing else already explains the refusal — otherwise a query
    # rejected for a subquery also gets told its columns are unknown, which
    # buries the reason that matters.
    if missing and not reasons:
        reasons.append(
            f"the columns of {', '.join(missing)} are not known here, so nothing can "
            "be typed — Insights needs a data type on every grouping and measure"
        )
    if reasons:
        return {"supported": False, "operations": [], "reasons": reasons}

    tables = [source] + ([join["doctype"]] if join else [])
    # column -> {DocType: data_type}. A name in two tables is ambiguous, and the
    # ambiguity has to survive to the lookup rather than be flattened away here.
    available: dict[str, dict[str, str]] = {}
    for doctype in tables:
        for column, data_type in (columns.get(doctype) or {}).items():
            available.setdefault(column, {})[doctype] = data_type

    operations = [_source("tab" + source, data_source)]

    if join:
        join_columns = columns.get(join["doctype"]) or {}
        # The check that makes reading a join out of SQL safe: both names have to
        # be columns the DocTypes really have. A typo'd or misread one would
        # otherwise become a join that runs and answers a different question.
        for column, doctype, known in ((join["source_column"], source, columns.get(source) or {}),
                                       (join["join_column"], join["doctype"], join_columns)):
            if column not in known:
                reasons.append(f"the join condition uses '{column}', which is not a "
                               f"column of {doctype}")
        if not reasons:
            operations.append(_join(join["join_type"], "tab" + join["doctype"], data_source,
                                    join["source_column"], join["join_column"],
                                    sorted(join_columns)))

    for rule in analysis.get("filters") or []:
        operator = OPERATORS.get(str(rule.get("operator") or "").strip())
        if not operator:
            reasons.append(
                f"filter operator '{rule.get('operator')}' is not one this converter "
                "translates — it handles =, !=, >, >=, < and <="
            )
            continue
        data_type, problem = _type_of(rule, available, tables)
        if problem:
            reasons.append(problem)
            continue
        operations.append(_filter(str(rule.get("field")).strip(), operator,
                                  _value(rule.get("value"), data_type)))

    aggregations = analysis.get("aggregations") or []
    group_by = [g for g in (analysis.get("group_by") or []) if g.get("field")]
    if len(aggregations) > 1:
        reasons.append(
            f"this query has {len(aggregations)} aggregates — only one is translated"
        )
    elif aggregations:
        measures = _measures(aggregations[0], available, tables, reasons)
        dimensions = []
        for reference in group_by:
            data_type, problem = _type_of(reference, available, tables)
            if problem:
                reasons.append(problem)
                continue
            column = str(reference.get("field")).strip()
            if data_type not in DIMENSION_DATA_TYPES:
                reasons.append(
                    f"'{column}' is {data_type}, and Insights groups only by "
                    "text, a date or a time"
                )
                continue
            dimensions.append({"dimension_name": column, "column_name": column,
                               "data_type": data_type})
        if measures:
            operations.append(_summarize(measures, dimensions))
    elif group_by:
        reasons.append("this query groups without aggregating, which has no chart to draw")

    if reasons:
        return {"supported": False, "operations": [], "reasons": reasons}
    return {"supported": True, "operations": operations, "reasons": []}


def _measures(aggregation, available, tables, reasons):
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
    data_type, problem = _type_of({"field": argument, "table": aggregation.get("table")},
                                  available, tables)
    if problem:
        reasons.append(problem)
        return []
    if name in NUMERIC_ONLY_AGGREGATIONS and data_type not in MEASURE_DATA_TYPES:
        reasons.append(
            f"'{argument}' is {data_type}, and only a number can be {function}'d"
        )
        return []
    return [{
        "measure_name": f"{name}_of_{argument}",
        "column_name": argument,
        "data_type": "Integer" if name == "count" else data_type,
        "aggregation": name,
    }]
