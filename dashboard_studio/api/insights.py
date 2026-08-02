"""Hand a pasted SQL query to Frappe Insights as a real, queryable Query.

**Scope is deliberately narrow: create the Query, and optionally set two axes
on a chart for it.** Insights already has a chart editor — palette, reference
lines, curve toggles, labels — and Dashboard Studio is not rebuilding any of it.

**Insights v3 only.** v2 support was removed rather than branched on: the site is
permanently on v3, and two code paths where one is dead is how a wrong-version
payload gets written by the branch nobody exercises. The v2 DocTypes still ship
alongside v3, which is exactly why the old version guard was unsound —
``exists("DocType", "Insights Query")`` is True on a v3 site, so it passed and
then wrote an orphan record invisible to the v3 UI.

**The v3 shapes below are from a real record on the site, not from the docs.**

A query holds its SQL inside an ``operations`` JSON array, not in a field::

    [{"type": "sql", "raw_sql": "SELECT …", "data_source": "Site DB"}]

and belongs to a Workbook (a required Link), which is why this creates one.

A chart's ``config`` — read back from chart tt51l7mma3, chart_type "Line"::

    {"x_axis": {"dimension": {"column_name": "academic_year",
                              "data_type": "String",
                              "dimension_name": "academic_year"}},
     "y_axis": {"series": [{"measure": {"aggregation": "count",
                                        "column_name": "count",
                                        "data_type": "Integer",
                                        "measure_name": "count"},
                            "type": "line"}]}}

Note the ``data_type`` on both axes. v3 needs it and cannot be told to work it
out, and v3 **never persists a query's result** — confirmed live: zero
``Insights Query Result`` rows reference any v3 query. So the v2 trick of running
the query in Insights and reading the executed columns back has no v3
counterpart, and automatic axis application is gone with it. The types now come
from the only honest source available: a Metabase card's ``result_metadata``,
carried in by ``integrations.metabase.card.describe_card``. Without those, this
refuses and tells the person to set the axes in Insights.

**Security boundary, stated because it is a real one.** This writes SQL that
another app will execute. Dashboard Studio never runs it: the record is stored,
and Insights executes it later under Insights' own permissions and its own SQL
validation. That is the whole reason this endpoint refuses anything that is not
a single read-only statement — Studio must not be the thing that filed a DELETE.
It also means this route bypasses the DS Metric allowlist and approval gate by
design; it is a scratchpad for exploring a migrated query, and nothing published
as EduTrust evidence should come from it.
"""

import frappe

from dashboard_studio.api.studio import DS_READ_ROLES, DS_WRITE_ROLES

# The v3 DocTypes. Named once so the version assumption has a single home.
QUERY_DOCTYPE = "Insights Query v3"
CHART_DOCTYPE = "Insights Chart v3"
WORKBOOK_DOCTYPE = "Insights Workbook"

# Insights manages this data source itself and points it at the site's own
# database, so a query written here reaches the same tables ERPNext uses. The
# NAME is unchanged from v2 — confirmed live, v3 lists exactly "Site DB" — but
# the DocType holding it is not: v3 resolves a query's data_source against
# "Insights Data Source v3", and both tables exist side by side on this site.
SITE_DB = "Site DB"
SOURCE_DOCTYPE = "Insights Data Source v3"

# Creating an Insights Query needs an Insights role, which a Dashboard Studio
# Editor does not automatically hold. Checked explicitly so the refusal names the
# missing role instead of surfacing as a bare permission error.
INSIGHTS_ROLES = ("Insights User", "Insights Admin")

# Every query this app creates lands in one workbook, created on first use.
# Queries are not loose objects in v3 — `workbook` is a required Link — and a
# workbook per query would litter the Insights sidebar with singletons.
WORKBOOK_TITLE = "Dashboard Studio"

# Insights Query v3.title is a Frappe Data field: varchar(140). Frappe refuses
# an over-long value with "Value too big" and aborts the insert, so the title is
# trimmed to fit rather than allowed to cost somebody their query.
MAX_TITLE_LENGTH = 140

