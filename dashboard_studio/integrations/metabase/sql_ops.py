"""Pasted SQL -> Insights v3 operations. The only translator in the app.

Paste the query, get Select Source / Join Table / Filter Rows / Group &
Summarize — a report that stays clickable in Insights' own editor instead of
being a block of SQL nobody can edit. The Metabase card-id route that used to
sit alongside this was removed; it is in ``archive/metabase_mbql_card_path.py``
with its client and tests.

**Where the line is, concretely.** `parser.analyze_sql` already draws most of it
and this narrows it further:

  works      one table, or any number joined each on a single `a.col = b.col`
             equality; WHERE with AND-ed comparisons, GROUP BY, one COUNT/SUM/AVG
             aggregate
  refused    subqueries, CROSS joins, the same table joined twice, an ON clause
             that is anything but a single equality of two qualified columns,
             OR, UNION, HAVING, CASE, DISTINCT, window functions, more than one
             aggregate, LIKE and IN

**A join carries the columns the query READS, not the whole table.** Insights'
``select_columns`` was every column of the joined table, which meant any
disagreement about any column — even one nothing referenced — broke the report
when it was opened. Two live failures came in that way. Now it is exactly what
the filters, groupings, aggregates and join conditions name.

**How a join is translated, and where it stops.** `analyze_sql` reads each ON
clause into two *named, table-oriented* columns — ``join_column`` always belongs
to the table being joined and ``source_column`` to one already in scope — which
is exactly what Insights' ``join_condition`` means, and why N joins are N
operations rather than a harder problem than one. Both names are then checked
against the real columns of their DocType here, so a column that does not exist
refuses rather than being written into a query that runs and answers something
else. Everything the orientation cannot be certain about (an unqualified side, a
compound ON, a self join) refuses back in the parser, by name.

**The one thing SQL cannot supply is types**, and Insights needs a ``data_type``
on every dimension and measure. They come from Frappe's own DocType metadata —
the tables are ``tab<DocType>``, so the site already knows what every column is. That is the
injected ``columns`` argument — ``{DocType: {column: data_type}}``, one entry per
table the query touches — and without it nothing is translated: a guessed type
draws a chart that is wrong without saying so. It doubles as the check that
makes joins safe: every column name read out of the SQL has to be one the
DocType really has.

Nothing converted here is trustworthy until a person has compared its number
against the original. See ADR-007 — that condition is why translating is allowed
at all.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# The Insights v3 side, read from source at the installed version
# (v3.12.2, ``frontend/src2/types/query.types.ts``). These shapes and the
# constants above them came from the MBQL card-path translator, which was
# archived when the card-id route was removed; they are here now because this is
# the only path that builds operations. Do not adjust a shape without reading
# that file — a key Insights does not recognise is dropped silently, and the
# query then answers a different question without failing.
# ---------------------------------------------------------------------------

# Insights writes queries against this data source; see api/insights.SITE_DB.
DEFAULT_DATA_SOURCE = "Site DB"

# SQL comparison operator -> Insights FilterOperator. Only the ones that mean
# the same thing on both sides. BETWEEN, LIKE and IN exist in Insights too, but
# their argument shapes have not been read from a real query, and a filter that
# selects different rows is a different number.
OPERATORS = {"=": "=", "!=": "!=", ">": ">", ">=": ">=", "<": "<", "<=": "<="}

# What Insights accepts: ibis_utils.apply_aggregate throws on anything else.
INSIGHTS_AGGREGATIONS = ("sum", "count", "avg", "min", "max", "count_distinct")

# A bare COUNT has no column. Insights' own count measure names the column
# "count" (frontend/src2/query/helpers.ts), so this matches what Insights does
# to itself rather than inventing a convention.
COUNT_COLUMN = "count"

DIMENSION_DATA_TYPES = ("String", "Date", "Datetime", "Time")
MEASURE_DATA_TYPES = ("Integer", "Decimal")

# Aggregations that need a number to work on. Counting is not one of them:
# count_distinct of a text column is an ordinary thing to want, and Insights'
# MeasureDataType allows String precisely because of it.
NUMERIC_ONLY_AGGREGATIONS = ("sum", "avg", "min", "max")


def _source(table_name, data_source):
    return {"type": "source",
            "table": {"type": "table", "data_source": data_source, "table_name": table_name}}


def _filter(column, operator, value):
    return {"type": "filter",
            "column": {"type": "column", "column_name": column},
            "operator": operator,
            "value": value}


def _join(join_type, table_name, data_source, left, right, select_columns):
    return {
        "type": "join",
        "join_type": join_type,
        "table": {"type": "table", "data_source": data_source, "table_name": table_name},
        "select_columns": [{"type": "column", "column_name": c} for c in select_columns],
        "join_condition": {
            "left_column": {"type": "column", "column_name": left},
            "right_column": {"type": "column", "column_name": right},
        },
    }


def _summarize(measures, dimensions):
    return {"type": "summarize", "measures": measures, "dimensions": dimensions}


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


# The framework columns Frappe puts on EVERY table, which no DocType lists among
# its fields — `frappe.get_meta(...).fields` returns the ones somebody defined,
# so without this seed a join on `parent` refuses as "not a column of X" on a
# child table where `parent` is the only column a join can use.
STANDARD_COLUMNS = {
    "name": "String",
    "owner": "String",
    "creation": "Datetime",
    "modified": "Datetime",
    "modified_by": "String",
    "docstatus": "Integer",
    "idx": "Integer",
    "parent": "String",
    "parentfield": "String",
    "parenttype": "String",
}

# Frappe's OPTIONAL columns — its own name for them. They are not created on
# every table, so they are typed here but never assumed present: a live
# conversion succeeded in Studio and then failed in Insights with "Column
# '_comments' is not found in table", on a table carrying the ten above and none
# of these four. Only `valid_columns` below decides whether they exist.
OPTIONAL_COLUMNS = {
    "_user_tags": "String",
    "_comments": "String",
    "_assign": "String",
    "_liked_by": "String",
    "_seen": "String",
}


def columns_from_meta(meta_fields, valid_columns=None):
    """Frappe DocType fields -> ``{column_name: data_type}``.

    ``meta_fields`` is ``[(fieldname, fieldtype), …]`` — passed in rather than
    read here, so this module stays Frappe-free and testable.

    ``valid_columns`` is the table's REAL column list, read from the database by
    the caller. When given it is authoritative in both directions: a framework
    column the table does not have is dropped, and a column that exists without
    a DocField (the underscore ones) is kept. It also drops the DocType fields
    that are not columns at all — Section Break, Column Break, HTML — which have
    fieldnames and would otherwise look like columns you could group by.

    Without it, only the unconditional columns are assumed. Guessing which
    optional ones exist is what produced a query Insights refused to run.
    """
    columns = dict(STANDARD_COLUMNS)
    for fieldname, fieldtype in meta_fields or []:
        if fieldname:
            columns[fieldname] = FIELDTYPE_TO_DATA_TYPE.get(fieldtype, "String")
    if valid_columns is None:
        return columns
    known = dict(OPTIONAL_COLUMNS)
    known.update(columns)
    return {column: known.get(column, "String") for column in valid_columns}


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


def _referenced_columns(analysis, available):
    """``{DocType: {column, …}}`` — the columns this query actually uses.

    A join's ``select_columns`` used to be every column of the joined table, and
    that is what turned an unrelated schema disagreement into a broken report:
    the Quality Performance query reads three columns from its child table and
    was carrying all twenty-two, two of which Insights did not think existed.
    Neither was used by anything. The query failed on open over columns nobody
    had asked for.

    So a join now carries what the query references and nothing else. That is
    not a workaround for one stale table — it is the difference between "any
    column of any joined table disagreeing breaks the report" and "a column
    this query actually reads disagrees", which is a real error worth refusing
    on rather than noise to survive.

    Unresolvable references are skipped here; the main pass refuses on them by
    name, and this must not duplicate that.
    """
    used: dict[str, set] = {}

    def note(column, table):
        column = str(column or "").strip()
        owners = available.get(column) or {}
        if table and table in owners:
            used.setdefault(table, set()).add(column)
        elif not table and len(owners) == 1:
            used.setdefault(next(iter(owners)), set()).add(column)

    for rule in analysis.get("filters") or []:
        note(rule.get("field"), rule.get("table"))
    for reference in analysis.get("group_by") or []:
        note(reference.get("field"), reference.get("table"))
    for aggregation in analysis.get("aggregations") or []:
        note(aggregation.get("argument"), aggregation.get("table"))
    # Both sides of every join condition, including a later join attaching to an
    # earlier joined table — that column has to come across too.
    for join in analysis.get("joins") or []:
        used.setdefault(join["doctype"], set()).add(join["join_column"])
        used.setdefault(join["source_table"], set()).add(join["source_column"])
    return used


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
    joins = analysis.get("joins") or []

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

    tables = [source] + [j["doctype"] for j in joins]
    # column -> {DocType: data_type}. A name in two tables is ambiguous, and the
    # ambiguity has to survive to the lookup rather than be flattened away here.
    available: dict[str, dict[str, str]] = {}
    for doctype in tables:
        for column, data_type in (columns.get(doctype) or {}).items():
            available.setdefault(column, {})[doctype] = data_type

    referenced = _referenced_columns(analysis, available)
    operations = [_source("tab" + source, data_source)]

    # One Insights join operation per JOIN, in the order they were written: each
    # attaches its table to the result built so far, which is what Insights'
    # join_condition.left_column means.
    for join in joins:
        join_columns = columns.get(join["doctype"]) or {}
        # The check that makes reading a join out of SQL safe: both names have to
        # be columns the DocTypes really have. A typo'd or misread one would
        # otherwise become a join that runs and answers a different question.
        for column, doctype, known in (
            (join["source_column"], join["source_table"],
             columns.get(join["source_table"]) or {}),
            (join["join_column"], join["doctype"], join_columns),
        ):
            if column not in known:
                reasons.append(f"the join condition uses '{column}', which is not a "
                               f"column of {doctype}")
        if reasons:
            break
        # What the query reads from this table, not everything the table has.
        # Every name here is still one the schema confirmed — `referenced` is
        # built from `available`, which is built from the validated columns.
        operations.append(_join(join["join_type"], "tab" + join["doctype"], data_source,
                                join["source_column"], join["join_column"],
                                sorted(referenced.get(join["doctype"], set()))))

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
    if not name or name not in INSIGHTS_AGGREGATIONS:
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
    # An explicit `* 1` in the SQL is Metabase casting the column to a number
    # before aggregating it. Where the column really is text that cast is the
    # only reason the report works at all, so it is honoured rather than refused
    # — but it is recorded, not waved through: `coerced_from` travels with the
    # measure and the UI says so, because every row that is not a number becomes
    # 0 and nothing about the converted query would otherwise show that. The
    # proper fix is the Frappe field's type; see ADR-009.
    coerced = bool(aggregation.get("coerced")) and data_type not in MEASURE_DATA_TYPES
    if name in NUMERIC_ONLY_AGGREGATIONS and data_type not in MEASURE_DATA_TYPES:
        if not coerced:
            reasons.append(
                f"'{argument}' is {data_type}, and only a number can be {function}'d"
            )
            return []
    measure = {
        "measure_name": f"{name}_of_{argument}",
        "column_name": argument,
        "data_type": "Integer" if name == "count" else ("Decimal" if coerced else data_type),
        "aggregation": name,
    }
    if coerced:
        measure["coerced_from"] = data_type
    return [measure]
