"""A Metabase card's chart settings + our operations -> an Insights chart config.

Frappe-free and unit-testable, like the rest of the translation. The input is
the sidecar `metabase_export_sql.py` writes beside each exported `.sql` — the
card's `series_settings`, its card-level `display`, and its id — plus the
operations `sql_ops` just produced. The output is the `config` blob an
`Insights Chart v3` stores, or nothing at all with a reason.

**Read this before loosening anything here.** The rest of the converter refuses
when it cannot translate; this one DEGRADES instead, to a chart Insights would
have built anyway. That is deliberate and it is not a softening of the refusal
rule: a wrong chart config is visible the moment somebody looks at the chart —
bars where a line belongs — whereas a wrong query returns a number nobody can
tell is wrong. So the cost of being wrong here is different in kind, and the
fallback is Part 3's "check this manually" flag rather than a blocked
conversion. What is NOT allowed is inventing a bar/line split that Metabase did
not state.

The shapes come from Insights' own source at the installed tag v3.12.2 —
`frontend/src2/types/chart.types.ts`:

    AxisChartConfig = { x_axis: XAxis; y_axis: YAxis; split_by?: SplitBy }
    XAxis           = { dimension: Dimension; label_rotation?: number }
    YAxis           = { series: Series[]; ... }
    Series          = { measure: Measure; type?: 'line' | 'bar';
                        align?: 'Left' | 'Right'; name?: string; ... }

`Dimension` and `Measure` are exactly what a `summarize` operation already
holds, so the axes are lifted from it rather than rebuilt — a rebuilt measure
that disagreed with the one in the query would chart a column the query does
not produce.
"""

import re

# Metabase's per-series display vocabulary, from its own source:
# `frontend/src/metabase/visualizations/lib/settings/series.ts` gives
# `{value: "line"}, {value: "area"}, {value: "bar"}`.
#
# Only two are translated. Insights' `Series.type` is `'line' | 'bar'` and
# nothing else; an `area` series is a line with `show_area`, which is a
# DIFFERENT field and a fill nobody asked this converter to reproduce. Anything
# unlisted — area, and whatever Metabase adds next — falls back rather than
# being bent into the nearest match.
_DISPLAY_TO_TYPE = {"bar": "bar", "line": "line"}

_TYPE_TO_CHART = {"bar": "Bar", "line": "Line"}

# Every Metabase display this translates, and the Insights chart type it lands
# on. The names are Insights' own CHARTS list in `chart.types.ts` — CHARTS =
# ['Number', 'Bar', 'Line', 'Row', 'Donut', 'Funnel', 'Table', ...] — and each
# family's REQUIREMENTS come from `charts/chart.ts`'s own validation at
# v3.12.2, read rather than recalled:
#
#   AXIS_CHARTS ('Bar','Line','Row')  x_axis.dimension required
#   'Number'                          number_columns non-empty
#   'Donut' / 'Funnel'                label_column + value_column required
#   'Table'                           rows non-empty ("Rows are required")
#
# The same file shows a chart REBUILDS its query from this config at render
# time (`addNumberChartOperation` runs `addSummarize({measures:
# number_columns, ...})`), so a config that names anything the query does not
# produce is a chart that errors on open — which is why every builder below
# lifts its columns from the summarize rather than composing them.
#
# Left unmapped ON PURPOSE, falling back to the manual-check flag: `gauge`,
# `object`, `pivot`, `combo`, `area`, `map`. Insights has no gauge/object;
# pivot needs a pivot_wider this converter does not emit; combo computes its
# split from array position (nothing stored to read); area is a line plus a
# fill field nobody stated; map needs region mappings. Approximating any of
# them would be a chart that renders and says something else.
_AXIS_DISPLAYS = {"bar": "Bar", "line": "Line", "row": "Row"}
_SIMPLE_DISPLAYS = {"scalar": "Number", "smartscalar": "Number",
                    "pie": "Donut", "funnel": "Funnel", "table": "Table"}