# CONFIRMED live in a browser on the v3 site: this is the route that loads the
# query. The v2 path (/insights/query/build/<name>) resolves to an empty shell —
# no error, just nothing — which is why the workbook id has to be carried
# through and returned rather than only the query name.
INSIGHTS_QUERY_PATH = "/insights/workbook/{workbook}/query/{name}"
DESK_QUERY_PATH = "/app/insights-query-v3/{name}"

# Our internal shape -> the exact string v3 stores in chart_type, and the series
# type inside y_axis.series[]. Only the axis-chart family: Bar and Line share the
# x_axis/y_axis config above, confirmed against a real record. Donut, Number and
# Table each have a different config shape, and guessing those is the mistake
# this scope exists to avoid.
AXIS_CHART_TYPES = {"bar": "Bar", "line": "Line"}
_SERIES_TYPE = {"Bar": "bar", "Line": "line"}

# v3's own vocabularies (query.types.ts). A dimension cannot be a number and a
# measure cannot be a date — these are not our rules, they are the ones the
# chart renderer applies.
DIMENSION_DATA_TYPES = ("String", "Date", "Datetime", "Time")
MEASURE_DATA_TYPES = ("Integer", "Decimal")

# A native query has already aggregated: `COUNT(*) AS count` produces one row per
# group. The chart still asks for an aggregation to apply over those rows, and
# "sum" of an already-grouped column is the identity — the only choice that
# cannot change the number. "count" would plot 1 for every group.
#
# CONFIRMED against Insights v3.12.2's own source, three ways, after the UI
# proved untestable through automation:
#
#   frontend/src2/types/query.types.ts
#     export const aggregations = ['sum', 'count', 'avg', 'min', 'max',
#                                  'count_distinct']
#   frontend/src2/query/helpers.ts — what Insights itself picks by default when
#   it turns a result column into a measure:
#     export function makeMeasure(column) {
#         return { aggregation: 'sum', … }
#   insights/insights/doctype/insights_data_source_v3/ibis_utils.py
#     if aggregate_function == "sum": return column.sum()
#     …
#     frappe.throw(f"Aggregate function {aggregate_function} is not supported")
#
# So this is not merely allowed, it is Insights' own default for exactly this
# step. The last line is worth knowing too: an unsupported value throws rather
# than drawing something wrong quietly, which is the one part of this config
# that fails loudly.
NATIVE_MEASURE_AGGREGATION = "sum"

# Metabase's base_type -> v3's data_type. Anything unlisted becomes String, which
# degrades safely: a String X axis is normal, and a String Y axis is refused by
# name below rather than charted.
BASE_TYPE_TO_DATA_TYPE = {
    "type/Integer": "Integer",
    "type/BigInteger": "Integer",
    "type/SmallInteger": "Integer",
    "type/Quantity": "Integer",
    "type/Float": "Decimal",
    "type/Decimal": "Decimal",
    "type/Number": "Decimal",
    "type/Date": "Date",
    "type/DateTime": "Datetime",
    "type/DateTimeWithTZ": "Datetime",
    "type/DateTimeWithLocalTZ": "Datetime",
    "type/Instant": "Datetime",
    "type/Time": "Time",
    "type/TimeWithTZ": "Time",
}

_READ_ONLY_STARTS = ("select", "with")


def clamp_title(name):
    """A title Insights will accept, or as much of one as fits.

    ``title`` is a Frappe Data field — varchar(140) — and Frappe refuses an
    over-long value with "Value too big", which aborts the whole insert. A title
    is cosmetic and a query is not, so this trims rather than letting a long name
    cost somebody their query.

    Real Metabase-compiled SQL is what surfaced this: its generated join aliases
    (``Quality Performance Actual Value Parameter Child_a3e4a16b``) are long
    enough that two or three of them blow the limit on their own.
    """
    name = " ".join(str(name or "").split())
    if len(name) <= MAX_TITLE_LENGTH:
        return name
    return name[: MAX_TITLE_LENGTH - 1].rstrip() + "…"


