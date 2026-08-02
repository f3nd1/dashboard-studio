"""Turn one Metabase card's JSON into the fields the Visualize tab needs.

Frappe-free on purpose, so the whole translation is unit-testable without a
Bench and without touching Metabase. ``client.fetch_card`` does the network part;
this does the reading.

**Why this exists.** The alternative is a person copying SQL out of Metabase's
editor by hand, and then Studio guessing the title, the axes and the chart type
back out of that SQL text. The card already knows all four. Reading them is a
translation between two known JSON shapes instead of a parse.

**The shape, confirmed live against UCC's Metabase (v1.62.5.1, 2026-07-28).**
This version serialises ``dataset_query`` as MBQL 5 (the MLv2 pipeline form),
not the classic ``{"type": "native", "native": {"query": …}}`` that Metabase's
published TypeScript types still describe::

    {"lib/type": "mbql/query",
     "database": 2,
     "lib.convert/converted?": true,
     "stages": [{"lib/type": "mbql.stage/native", "native": "SELECT …"}]}

``lib.convert/converted?`` is set by Metabase's own legacy-to-MBQL5 converter on
the way out; it means "normalised", not "altered". The SQL is a plain string on
the stage, under ``native``.

Note the top-level ``lib/type`` reads ``mbql/query`` for EVERY card, GUI or
native alike — the distinction lives one level down, on the stage. Reading the
top level is what makes a native card look like a GUI one. Of UCC's 2,003 cards,
227 are native.

**Flag-don't-guess, same contract as parser.py.** Everything this cannot read
safely sets ``supported: False`` with a named reason rather than returning a
half-translation. A silently wrong axis is worse than no axis: the person would
have to notice the chart is wrong, and the whole point of reading the card was
that they no longer have to check.
"""

from __future__ import annotations

# Reused, not re-written: one definition of "what a Frappe table looks like in
# SQL". A second regex here could drift from the parser's and quietly disagree
# about which tables a query reads.
from dashboard_studio.integrations.metabase.parser import TABLE_PATTERN

# Metabase `display` -> the chart type Studio's Visualize step offers.
#
# Studio's list is bar/line/donut/number/table (studio_core.INSIGHTS_CHART_TYPES)
# and this maps only what carries the same meaning. pie->donut and
# scalar/smartscalar->number are the same encoding drawn differently; a
# smartscalar loses its trend comparison, which Studio has no equivalent for.
#
# Everything else — area, combo, row, pivot, gauge, progress, funnel, object,
# map, scatter, boxplot, waterfall, sankey, treemap, list, and any `custom:*`
# plugin — has no honest equivalent and is refused BY NAME. Mapping row to bar
# would silently flip the orientation the person chose in Metabase.
DISPLAY_TO_CHART_TYPE = {
    "table": "table",
    "bar": "bar",
    "line": "line",
    "pie": "donut",
    "scalar": "number",
    "smartscalar": "number",
}

# Where the axes live in visualization_settings, per display family. Values are
# arrays of result-column names for graph.*, and a bare name for pie.*.
_AXIS_SETTINGS = (
    ("graph.dimensions", "graph.metrics"),
    ("pie.dimension", "pie.metric"),
)

_NATIVE_STAGE = "mbql.stage/native"

# Metabase substitutes these before it runs the query; the stored text is not
# valid SQL. `{{x}}` is a template tag or a `{{#123-card}}` reference, `[[...]]`
# an optional clause. Insights would store it happily and fail on Run.
_TEMPLATE_MARKERS = ("{{", "[[")


def _at(value, index=0):
    """A settings value that may be a bare name or an array of them.

    ``graph.dimensions`` is an array precisely because a chart can have two: the
    X axis and the colour breakdown. Index 1 is that second one.
    """
    if isinstance(value, (list, tuple)):
        value = value[index] if len(value) > index else None
    elif index:
        return None
    value = str(value or "").strip()
    return value or None