# Every series goes on the LEFT axis, always.
#
# Metabase stores `axis` only when somebody overrode it; its default is `null`,
# meaning Auto, and the split is then decided at RENDER time by
# `graph.y_axis.auto_split`. The QIPI card confirmed that from real data —
# neither of its two series carries an `axis` key at all, though the chart
# plainly has two axes. So there is nothing here to read, and a right-axis
# assignment would be this converter's invention rather than the card's
# intention. Left for everything; the reader moves one series across in the
# chart's own gear menu, which is one click.
_ALIGN = "Left"


# A date part that is a NUMBER rather than a date: month-of-year pools every
# January, so it is 12 rows and genuinely not a date. Insights' chart X axis
# offers only date-compatible columns, so grouping by one converts correctly and
# cannot be charted — ADR-024 records why regrouping it silently would answer a
# different question.
#
# `year` is deliberately absent: ADR-024 emits it as a granularity on the date
# column itself, which stays chartable, so it never reaches a mutate.
_UNCHARTABLE_PARTS = ("month", "quarter", "day")


def date_part_grouping(operations):
    """``{part, column, dimension}`` when the chart's X axis is a date NUMBER.

    Not a refusal and not a blocker: the query converts, the numbers are right,
    and a chart is built. It simply cannot be charted in Insights, and the fix —
    regrouping by year — is a different question that only a person may choose.
    So this REPORTS the condition and never acts on it.
    """
    dimensions = {str(d.get("column_name")) for d in _measures_and_dimensions(operations)[1]}
    for operation in operations or []:
        if not isinstance(operation, dict) or operation.get("type") != "mutate":
            continue
        name = str(operation.get("new_name") or "")
        if name not in dimensions:
            continue
        text = str((operation.get("expression") or {}).get("expression") or "")
        for part in _UNCHARTABLE_PARTS:
            if text.startswith(part + "("):
                return {"part": part, "dimension": name,
                        "column": text[len(part) + 1:].rstrip(")").strip(),
                        "entangled": _date_part_entangled(operations, part)}
    return None


def _date_part_entangled(operations, part):
    """Does anything besides a bare ``part(col)`` grouping consume this part?

    Mirrors `datePartEntangled` in studio_core.js — the two must agree, or the
    corpus scan sizes a one-click fix the page will not offer. A part feeding a
    label expression (`case(month(d) == 1, '01-Jan', ...)`) cannot survive the
    regroup substitution: regrouped to year it compares 2024 against 1..12 and
    labels every row NULL, found live. Entangled means the one-click does not
    apply and the report is a hand edit.
    """
    pure = re.compile(r"^" + re.escape(part) + r"\(\w+\)$")
    for operation in operations or []:
        if not isinstance(operation, dict) or operation.get("type") != "mutate":
            continue
        text = str((operation.get("expression") or {}).get("expression") or "")
        if part + "(" in text and not pure.match(text):
            return True
    return False


def _measures_and_dimensions(operations):
    """The summarize's own `measures` and `dimensions`, or `([], [])`."""
    for operation in operations or []:
        if isinstance(operation, dict) and operation.get("type") == "summarize":
            return (list(operation.get("measures") or []),
                    list(operation.get("dimensions") or []))
    return [], []