def query_title(analysis, sql=None):
    """A title for the Insights Query, from whatever the analysis managed.

    Degrades on purpose. The queries most worth handing to Insights are the ones
    the DS parser could NOT translate, so a title that only works for a clean
    parse would be missing exactly when it is needed.
    """
    analysis = analysis or {}
    doctypes = [d for d in (analysis.get("doctypes") or []) if d]
    group_by = [g for g in (analysis.get("group_by") or []) if g]
    aggregations = analysis.get("aggregations") or []
    function = str((aggregations[0] or {}).get("function") or "").title() if aggregations else ""

    if doctypes and len(doctypes) == 1 and group_by and function:
        return clamp_title(f"{function} of {doctypes[0]} by {group_by[0]}")
    if doctypes and len(doctypes) == 1:
        return clamp_title(f"{doctypes[0]} query")
    if len(doctypes) > 1:
        # Name the base table and COUNT the rest. Concatenating three table
        # names was fine for hand-written SQL and useless for compiled MBQL,
        # where a dozen generated aliases produce a title that is both
        # over-length and unreadable.
        return clamp_title(f"{sorted(doctypes)[0]} + {len(doctypes) - 1} more")
    return "Imported SQL query"


def sql_operations(sql):
    """The ``operations`` array v3 stores a native query in."""
    return [{"type": "sql", "raw_sql": sql, "data_source": SITE_DB}]


def operation_sql(operations):
    """The raw SQL out of an operations array, or None if it holds no SQL stage."""
    for operation in operations or []:
        if isinstance(operation, dict) and operation.get("type") == "sql":
            return operation.get("raw_sql")
    return None


def axis_columns(columns):
    """Metabase ``result_metadata`` -> [{name, data_type}] in v3's vocabulary.

    Frappe-free so the mapping is unit-testable. Anything with no known base_type
    becomes String, which is refused as a measure and allowed as a dimension.
    """
    out = []
    for column in columns or []:
        if not isinstance(column, dict):
            continue
        name = str(column.get("name") or "").strip()
        if not name:
            continue
        base = str(column.get("base_type") or "")
        out.append({"name": name, "data_type": BASE_TYPE_TO_DATA_TYPE.get(base, "String")})
    return out


def pick_series(columns, x, y, series=None):
    """Validate the colour breakdown column, or refuse — ``(series, reason)``.

    Never guessed. A third column in the result is not evidence that somebody
    wants it coloured by, and a chart that silently splits into 40 segments is
    worse than one that does not split at all. So this only ever confirms a
    column the caller asked for.
    """
    if not series:
        return None, None
    types = {c["name"]: c["data_type"] for c in columns}
    if series not in types:
        return None, (
            f"'{series}' is not a column this query returns, so it cannot be the "
            "colour breakdown. It returns: " + ", ".join(types) + "."
        )
    if series in (x, y):
        return None, (
            f"'{series}' is already the {'X axis' if series == x else 'Y axis'}, so "
            "it cannot also be the colour breakdown."
        )
    if types[series] not in DIMENSION_DATA_TYPES:
        return None, (
            f"'{series}' is a {types[series]}, and a colour breakdown has to be "
            "text, a date or a time — the same rule as the X axis."
        )
    return series, None