def _columns(card):
    """``result_metadata`` as [{name, display_name, base_type}].

    Returned VERBATIM, with no type translation. The eventual destination is
    Insights v3's per-axis ``data_type``, and that shape is not confirmed yet —
    inventing a mapping now would bake in a guess exactly where the last two
    rounds of this work went wrong.
    """
    out = []
    for column in card.get("result_metadata") or []:
        if not isinstance(column, dict):
            continue
        name = str(column.get("name") or "").strip()
        if not name:
            continue
        out.append({
            "name": name,
            "display_name": str(column.get("display_name") or name),
            "base_type": str(column.get("base_type") or ""),
        })
    return out


def _sql_and_reasons(card):
    """``(sql, reasons)`` — the native SQL, or why there is none to take."""
    query = card.get("dataset_query")
    if not isinstance(query, dict):
        return None, ["this card has no dataset_query to read"]

    stages = query.get("stages")
    if not isinstance(stages, list):
        # Either a Metabase old enough to serialise the legacy shape, or
        # something else entirely. Named rather than papered over: supporting
        # both shapes on speculation is how the last wrong assumption survived.
        return None, [
            "this card's dataset_query has no 'stages' — it is not the MBQL 5 "
            "shape this reader understands"
        ]
    if not stages:
        return None, ["this card's dataset_query has no stages at all"]
    if len(stages) > 1:
        # A native stage with MBQL stages on top of it: Metabase's "explore
        # these results", and models built on a native query. Taking stage 0's
        # SQL alone would drop the filtering or aggregation layered above it and
        # hand over a query that answers a different question.
        return None, [
            f"this card runs in {len(stages)} stages — the SQL is only the first "
            "of them, and the steps built on top of it cannot be translated"
        ]

    stage = stages[0] if isinstance(stages[0], dict) else {}
    if stage.get("lib/type") != _NATIVE_STAGE:
        return None, [
            "this is a GUI-built question, not a SQL one, so there is no query "
            "text to import"
        ]

    sql = str(stage.get("native") or "").strip()
    if not sql:
        return None, ["this card is a native query but its SQL is empty"]

    reasons = []
    if stage.get("template-tags"):
        reasons.append(
            "this query uses Metabase variables, which Metabase fills in before "
            "it runs — the stored text is not runnable SQL on its own"
        )
    elif any(marker in sql for marker in _TEMPLATE_MARKERS):
        # Belt and braces: the tags dict is the authority, but a `{{#123-card}}`
        # reference to another question can appear without one.
        reasons.append(
            "this query contains {{…}} or [[…]] placeholders that Metabase fills "
            "in before it runs, so the stored text is not runnable SQL"
        )
    return sql, reasons


def referenced_tables(card, table_names=None):
    """Every physical table a card reads -> ``(tables, unresolved)``.

    Built for one job: deciding which tables a read-only database login has to
    be granted SELECT on. That job sets the error direction — **over-inclusion
    is safe, under-inclusion silently breaks a dashboard** — so this errs toward
    naming more tables, not fewer, and reports anything it could not resolve
    rather than dropping it.

    ``table_names`` maps Metabase's numeric table id to the physical table name,
    as ``GET /api/table`` returns it. Without it, MBQL cards resolve to nothing
    and every one of them lands in ``unresolved``.

    ponytail: the MBQL side is a recursive scan for ``source-table`` /
    ``source-card`` keys rather than a walk of the documented stage/join
    nesting. MBQL 5 puts a join's source inside the join's own ``stages``, and
    that shape has moved between versions — a scan cannot miss a table by
    looking in the wrong place, and finding one somewhere unexpected costs a
    surplus GRANT, which is the harmless direction here.
    """
    if not isinstance(card, dict):
        raise TypeError("card must be the decoded JSON of one Metabase card")
    table_names = table_names or {}
    tables, unresolved = set(), []
    label = f"card {card.get('id')}"

    sql, _ = _sql_and_reasons(card)
    if sql:
        found = TABLE_PATTERN.findall(sql)
        if found:
            tables.update("tab" + name.strip() for name in found if name.strip())
        else:
            # Native SQL naming its tables some other way — a different quoting
            # style, or a database that is not this Frappe site.
            unresolved.append(f"{label}: native SQL with no `tab…` table reference")
        return tables, unresolved

    ids, cards = _scan_sources(card.get("dataset_query"))
    for table_id in sorted(ids):
        name = table_names.get(table_id) or table_names.get(str(table_id))
        if name:
            tables.add(name)
        else:
            unresolved.append(f"{label}: table id {table_id} not in the table list")
    for other in sorted(cards):
        # A question built on another question. Its tables belong to that card,
        # which this inventory reaches on its own pass — named so a reader can
        # see the dependency rather than wonder why the card contributed none.
        unresolved.append(f"{label}: built on card {other}, counted there")
    if not ids and not cards:
        unresolved.append(f"{label}: no source-table anywhere in dataset_query")
    return tables, unresolved


