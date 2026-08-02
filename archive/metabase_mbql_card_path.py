"""Metabase MBQL 5 -> Frappe Insights v3 operations.

Frappe-free and metadata-injected, so the whole translation is unit-testable
without a Bench and without touching Metabase.

**Read ADR-006 before changing anything here.** This was rejected once and then
reopened deliberately, with a condition: *a converted query is not trustworthy
until a person has compared its number against Metabase's*. That condition is
not decoration. Translation makes Dashboard Studio the authority on what a
question computes, and a translation that disagrees produces a different number
with **no error** — the fault `docs/SOPHIA_FAULT_PATTERN.md` names, "they do not
fail, they disagree." The verification gate in `api/convert.py` is the only
thing standing between that and a published figure. Do not weaken it, and do not
add a rule here that makes the translator look more capable than its checking.

**Both formats were read from source, at the versions actually installed.** The
first attempt at this died because both ends were assumed:

- Metabase MBQL 5 (``lib/schema.cljc``, ``lib/schema/join.cljc``,
  ``lib/schema/ref.cljc``). A stage carries ``source-table``, ``filters``
  (plural), ``aggregation``, ``breakout``, ``joins``, ``expressions``,
  ``fields``, ``order-by``, ``limit``. A field ref is ``[:field opts id]`` —
  **options at position 1, identifier at position 2**, which is the reversal
  that broke the first attempt. A join is ``{lib/type, stages, conditions,
  alias, strategy}`` and its source table lives inside its own ``stages``.
- Insights v3.12.2 (``frontend/src2/types/query.types.ts``). Operations are
  ``source`` / ``filter`` / ``join`` / ``summarize``, with the arg shapes in
  ``_source``, ``_filter``, ``_join`` and ``_summarize`` below.

**Flag-don't-guess, harder than elsewhere in this repo.** Everything not on the
rule table refuses by name. A refusal costs a person the manual path they
already have; a wrong translation costs them a number they believe.
"""

from __future__ import annotations

# Insights writes queries against this data source; see api/insights.SITE_DB.
DEFAULT_DATA_SOURCE = "Site DB"

# MBQL comparison operator -> Insights FilterOperator. Only the ones that mean
# the same thing on both sides. MBQL's :between, :contains, :starts-with and the
# rest exist in Insights too, but their argument shapes have not been read from
# a real card, and a filter that selects different rows is a different number.
OPERATORS = {"=": "=", "!=": "!=", ">": ">", ">=": ">=", "<": "<", "<=": "<="}

# MBQL join strategy -> Insights JoinType. MBQL defaults to :left-join when the
# key is absent, which is Metabase's own default, not an assumption of ours.
JOIN_TYPES = {
    "left-join": "left",
    "right-join": "right",
    "inner-join": "inner",
    "full-join": "full",
}
DEFAULT_JOIN_STRATEGY = "left-join"

# MBQL aggregation -> Insights AggregationType. Insights accepts exactly
# sum/count/avg/min/max/count_distinct (ibis_utils.apply_aggregate throws on
# anything else), so this is the whole overlap.
AGGREGATIONS = {
    "count": "count",
    "sum": "sum",
    "avg": "avg",
    "min": "min",
    "max": "max",
    "distinct": "count_distinct",
}

# A bare :count has no column. Insights' own count measure names the column
# "count" (frontend/src2/query/helpers.ts), so this matches what Insights does
# to itself rather than inventing a convention.
COUNT_COLUMN = "count"

DIMENSION_DATA_TYPES = ("String", "Date", "Datetime", "Time")
MEASURE_DATA_TYPES = ("Integer", "Decimal")

# Aggregations that need a number to work on. Counting is not one of them:
# count_distinct of a text column is an ordinary thing to want, and Insights'
# MeasureDataType allows String precisely because of it.
NUMERIC_ONLY_AGGREGATIONS = ("sum", "avg", "min", "max")

# What the aggregation RETURNS, where that is fixed regardless of the column it
# reads. `data_type` on a measure is the result type — Insights' own count
# measure is Integer while makeMeasure carries the column's type through for
# sum, and both are the type of the number that ends up on the axis.
AGGREGATION_RESULT_TYPES = {"count": "Integer", "count_distinct": "Integer"}

# Stage keys this translator does not handle. Each one changes which rows or
# which columns come back, so ignoring any of them would silently produce a
# different number.
UNSUPPORTED_STAGE_KEYS = {
    "expressions": "a custom column",
    "fields": "an explicit column selection",
    "order-by": "a sort",
    "limit": "a row limit",
    "page": "pagination",
    "pivot": "a pivot",
    "source-card": "a question built on another question",
}