def pick_axes(columns, x_axis=None, y_axis=None):
    """Choose the two axes from the query's real columns, or refuse.

    Returns ``(x, y, reason)`` — reason is set only when it refuses.

    Frappe-free so the choice is unit-testable. The rules are v3's own:

    - a requested axis must be one of the columns the card actually returns.
      Studio's Step 2 guesses come from parsed SQL text, and an unaliased
      ``COUNT(*)`` is labelled differently in the result than in the SQL;
    - the Y axis must be Integer or Decimal — a measure cannot be anything else;
    - the X axis must be String, Date, Datetime or Time — a dimension cannot be
      a number.

    Refusing by name matters more here than it did under v2, because v3 will
    accept whatever config is written and simply draw nothing.
    """
    labels = [c["name"] for c in columns]
    if not labels:
        return None, None, (
            "Studio has no column types for this query, so it cannot set the axes "
            "safely. Set them in Insights — it knows the columns once you have run "
            "the query there."
        )
    types = {c["name"]: c["data_type"] for c in columns}
    numeric = [c["name"] for c in columns if c["data_type"] in MEASURE_DATA_TYPES]

    def known(value, axis):
        value = (value or "").strip()
        if not value:
            return None, None
        if value not in types:
            return None, (
                f"'{value}' is not a column this query returns, so it cannot be the "
                f"{axis} axis. It returns: " + ", ".join(labels) + "."
            )
        return value, None

    x, reason = known(x_axis, "X")
    if reason:
        return None, None, reason
    y, reason = known(y_axis, "Y")
    if reason:
        return None, None, reason

    if not y:
        if not numeric:
            return None, None, (
                "None of this query's columns is a number, so there is nothing to "
                "plot on the Y axis. They are: "
                + ", ".join(f"{c['name']} ({c['data_type']})" for c in columns)
                + ". Set this axis in Insights if one of them is a number it could "
                "not recognise."
            )
        y = numeric[0]
    elif types[y] not in MEASURE_DATA_TYPES:
        return None, None, (
            f"'{y}' is a {types[y]}, not a number, so plotting it on the Y axis "
            "would draw a chart that is wrong without saying so. Set this axis in "
            "Insights if you know better."
        )

    if not x:
        # The first column that is not the measure and can be a dimension.
        remaining = [label for label in labels
                     if label != y and types[label] in DIMENSION_DATA_TYPES]
        if not remaining:
            return None, None, (
                "This query has no column Insights can use as an X axis — a "
                "dimension has to be text, a date or a time. It returns: "
                + ", ".join(f"{c['name']} ({c['data_type']})" for c in columns) + "."
            )
        x = remaining[0]
    elif types[x] not in DIMENSION_DATA_TYPES:
        return None, None, (
            f"'{x}' is a {types[x]}, and Insights only puts text, dates or times on "
            "the X axis. Set this axis in Insights if you need a number there."
        )
    return x, y, None


def _dimension(name, data_type):
    """``dimension_name`` repeats the column name — that is what the real
    record does, and it is the label the chart shows."""
    return {"column_name": name, "data_type": data_type, "dimension_name": name}


def chart_config(x, y, x_type, y_type, series_type, split=None, split_type=None):
    """The v3 axis-chart config, in the shape read back from a real record.

    ``split`` is the colour breakdown — Insights calls it ``split_by``, and it
    is what turns one bar per x value into one bar split into a coloured segment
    per series value. Omitted entirely when there is none: v3 types it optional,
    and writing ``split_by: null`` asserts something the real record never says.
    """
    config = {
        "x_axis": {"dimension": _dimension(x, x_type)},
        "y_axis": {
            "series": [{
                "measure": {
                    "aggregation": NATIVE_MEASURE_AGGREGATION,
                    "column_name": y,
                    "data_type": y_type,
                    "measure_name": y,
                },
                "type": series_type,
            }]
        },
    }
    if split:
        config["split_by"] = {"dimension": _dimension(split, split_type)}
    return config


