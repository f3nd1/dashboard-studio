"""Hand a pasted SQL query to Frappe Insights as a real, queryable Query.

**Scope is deliberately one thing: create the Query.** No chart, no dashboard, no
workbook. Insights already has a chart editor — title, axes, reference line,
palette, curve toggles — and Dashboard Studio is not rebuilding any of it. Once
the Query exists, the person opens Insights and builds the chart there.

Chart *creation* is still not done here, and never will be: Insights creates the
chart itself in ``InsightsQuery.after_insert`` and links it as ``query.chart``.
``apply_insights_chart`` below UPDATES that record. Inserting a second one would
leave an orphan competing with the real one.

An earlier version of this note said chart config needs a ``data_type`` per axis
column. **That was read from Insights v3 and is wrong for v2**, which stores only
plain column labels — confirmed against a real record on this site. The v2
options shape is in ``_merge_chart_options``.

Verified against the site on 2026-07-26 (Insights **v2.2.3**): ``Insights Query``
carries the SQL in a plain ``sql`` field with ``is_native_query`` and a
``data_source`` Link. End-to-end confirmed live, not just in fixtures — a query
created by this endpoint (QRY-1310) opened in the Insights editor and executed
successfully. That also settles the one doubt the schema raised: ``sql`` is
marked read-only in the DocType JSON, but a plain insert populates it and
Insights runs it.

Insights v3 models the same thing completely differently — ``Insights Query v3``
requires a workbook and buries the SQL in an ``operations`` JSON array as
``{"type": "sql", "raw_sql": …}`` — so this module is v2-only and says so out
loud rather than half-supporting both. ``_require_insights`` names the version
problem if the DocType is absent.

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

from dashboard_studio.api.studio import DS_WRITE_ROLES

# The v2 DocType. Named once so the version assumption has a single home.
QUERY_DOCTYPE = "Insights Query"

# Insights manages this data source itself and points it at the site's own
# database, so a query written here reaches the same tables ERPNext uses. Its
# name is literally "Site DB" — enforced on the Insights side by "Only one site
# database can be configured".
SITE_DB = "Site DB"

# Creating an Insights Query needs an Insights role, which a Dashboard Studio
# Editor does not automatically hold. Checked explicitly so the refusal names the
# missing role instead of surfacing as a bare permission error.
INSIGHTS_ROLES = ("Insights User", "Insights Admin")

# CONFIRMED on this site (Insights v2.2.3, 2026-07-26): opening QRY-1308 at this
# path loaded the real chart editor. It is still a per-install value rather than
# a fact about Insights — a standalone v2 mounts its SPA at /insights, while a v3
# install running the legacy UI mounts it at /insights_v2 — so if this ever 404s
# after an upgrade, this constant is the only thing to change. The Desk URL below
# is derived from Frappe itself and is correct on any install, which is why both
# are still returned.
INSIGHTS_QUERY_PATH = "/insights/query/build/{name}"
DESK_QUERY_PATH = "/app/insights-query/{name}"

# Insights creates this itself, one per query, and links it as query.chart.
CHART_DOCTYPE = "Insights Chart"
RESULT_DOCTYPE = "Insights Query Result"

# Our internal shape -> the exact string v2 stores in Insights Chart.chart_type.
# Only the AxisChart family: these four share AxisChartOptions.vue, whose
# xAxis/yAxis shape is confirmed. Number, Pie, Table, Progress, Trend and Pivot
# Table each have their own options component with different keys, and guessing
# those is the mistake this scope exists to avoid.
AXIS_CHART_TYPES = {"bar": "Bar", "line": "Line", "row": "Row", "scatter": "Scatter"}

# The series type inside yAxis[].series_options. "bar" is confirmed from a real
# record; the rest are not.
#
# ponytail: only the two confirmed values are written. Row and Scatter get an
# empty series_options and let Insights fill its own default, because writing an
# unverified value into another app's config is the thing this whole handoff has
# refused from the start. Fill them in once a real record shows what they are.
_SERIES_TYPE = {"Bar": "bar", "Line": "line"}

# What get_columns_with_inferred_types can produce. Everything else — and
# anything it could not parse at all — comes back "String".
NUMERIC_COLUMN_TYPES = ("Integer", "Decimal")

_READ_ONLY_STARTS = ("select", "with")


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
        return f"{function} of {doctypes[0]} by {group_by[0]}"
    if doctypes and len(doctypes) == 1:
        return f"{doctypes[0]} query"
    if len(doctypes) > 1:
        return " + ".join(sorted(doctypes)[:3]) + " query"
    return "Imported SQL query"


def result_columns(results):
    """The column row of an executed query, as [{label, type}].

    Insights stores results as a JSON array whose FIRST ROW is the column
    metadata (``ResultColumn``: label, type, options) and whose remaining rows
    are data. Returns [] when there is nothing usable.
    """
    rows = results if isinstance(results, list) else []
    if not rows or not isinstance(rows[0], list):
        return []
    out = []
    for column in rows[0]:
        if not isinstance(column, dict):
            continue
        label = str(column.get("label") or "").strip()
        if label:
            out.append({"label": label, "type": str(column.get("type") or "String")})
    return out


def pick_axes(columns, x_axis=None, y_axis=None):
    """Choose the two axes from the REAL executed columns, or refuse.

    Returns ``(x, y, reason)`` — reason is set only when it refuses.

    Frappe-free so the choice is unit-testable. The rule is deliberately narrow:

    - a requested axis must be one of the labels the query actually returned.
      Studio's Step 2 guesses come from parsed SQL text, and an unaliased
      ``COUNT(*)`` is labelled differently in the result than in the SQL;
    - the Y axis must be Integer or Decimal. Everything else is refused BY NAME.

    That second rule is the whole safety story. Insights infers these types from
    the returned VALUES (pandas, priority String > Datetime > Decimal > Integer),
    not from the database, and String wins — so one unparseable value, an
    all-NULL column, or a duration rendered as "3 days 04:00:00" makes the whole
    column String. Charting such a column as a Y axis produces a wrong picture
    with no error, so this refuses instead and says which column and why.
    """
    labels = [c["label"] for c in columns]
    if not labels:
        return None, None, ("This query has no result columns to read. Run it in "
                            "Insights first, then try again.")
    types = {c["label"]: c["type"] for c in columns}
    numeric = [c["label"] for c in columns if c["type"] in NUMERIC_COLUMN_TYPES]

    def known(value, axis):
        value = (value or "").strip()
        if not value:
            return None, None
        if value not in types:
            return None, (
                f"'{value}' is not a column this query returned, so it cannot be the "
                f"{axis} axis. It returned: " + ", ".join(labels) + "."
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
                "None of this query's columns came back numeric, so there is nothing "
                "to plot on the Y axis. Insights read them as: "
                + ", ".join(f"{c['label']} ({c['type']})" for c in columns)
                + ". Set the axes in Insights if one of these is a number it could "
                "not recognise."
            )
        y = numeric[0]
    elif types[y] not in NUMERIC_COLUMN_TYPES:
        return None, None, (
            f"Insights read '{y}' as {types[y]}, not a number, so plotting it on the "
            "Y axis would draw a chart that is wrong without saying so. A column reads "
            "as String when it is empty, mixed, or a computed value like a duration. "
            "Set this axis in Insights if you know better."
        )

    if not x:
        # The first column that is not the measure. Whatever it is, it is a
        # label; a String X axis is normal and not refused.
        remaining = [label for label in labels if label != y]
        if not remaining:
            return None, None, (
                "This query returned only one column, so there is nothing to put on "
                "the X axis."
            )
        x = remaining[0]
    return x, y, None


def _merge_chart_options(existing, x, y, series_type):
    """The v2 options shape, preserving everything we do not own.

    Confirmed against a real record on this site:

        {"xAxis": [{"column": "student_category"}],
         "yAxis": [{"column": "count", "series_options": {"type": "bar"}}],
         "rotateLabels": "0", "title": …, "colors": [...], "query": "QRY-1321"}

    xAxis is an ARRAY, not an object. Only xAxis and yAxis are replaced —
    colors, rotateLabels, title and anything else a person set in Insights are
    carried through untouched, because this runs on a chart they may already
    have styled.
    """
    merged = dict(existing or {})
    merged["xAxis"] = [{"column": x}]
    merged["yAxis"] = [{"column": y, "series_options": {"type": series_type} if series_type else {}}]
    return merged


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
    """Refuse with the reason, before anything is written."""
    if not frappe.db.exists("DocType", QUERY_DOCTYPE):
        frappe.throw(
            f"Frappe Insights is not installed on this site, or is a version without "
            f"the '{QUERY_DOCTYPE}' DocType. This handoff supports Insights v2; v3 "
            "stores queries as 'Insights Query v3' and needs a different payload."
        )
    roles = set(frappe.get_roles())
    if not roles & set(INSIGHTS_ROLES):
        frappe.throw(
            "Creating an Insights query needs the "
            + " or ".join(INSIGHTS_ROLES)
            + " role, which this account does not have. A Dashboard Studio Editor "
            "does not get it automatically — ask an administrator to add it."
        )
    if not frappe.db.exists("Insights Data Source", SITE_DB):
        frappe.throw(
            f"Insights has no '{SITE_DB}' data source on this site, so there is "
            "nothing to run the query against. It is the built-in source pointing "
            "at this site's own database; open Insights once to have it created."
        )


@frappe.whitelist()
def create_insights_query(sql: str, title: str = None, analysis=None):
    """Create (or reuse) a native Insights Query holding this SQL.

    Returns the record and two links: the Insights UI and the Desk form. Two,
    because only the second is provably correct on every install — see
    INSIGHTS_QUERY_PATH.
    """
    frappe.only_for(DS_WRITE_ROLES)
    _require_insights()

    text, reason = _normalised_sql(sql)
    if reason:
        frappe.throw(reason)

    if isinstance(analysis, str):
        analysis = frappe.parse_json(analysis)
    name = (title or "").strip() or query_title(analysis, text)

    # Reuse rather than pile up duplicates: clicking twice is the normal way to
    # find out whether the first click worked. Keyed on the SQL, because that is
    # what makes two queries the same query — the title is editable in Insights.
    #
    # ponytail: exact-text match, so whitespace differences make a new record.
    # Normalising SQL properly needs a parser and this is a convenience, not a
    # correctness rule.
    existing = frappe.get_all(
        QUERY_DOCTYPE,
        filters={"is_native_query": 1, "sql": text},
        fields=["name", "title"],
        limit=1,
    )
    if existing:
        return _result(existing[0]["name"], existing[0].get("title") or name, reused=True)

    doc = frappe.get_doc({
        "doctype": QUERY_DOCTYPE,
        "title": name,
        "is_native_query": 1,
        "data_source": SITE_DB,
        "sql": text,
    }).insert()
    return _result(doc.name, name, reused=False)


def _result(name, title, reused):
    return {
        "name": name,
        "title": title,
        "reused": bool(reused),
        "data_source": SITE_DB,
        "insights_url": INSIGHTS_QUERY_PATH.format(name=name),
        "desk_url": DESK_QUERY_PATH.format(name=name),
    }


@frappe.whitelist()
def apply_insights_chart(query: str, chart_type: str = None, x_axis: str = None,
                         y_axis: str = None):
    """Set the axes and type on the chart Insights already made for this query.

    Runs AFTER the person has executed the query in Insights, and reads the real
    column labels and inferred types from the stored result. Studio still never
    executes the SQL — ``InsightsQuery.run`` is whitelisted and deliberately not
    called here, because "Studio files it, Insights runs it" is the boundary this
    whole handoff is built on. No result yet means a refusal, not an execution.

    Updates ``query.chart``; never inserts. Insights creates that chart itself in
    after_insert and deletes it on trash, so a second one would be an orphan
    competing with the real record.
    """
    frappe.only_for(DS_WRITE_ROLES)
    _require_insights()

    kind = (chart_type or "bar").strip().lower()
    if kind not in AXIS_CHART_TYPES:
        frappe.throw(
            f"Studio can only set the axes for {', '.join(sorted(AXIS_CHART_TYPES.values()))} "
            f"charts, and this one is '{chart_type}'. Those four share one options "
            "shape that has been checked against a real record; the others do not. "
            "Set this chart up in Insights instead."
        )
    resolved_type = AXIS_CHART_TYPES[kind]

    doc = frappe.get_doc(QUERY_DOCTYPE, query)
    chart = doc.get("chart")
    if not chart:
        frappe.throw(
            f"'{query}' has no chart linked. Insights normally creates one with the "
            "query; open the query in Insights once and try again."
        )

    stored = frappe.get_all(
        RESULT_DOCTYPE, filters={"query": query}, fields=["name"], limit=1
    )
    if not stored:
        frappe.throw(
            "This query has not been run yet, so Insights does not know what columns "
            "it returns. Open it in Insights, press Run, then come back."
        )
    results = frappe.get_doc(RESULT_DOCTYPE, stored[0]["name"]).get("results")
    if isinstance(results, str):
        results = frappe.parse_json(results)

    columns = result_columns(results)
    x, y, reason = pick_axes(columns, x_axis, y_axis)
    if reason:
        frappe.throw(reason)

    chart_doc = frappe.get_doc(CHART_DOCTYPE, chart)
    options = chart_doc.get("options")
    if isinstance(options, str):
        options = frappe.parse_json(options) or {}
    chart_doc.chart_type = resolved_type
    chart_doc.options = frappe.as_json(
        _merge_chart_options(options, x, y, _SERIES_TYPE.get(resolved_type))
    )
    chart_doc.save()

    return {
        "query": query,
        "chart": chart,
        "chart_type": resolved_type,
        "x_axis": x,
        "y_axis": y,
        "columns": columns,
        "insights_url": INSIGHTS_QUERY_PATH.format(name=query),
    }