def _keyword(value):
    """Clojure keywords arrive over JSON as ':foo' or 'foo' depending on the
    serialiser. Normalised once so no rule has to care which."""
    text = str(value or "")
    return text[1:] if text.startswith(":") else text


def _clause(node):
    """``[tag opts & args]`` -> ``(tag, args)``, or ``(None, [])``.

    MBQL 5 puts the options map at position 1. Reading position 1 as the first
    argument — as legacy MBQL allowed — is exactly the mistake that made the
    first attempt parse nothing.
    """
    if not isinstance(node, list) or not node:
        return None, []
    return _keyword(node[0]), list(node[2:])


def _column(ref, metadata, reasons, what):
    """A field ref -> ``{"name", "data_type"}``, or None with a named reason."""
    tag, args = _clause(ref)
    if tag != "field" or not args:
        reasons.append(f"{what} is not a plain field reference")
        return None
    ident = args[0]
    if isinstance(ident, str):
        # A native-stage or already-named column: no metadata to look up, and
        # no type either, so it can be a dimension but never a measure.
        return {"name": ident, "data_type": "String"}
    field = (metadata.get("fields") or {}).get(ident)
    if not field:
        reasons.append(f"{what} refers to Metabase field {ident}, which is not in the metadata")
        return None
    # A temporal bucket (month/quarter/year) changes the values a breakout
    # returns. Insights has `granularity` for this, but its allowed values were
    # not read from source, so bucketed columns refuse rather than silently
    # grouping by raw timestamp — which would be a different chart entirely.
    opts = ref[1] if len(ref) > 1 and isinstance(ref[1], dict) else {}
    if opts.get("temporal-unit") or opts.get(":temporal-unit"):
        reasons.append(
            f"{what} is grouped by a date bucket "
            f"({_keyword(opts.get('temporal-unit') or opts.get(':temporal-unit'))}), "
            "which this converter does not translate"
        )
        return None
    return {"name": field["name"], "data_type": field.get("data_type") or "String"}


def _table(table_id, metadata, reasons, what):
    table = (metadata.get("tables") or {}).get(table_id)
    if not table:
        reasons.append(f"{what} is Metabase table {table_id}, which is not in the metadata")
        return None
    return table["name"]


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


def _translate_filters(stage, metadata, reasons):
    out = []
    for clause in stage.get("filters") or []:
        tag, args = _clause(clause)
        operator = OPERATORS.get(tag)
        if not operator or len(args) != 2:
            reasons.append(f"filter '{tag}' is not a simple comparison this converter handles")
            continue
        column = _column(args[0], metadata, reasons, f"the '{tag}' filter's column")
        if not column:
            continue
        value = args[1]
        if isinstance(value, list):
            reasons.append(
                f"the '{tag}' filter compares two fields rather than a field to a value"
            )
            continue
        out.append(_filter(column["name"], operator, value))
    return out


def _translate_joins(stage, metadata, reasons, data_source):
    out = []
    for join in stage.get("joins") or []:
        if not isinstance(join, dict):
            reasons.append("a join is not a map")
            continue
        stages = join.get("stages") or []
        if len(stages) != 1:
            reasons.append("a join runs in more than one stage, which cannot be translated")
            continue
        table_name = _table(stages[0].get("source-table"), metadata, reasons, "a joined table")
        if not table_name:
            continue
        strategy = _keyword(join.get("strategy") or DEFAULT_JOIN_STRATEGY)
        join_type = JOIN_TYPES.get(strategy)
        if not join_type:
            reasons.append(f"join strategy '{strategy}' has no Insights equivalent")
            continue
        conditions = join.get("conditions") or []
        if len(conditions) != 1:
            reasons.append(
                f"a join has {len(conditions)} conditions — only a single equality is translated"
            )
            continue
        tag, args = _clause(conditions[0])
        if tag != "=" or len(args) != 2:
            reasons.append("a join condition is not a simple equality")
            continue
        left = _column(args[0], metadata, reasons, "a join condition's left side")
        right = _column(args[1], metadata, reasons, "a join condition's right side")
        if not left or not right:
            continue
        # Insights needs the columns to keep from the joined table. MBQL's
        # :fields is :all / :none / an explicit list; anything but :all would
        # mean reproducing Metabase's column selection, which is not read here.
        fields = join.get("fields")
        if fields is not None and _keyword(fields) != "all":
            reasons.append(
                "a join selects specific columns, which this converter does not reproduce"
            )
            continue
        columns = (metadata.get("table_columns") or {}).get(stages[0].get("source-table"))
        if not columns:
            reasons.append(f"the columns of joined table '{table_name}' are not in the metadata")
            continue
        out.append(_join(join_type, table_name, data_source, left["name"], right["name"], columns))
    return out