def _mask_sql(text):
    """``(masked, error)`` — the SQL with comments and string CONTENTS blanked.

    Same length as the input, so an offset in the mask is an offset in the
    original. The guard below reads this instead of the raw text, because both
    of its checks were being fooled by it: a leading comment hid the SELECT, and
    a semicolon inside a comment or a string looked like a second statement.

    **Quote-aware on purpose, and this is the whole security argument.** The
    obvious implementation — strip comments, then check — is a bypass::

        SELECT '/*' AS a FROM t; DROP TABLE t

    A stripper that does not know it is inside a string sees ``/*``, treats the
    rest as an unterminated comment, swallows the ``;`` and the ``DROP``, and the
    guard waves it through. Scanning left to right with quote state cannot do
    that.

    Every ambiguity resolves toward CODE, never toward comment. Mistaking a
    comment for code costs a false refusal; mistaking code for a comment hides a
    statement. So:

    - ``--`` starts a comment only when followed by whitespace or end of line,
      which is MySQL's actual rule — ``SELECT 1--2`` is arithmetic, not a comment;
    - ``/*!`` is MySQL's *executable* comment and really runs, so it is treated
      as code and will fail the SELECT check rather than being skipped;
    - an unterminated comment or string is an error, never "swallow to the end".

    ponytail: no ``#`` line comments. Recognising one would mean skipping its
    contents, which is the direction that hides things; not recognising it means
    a query starting with ``#`` is refused, which is merely annoying. Add it only
    with the same care as the rest.
    """
    out = []
    index, end = 0, len(text)
    while index < end:
        char = text[index]

        if char == "/" and text.startswith("/*", index):
            if text.startswith("/*!", index):
                out.append(char)          # executes; leave it as code
                index += 1
                continue
            close = text.find("*/", index + 2)
            if close == -1:
                return None, ("That query has a /* comment that is never closed, so "
                              "where the statement really begins cannot be told.")
            out.append(" " * (close + 2 - index))
            index = close + 2
            continue

        if (char == "-" and text.startswith("--", index)
                and (index + 2 >= end or text[index + 2] in " \t\r\n")):
            close = text.find("\n", index)
            close = end if close == -1 else close
            out.append(" " * (close - index))
            index = close
            continue

        if char in "'\"`":
            quote = char
            out.append(char)
            index += 1
            closed = False
            while index < end:
                inner = text[index]
                # Backticks quote identifiers and take no backslash escape.
                if inner == "\\" and quote != "`" and index + 1 < end:
                    out.append("  ")
                    index += 2
                    continue
                if inner == quote:
                    if index + 1 < end and text[index + 1] == quote:
                        out.append("  ")      # doubled quote, still inside
                        index += 2
                        continue
                    out.append(quote)
                    index += 1
                    closed = True
                    break
                out.append(" ")
                index += 1
            if not closed:
                return None, ("That query has a quote that is never closed, so it "
                              "cannot be read safely.")
            continue

        out.append(char)
        index += 1
    return "".join(out), None


def _normalised_sql(sql):
    """The SQL as it will be stored, or a refusal reason.

    Returns ``(sql, reason)`` — exactly one is set.

    ponytail: a start-of-statement check plus a no-second-statement check over a
    comment/string mask, not a SQL parser. Insights validates again before it
    executes, so this is the cheap outer guard whose only job is that Studio
    never writes a destructive statement into another app's record. Replace it
    with the real parser if this ever needs to allow more than SELECT.
    """
    text = (sql or "").strip()
    if not text:
        return None, "There is no SQL to send. Paste a query first."

    masked, error = _mask_sql(text)
    if error:
        return None, error

    # One trailing semicolon is ordinary; any other is a second statement. Cut it
    # by POSITION in the mask, so a semicolon inside a comment or a string is
    # neither mistaken for the terminator nor for a second statement.
    trimmed = masked.rstrip()
    if trimmed.endswith(";"):
        text = text[: len(trimmed) - 1].rstrip()
        masked = masked[: len(trimmed) - 1]
    if ";" in masked:
        return None, (
            "That looks like more than one statement. Send a single SELECT — "
            "Insights runs what is stored here."
        )

    statement = masked.lstrip("( \n\t\r")
    if not statement.strip():
        return None, ("There is no statement here — only a comment. Paste the "
                      "query itself as well.")
    if not statement.lower().startswith(_READ_ONLY_STARTS):
        return None, (
            "Only a SELECT (or WITH) query can be sent to Insights. This one starts "
            f"with '{statement.split()[0]}', and Dashboard Studio will not file a "
            "statement that writes."
        )
    return text, None


def _require_insights():
    """Refuse with the reason, before anything is written.

    Tests the **v3** DocType specifically. The old guard tested for the v2
    "Insights Query", which a v3 site still ships — so it passed on v3 and let a
    v2-shaped record be written where nothing would ever read it.
    """
    if not frappe.db.exists("DocType", QUERY_DOCTYPE):
        frappe.throw(
            f"Frappe Insights is not installed on this site, or is older than v3: "
            f"there is no '{QUERY_DOCTYPE}' DocType. Dashboard Studio supports "
            "Insights v3 only — v2 stored queries as 'Insights Query', with a "
            "different payload that this no longer writes."
        )
    roles = set(frappe.get_roles())
    if not roles & set(INSIGHTS_ROLES):
        frappe.throw(
            "Creating an Insights query needs the "
            + " or ".join(INSIGHTS_ROLES)
            + " role, which this account does not have. A Dashboard Studio Editor "
            "does not get it automatically — ask an administrator to add it."
        )
    # Against the v3 table, which is the one v3 resolves the query's data_source
    # against. This read the v2 "Insights Data Source" and passed only because
    # both tables happen to hold a row called "Site DB" — the same fault as the
    # version guard above, checking one generation to decide about the other. It
    # would have started refusing every create the moment the v2 records were
    # deleted, with a message blaming a source that was fine.
    if not frappe.db.exists(SOURCE_DOCTYPE, SITE_DB):
        frappe.throw(
            f"Insights has no '{SITE_DB}' data source on this site, so there is "
            "nothing to run the query against. It is the built-in source pointing "
            "at this site's own database; open Insights once to have it created."
        )