def _entry_for(measure, ordinal, settings, reasons):
    """The `series_settings` entry naming this measure, or `{}`.

    Metabase keys a series by its own result column name. For a compiled
    question that is the aggregate's SELECT alias, which Metabase writes as the
    bare function name — the real QIPI card carries exactly `avg` and `count`,
    while this converter names the same two measures `avg_of_<column>` and
    `count`. So the two are matched on the AGGREGATION, which both sides state.

    Two measures sharing a function are told apart by POSITION, because that is
    Metabase's own rule rather than a guess: its aliases for repeated functions
    are `avg`, `avg_2`, `avg_3` — literal result-column names, numbered in SQL
    order, observed across the full corpus. So the Nth same-function measure
    (SQL order, which is the order this list holds) takes the key `<func>` for
    N=1 and `<func>_<N>` after that. Only those two spellings match; `avg_x`,
    `teacher_1` and a numbered key past the group's size match nothing.

    `ordinal` is None for a measure that exists only as a COMPONENT of an
    expression over aggregates (ADR-011). Metabase numbers its own result
    columns, and a component never was one — its output column is the
    expression's — so a component takes no key and does not count in the
    numbering. A same-function key pointed at one refuses the whole card by
    name, because styling a component as if it were a result column puts the
    label and the line on a series Metabase never drew.
    """
    wanted = str(measure.get("aggregation") or "").strip().lower()
    if not wanted:
        return {}
    if ordinal is None:
        pointed = [key for key in settings
                   if str(key).strip().lower() == wanted
                   or re.fullmatch(re.escape(wanted) + r"_\d+",
                                   str(key).strip().lower())]
        if pointed:
            reasons.append(
                f"the '{pointed[0]}' series setting names a '{wanted}' aggregate "
                "that exists here only inside a computed expression — Metabase "
                "numbers its own result columns, so the two cannot be lined up. "
                "Build the chart by hand.")
        return {}
    spellings = {wanted} if ordinal == 1 else {f"{wanted}_{ordinal}"}
    named = [value for key, value in settings.items()
             if str(key).strip().lower() in spellings]
    if not named:
        return {}
    entry = named[0]
    return entry if isinstance(entry, dict) else {}


def chart_config_from_card(card, operations):
    """``(config, chart_type, reason)`` — the chart to create, or why not.

    `config` is None whenever anything is missing or ambiguous, and `reason`
    then says so in a sentence meant for the person reading the conversion
    result. Both are returned rather than raising: not building a chart is an
    ordinary outcome here, not a failure of the conversion.
    """
    card = card if isinstance(card, dict) else {}
    settings = card.get("series_settings")
    settings = settings if isinstance(settings, dict) else {}
    display = str(card.get("display") or "").strip().lower()

    measures, dimensions = _measures_and_dimensions(operations)
    if not measures:
        return None, None, "the query produces no measures, so there is no chart to build"
    if display in _SIMPLE_DISPLAYS:
        return _simple_chart(_SIMPLE_DISPLAYS[display], measures, dimensions)
    if display not in _AXIS_DISPLAYS:
        return None, None, (
            f"Metabase drew this card as '{display or 'nothing recorded'}', which "
            "this converter does not translate into a chart type")
    # One dimension is one X axis. Two would need a `split_by`, and deciding
    # which is the axis and which the colour breakdown changes what it says.
    if len(dimensions) != 1:
        return None, None, (
            f"the query groups by {len(dimensions)} columns, and a chart needs "
            "exactly one for its X axis — build this one in Insights by hand")

    # Each measure's ordinal within its own function group, in this list's
    # order — which is SQL order, the order Metabase numbers by. A measure
    # that exists only inside an expression gets None: it is not a Metabase
    # result column, so it neither takes a key nor counts in the numbering.
    components = _expression_components(operations)
    seen = {}
    ordinals = []
    for measure in measures:
        if measure.get("measure_name") in components:
            ordinals.append(None)
            continue
        key = str(measure.get("aggregation") or "").strip().lower()
        seen[key] = seen.get(key, 0) + 1
        ordinals.append(seen[key])

    series, matched, reasons = [], [], []
    for measure, ordinal in zip(measures, ordinals):
        entry = _entry_for(measure, ordinal, settings, reasons)
        if reasons:
            return None, None, reasons[0]
        item = {"measure": dict(measure), "align": _ALIGN}
        if display == "row":
            # A Row chart has no per-series type — Metabase's own UI hides the
            # display control for row cards (`getHidden` in its series.ts
            # admits only line/area/bar/combo), so a stored `display` on one is
            # a leftover Metabase itself does not render, and this reads the
            # card the way Metabase does. Insights' Row renderer defaults the
            # series type, so none is written.
            pass
        else:
            # The card-level display is what a series inherits when it carries
            # no `display` of its own — the QIPI card is `display: "line"` with
            # only `count` overridden to bar, and that override is the point.
            raw = str(entry.get("display") or "").strip().lower() or display
            if raw not in _DISPLAY_TO_TYPE:
                return None, None, (
                    f"Metabase drew one series as '{raw}', which this converter "
                    "does not translate into a chart type")
            item["type"] = _DISPLAY_TO_TYPE[raw]
        # Metabase's own label. Absent, Insights falls back to the measure name,
        # which is this converter's name rather than the report's.
        label = str(entry.get("title") or "").strip()
        if label:
            item["name"] = label
        if entry:
            matched.append(measure.get("measure_name"))
        series.append(item)

    # Settings that exist but describe NOTHING this query produces — custom
    # series keys like `teacher_1` — abandon the chart. Building it anyway
    # would silently drop every setting somebody stored, which is a chart that
    # renders and is not the one they configured. An EMPTY settings dict is the
    # opposite case and builds fine: the card-level display alone is still
    # Metabase's own, and the chart type is the win.
    if settings and not matched:
        keys = ", ".join(sorted(str(k) for k in settings)[:3])
        return None, None, (
            f"this card's series settings are keyed by names this query does "
            f"not produce ({keys}) — nothing could be matched, so the chart is "
            "left for a person to build")

    config = {"x_axis": {"dimension": dict(dimensions[0])},
              "y_axis": {"series": series}}
    return config, _AXIS_DISPLAYS[display], None