def _translate_summarize(stage, metadata, reasons):
    aggregations = stage.get("aggregation") or []
    breakout = stage.get("breakout") or []
    if not aggregations and not breakout:
        return []
    if not aggregations:
        reasons.append("this question groups without aggregating, which has no chart to draw")
        return []

    measures = []
    for clause in aggregations:
        tag, args = _clause(clause)
        aggregation = AGGREGATIONS.get(tag)
        if not aggregation:
            # The ratio/arithmetic shape — [:* [:/ [:count-where …] [:count]] 100].
            # Named as the compound expression it is, because this is the case
            # most likely to be a metric somebody cares about.
            reasons.append(
                f"aggregation '{tag or 'unknown'}' is a compound or custom expression, "
                "not a simple aggregate"
            )
            continue
        if not args:
            if aggregation != "count":
                reasons.append(f"aggregation '{tag}' has no column to aggregate")
                continue
            measures.append({"measure_name": COUNT_COLUMN, "column_name": COUNT_COLUMN,
                             "data_type": "Integer", "aggregation": "count"})
            continue
        column = _column(args[0], metadata, reasons, f"the '{tag}' aggregation's column")
        if not column:
            continue
        if (aggregation in NUMERIC_ONLY_AGGREGATIONS
                and column["data_type"] not in MEASURE_DATA_TYPES):
            reasons.append(
                f"'{column['name']}' is {column['data_type']}, and only a number can be "
                f"{tag}'d"
            )
            continue
        measures.append({
            "measure_name": f"{aggregation}_of_{column['name']}",
            "column_name": column["name"],
            "data_type": AGGREGATION_RESULT_TYPES.get(aggregation, column["data_type"]),
            "aggregation": aggregation,
        })

    dimensions = []
    for ref in breakout:
        column = _column(ref, metadata, reasons, "a group-by column")
        if not column:
            continue
        if column["data_type"] not in DIMENSION_DATA_TYPES:
            reasons.append(
                f"'{column['name']}' is {column['data_type']}, and Insights groups only by "
                "text, a date or a time"
            )
            continue
        dimensions.append({"dimension_name": column["name"], "column_name": column["name"],
                           "data_type": column["data_type"]})

    if not measures:
        return []
    return [_summarize(measures, dimensions)]


def translate_card(card, metadata, data_source=DEFAULT_DATA_SOURCE):
    """One Metabase card -> ``{supported, reasons, operations, tables}``.

    ``metadata`` is Frappe-free and injected::

        {"tables":        {<table id>: {"name": "tabStudent Applicant"}},
         "fields":        {<field id>: {"name": "status", "data_type": "String"}},
         "table_columns": {<table id>: ["name", "status", …]}}

    ``supported`` is False whenever ``reasons`` is non-empty, and the caller must
    not use ``operations`` then — a partial operation list is a query that
    answers a different question, which is the whole hazard here.
    """
    if not isinstance(card, dict):
        raise TypeError("card must be the decoded JSON of one Metabase card")
    reasons = []
    query = card.get("dataset_query")
    if not isinstance(query, dict):
        return _result(False, [], ["this card has no dataset_query to read"])

    stages = query.get("stages")
    if not isinstance(stages, list) or not stages:
        return _result(False, [], [
            "this card's dataset_query has no 'stages' — it is not the MBQL 5 shape "
            "this converter understands"
        ])
    if len(stages) > 1:
        return _result(False, [], [
            f"this card runs in {len(stages)} stages; only the first would be translated, "
            "and the steps built on top of it change the answer"
        ])

    stage = stages[0] if isinstance(stages[0], dict) else {}
    kind = _keyword(stage.get("lib/type"))
    if kind == "mbql.stage/native":
        return _result(False, [], [
            "this is a native SQL card — send it through the SQL path, which needs no "
            "translation at all"
        ])
    if kind and kind != "mbql.stage/mbql":
        return _result(False, [], [f"unknown stage type '{kind}'"])

    for key, description in UNSUPPORTED_STAGE_KEYS.items():
        if stage.get(key):
            reasons.append(f"this question uses {description}, which this converter cannot translate")

    table_name = _table(stage.get("source-table"), metadata, reasons, "the source table")
    if not table_name:
        return _result(False, [], reasons or ["this question has no source table"])

    operations = [_source(table_name, data_source)]
    operations.extend(_translate_joins(stage, metadata, reasons, data_source))
    operations.extend(_translate_filters(stage, metadata, reasons))
    operations.extend(_translate_summarize(stage, metadata, reasons))
    return _result(not reasons, operations, reasons)


def _result(supported, operations, reasons):
    return {
        "supported": bool(supported) and not reasons,
        "operations": operations if supported and not reasons else [],
        "reasons": reasons,
    }