def _studio_workbook():
    """The default workbook, made on first use.

    v3 requires one — `workbook` is a reqd Link — so there is no version of this
    that skips it. Used when the caller names none.
    """
    existing = frappe.get_all(
        WORKBOOK_DOCTYPE, filters={"title": WORKBOOK_TITLE}, fields=["name"],
        order_by="creation asc", limit=1,
    )
    if existing:
        return existing[0]["name"]
    return frappe.get_doc({
        "doctype": WORKBOOK_DOCTYPE,
        "title": WORKBOOK_TITLE,
    }).insert().name


@frappe.whitelist()
def list_insights_workbooks():
    """The workbooks a query can be created in, newest activity first.

    Read-only. Returns the default's name separately so the picker can preselect
    it without having to know the title convention.
    """
    frappe.only_for(DS_READ_ROLES)
    _require_insights()
    rows = frappe.get_all(
        WORKBOOK_DOCTYPE, fields=["name", "title"], order_by="modified desc", limit=100,
    )
    return {
        "workbooks": [
            {"name": r["name"], "title": r.get("title") or r["name"]} for r in rows
        ],
        "default_title": WORKBOOK_TITLE,
    }


def _resolve_workbook(workbook):
    """The workbook to create in — the named one, or the default.

    The name is CHECKED, never trusted: it arrives from the browser, and
    `workbook` is a Link that Frappe would happily accept as a dangling
    reference on insert, leaving a query in a workbook that does not exist.
    """
    workbook = str(workbook or "").strip()
    if not workbook:
        return _studio_workbook()
    if not frappe.db.exists(WORKBOOK_DOCTYPE, workbook):
        frappe.throw(
            f"There is no Insights workbook '{workbook}'. Pick one from the list, "
            "or leave it unset to use the Dashboard Studio workbook."
        )
    return workbook


@frappe.whitelist()
def create_insights_query(sql: str, title: str = None, analysis=None, workbook: str = None):
    """Create (or reuse) a native Insights Query holding this SQL.

    ``workbook`` is the Insights workbook to create it in; without one it lands
    in the Dashboard Studio workbook, created on first use. Reuse is scoped to
    the chosen workbook — the same SQL filed deliberately into two workbooks is
    two queries, not a mistake to deduplicate away.

    Returns the record, its workbook, and two links: the Insights UI and the Desk
    form. Two, because only the second is provably correct on every install.
    """
    frappe.only_for(DS_WRITE_ROLES)
    _require_insights()

    text, reason = _normalised_sql(sql)
    if reason:
        frappe.throw(reason)

    if isinstance(analysis, str):
        analysis = frappe.parse_json(analysis)
    # Clamped HERE, on the resolved name, not inside query_title alone: a title
    # typed or edited in Studio reaches Insights by this same line and would hit
    # the same varchar(140) refusal. One clamp, where every title routes through.
    name = clamp_title((title or "").strip() or query_title(analysis, text))
    workbook = _resolve_workbook(workbook)

    # Reuse rather than pile up duplicates: clicking twice is the normal way to
    # find out whether the first click worked. Keyed on the SQL, because that is
    # what makes two queries the same query — the title is editable in Insights.
    #
    # ponytail: the SQL lives inside a JSON array, so this reads the workbook's
    # queries and compares in Python rather than filtering in SQL. One workbook's
    # worth of rows; if that ever gets large, store a hash in a field.
    for row in frappe.get_all(
        QUERY_DOCTYPE, filters={"workbook": workbook},
        fields=["name", "title", "operations"], limit=500,
    ):
        operations = row.get("operations")
        if isinstance(operations, str):
            operations = frappe.parse_json(operations)
        if operation_sql(operations) == text:
            return _result(row["name"], row.get("title") or name, workbook, reused=True)

    doc = frappe.get_doc({
        "doctype": QUERY_DOCTYPE,
        "workbook": workbook,
        "title": name,
        "is_native_query": 1,
        # What the Insights UI sets on every query it creates. For Site DB it
        # means the query runs against the site's own database rather than a
        # copy; getting it wrong fails visibly at Run rather than quietly.
        "use_live_connection": 1,
        "operations": frappe.as_json(sql_operations(text)),
    }).insert()
    return _result(doc.name, name, workbook, reused=False)