def _scan_sources(node, ids=None, cards=None):
    """Every source-table / source-card id anywhere in the structure."""
    ids = set() if ids is None else ids
    cards = set() if cards is None else cards
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "source-table" and isinstance(value, int):
                ids.add(value)
            elif key == "source-card" and isinstance(value, int):
                cards.add(value)
            else:
                _scan_sources(value, ids, cards)
    elif isinstance(node, list):
        for item in node:
            _scan_sources(item, ids, cards)
    return ids, cards


def describe_card(card):
    """One Metabase card -> what Visualize can use, or named refusals.

    Returns ``{card_id, title, sql, display, chart_type, x_axis, y_axis,
    columns, supported, reasons}``. ``supported`` is False whenever ``reasons``
    is non-empty, and the caller must not use any of the other fields then.
    """
    if not isinstance(card, dict):
        raise TypeError("card must be the decoded JSON of one Metabase card")

    sql, reasons = _sql_and_reasons(card)

    display = str(card.get("display") or "").strip().lower()
    chart_type = DISPLAY_TO_CHART_TYPE.get(display)
    if not chart_type:
        reasons.append(
            f"Metabase draws this as '{display or 'nothing'}', which Studio has no "
            "equivalent for. It offers "
            + ", ".join(sorted(set(DISPLAY_TO_CHART_TYPE.values())))
            + "."
        )

    columns = _columns(card)
    if not columns:
        # Metabase writes result_metadata when the card is saved or run. Without
        # it there is no column list to check the axes against.
        #
        # ponytail: this catches MISSING metadata, not STALE metadata. Metabase
        # exposes nothing to date it against the SQL, so a card whose query was
        # edited without re-running can name columns it no longer returns. The
        # axes below are checked against this list, which bounds the damage to
        # "a stale name is dropped, not imported wrong". A real freshness check
        # would need Metabase to run the query, which is exactly what this must
        # never ask it to do.
        reasons.append(
            "Metabase has no stored column list for this card, so its axis "
            "settings cannot be checked. Open it in Metabase and run it once."
        )

    settings = card.get("visualization_settings")
    settings = settings if isinstance(settings, dict) else {}
    known = {column["name"] for column in columns}
    x_axis = y_axis = series = None
    for dimension_key, measure_key in _AXIS_SETTINGS:
        x_axis = x_axis or _at(settings.get(dimension_key))
        y_axis = y_axis or _at(settings.get(measure_key))
        # The second dimension is the colour breakdown — the thing that makes
        # one bar per x value split into a segment per series value.
        series = series or _at(settings.get(dimension_key), 1)
    # An axis naming a column the card does not return is dropped, not imported
    # and not refused: Step 2 already has a "nothing to guess from" state, and a
    # blank the person fills in beats a name that charts the wrong column.
    x_axis = x_axis if x_axis in known else None
    y_axis = y_axis if y_axis in known else None
    series = series if series in known and series != x_axis else None

    return {
        "card_id": card.get("id"),
        "title": str(card.get("name") or "").strip() or "Imported Metabase card",
        "sql": sql or "",
        "display": display,
        "chart_type": chart_type or "",
        "x_axis": x_axis or "",
        "y_axis": y_axis or "",
        "series": series or "",
        "columns": columns,
        "supported": not reasons,
        "reasons": reasons,
    }