def _expression_components(operations):
    """Measure names an ADR-011 expression mutate reads — the measures that are
    components of a computed column rather than result columns of their own.
    Only mutates AFTER the summarize qualify: those are the ones whose
    expressions are written over measure names."""
    past_summarize = False
    found = set()
    for operation in operations or []:
        if not isinstance(operation, dict):
            continue
        if operation.get("type") == "summarize":
            past_summarize = True
            measures = operation.get("measures") or []
        elif past_summarize and operation.get("type") == "mutate":
            text = str((operation.get("expression") or {}).get("expression") or "")
            for measure in measures:
                name = str(measure.get("measure_name") or "")
                if name and re.search(r"\b" + re.escape(name) + r"\b", text):
                    found.add(name)
    return found


def _simple_chart(chart_type, measures, dimensions):
    """A chart with no X axis or a fixed slot layout — Number, Donut, Funnel,
    Table. Each requirement below is `chart.ts`'s own validation, so a config
    this refuses to emit is one Insights would reject on open.

    `series_settings` is deliberately not read here: it describes AXIS series
    (type, axis side), and none of these charts has either. A label on a Number
    or Donut lives in the measure name, which is the query's to define.
    """
    if chart_type == "Number":
        # `addNumberChartOperation` summarizes by `date_column` alone, so a
        # grouped query cannot be said as a Number without dropping or guessing
        # the grouping — and a scalar card's query does not group.
        if dimensions:
            return None, None, (
                f"Metabase drew this card as a single number, but the query "
                f"groups by {len(dimensions)} column(s) — a Number chart would "
                "drop the grouping, so it is left for a person to build")
        return ({"number_columns": [dict(m) for m in measures],
                 "number_column_options": [{} for _ in measures],
                 "comparison": False, "sparkline": False},
                "Number", None)
    if chart_type in ("Donut", "Funnel"):
        if len(dimensions) != 1 or len(measures) != 1:
            return None, None, (
                f"a {chart_type} chart takes exactly one label column and one "
                f"value — this query produces {len(dimensions)} grouping(s) "
                f"and {len(measures)} measure(s)")
        return ({"label_column": dict(dimensions[0]),
                 "value_column": dict(measures[0])},
                chart_type, None)
    # Table. `chart.ts` demands non-empty rows, so an ungrouped query has
    # nothing to put there.
    if not dimensions:
        return None, None, (
            "a Table chart needs at least one row grouping, and this query "
            "groups by nothing")
    return ({"rows": [dict(d) for d in dimensions], "columns": [],
             "values": [dict(m) for m in measures]},
            "Table", None)