def _result(name, title, workbook, reused):
    return {
        "name": name,
        "title": title,
        "workbook": workbook,
        "reused": bool(reused),
        "data_source": SITE_DB,
        "insights_url": INSIGHTS_QUERY_PATH.format(workbook=workbook, name=name),
        "desk_url": DESK_QUERY_PATH.format(name=name),
    }


@frappe.whitelist()
def apply_insights_chart(query: str, chart_type: str = None, x_axis: str = None,
                         y_axis: str = None, columns=None, series: str = None):
    """Set the axes and type on this query's chart, creating the chart if needed.

    ``columns`` is a Metabase card's ``result_metadata`` as
    ``integrations.metabase.card.describe_card`` returns it — ``[{name,
    base_type}]``. It is the only source of per-column types this side has:
    **v3 never persists a query's result**, so unlike v2 there is nothing to read
    back after the person presses Run. Without columns this refuses; it does not
    guess a data_type, because v3 accepts whatever config is written and then
    draws nothing.

    Studio still never executes the SQL. Insights runs it; this only writes
    config.

    Unlike v2, v3 does NOT create a chart with the query, so this creates one if
    the query has none and updates it on every later call.
    """
    frappe.only_for(DS_WRITE_ROLES)
    _require_insights()

    kind = (chart_type or "bar").strip().lower()
    if kind not in AXIS_CHART_TYPES:
        frappe.throw(
            f"Studio can only set the axes for {', '.join(sorted(AXIS_CHART_TYPES.values()))} "
            f"charts, and this one is '{chart_type}'. Those two share one config "
            "shape that has been checked against a real record; Donut, Number and "
            "Table each use a different one. Set this chart up in Insights instead."
        )
    resolved_type = AXIS_CHART_TYPES[kind]

    if isinstance(columns, str):
        columns = frappe.parse_json(columns)
    mapped = axis_columns(columns)
    x, y, reason = pick_axes(mapped, x_axis, y_axis)
    if reason:
        frappe.throw(reason)
    split, reason = pick_series(mapped, x, y, (series or "").strip() or None)
    if reason:
        frappe.throw(reason)
    types = {c["name"]: c["data_type"] for c in mapped}

    doc = frappe.get_doc(QUERY_DOCTYPE, query)
    workbook = doc.get("workbook")
    config = frappe.as_json(chart_config(
        x, y, types[x], types[y], _SERIES_TYPE[resolved_type],
        split, types.get(split),
    ))

    existing = frappe.get_all(
        CHART_DOCTYPE, filters={"query": query}, fields=["name"],
        order_by="creation asc", limit=1,
    )
    if existing:
        chart_doc = frappe.get_doc(CHART_DOCTYPE, existing[0]["name"])
        chart_doc.chart_type = resolved_type
        chart_doc.config = config
        chart_doc.save()
        chart = chart_doc.name
    else:
        chart = frappe.get_doc({
            "doctype": CHART_DOCTYPE,
            "workbook": workbook,
            "query": query,
            "title": doc.get("title") or query,
            "chart_type": resolved_type,
            "config": config,
        }).insert().name

    return {
        "query": query,
        "workbook": workbook,
        "chart": chart,
        "chart_type": resolved_type,
        "x_axis": x,
        "y_axis": y,
        "series": split or "",
        "columns": mapped,
        "insights_url": INSIGHTS_QUERY_PATH.format(workbook=workbook, name=query),
    }
