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

# Insights' own chart types for an axis chart: AXIS_CHARTS = ['Bar','Line','Row'].
# 'Row' is a sideways bar and Metabase spells that 'row', which is not in the
# display map above, so it cannot be reached from here.
_TYPE_TO_CHART = {"bar": "Bar", "line": "Line"}

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


def _measures_and_dimensions(operations):
    """The summarize's own `measures` and `dimensions`, or `([], [])`."""
    for operation in operations or []:
        if isinstance(operation, dict) and operation.get("type") == "summarize":
            return (list(operation.get("measures") or []),
                    list(operation.get("dimensions") or []))
    return [], []


def _entry_for(measure, settings, counts, reasons):
    """The `series_settings` entry naming this measure, or `{}`.

    Metabase keys a series by its own result column name. For a compiled
    question that is the aggregate's SELECT alias, which Metabase writes as the
    bare function name — the real QIPI card carries exactly `avg` and `count`,
    while this converter names the same two measures `avg_of_<column>` and
    `count`. So the two are matched on the AGGREGATION, which both sides state.

    That key names only the FUNCTION, so two measures sharing one cannot be
    told apart: `AVG(a)` and `AVG(b)` are `avg` and `avg_2` to Metabase and
    `avg_of_a` and `avg_of_b` here, and nothing lines them up. That is recorded
    in `reasons` and abandons the whole card, because putting the label and the
    line on the wrong series makes a chart that reads correctly and is not.
    """
    wanted = str(measure.get("aggregation") or "").strip().lower()
    named = [value for key, value in settings.items()
             if str(key).strip().lower() == wanted]
    if not named:
        return {}
    if counts.get(wanted, 0) > 1:
        reasons.append(
            f"this query has {counts[wanted]} '{wanted}' measures, and Metabase "
            "names a series only by its function — so which of them its display "
            "setting belongs to cannot be told. Build the chart by hand.")
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
    # One dimension is one X axis. Two would need a `split_by`, and deciding
    # which is the axis and which the colour breakdown changes what it says.
    if len(dimensions) != 1:
        return None, None, (
            f"the query groups by {len(dimensions)} columns, and a chart needs "
            "exactly one for its X axis — build this one in Insights by hand")
    if display not in _DISPLAY_TO_TYPE:
        return None, None, (
            f"Metabase drew this card as '{display or 'nothing recorded'}', which "
            "this converter does not translate into a chart type")

    counts = {}
    for measure in measures:
        key = str(measure.get("aggregation") or "").strip().lower()
        counts[key] = counts.get(key, 0) + 1

    series, overridden, reasons = [], [], []
    for measure in measures:
        entry = _entry_for(measure, settings, counts, reasons)
        if reasons:
            return None, None, reasons[0]
        # The card-level display is what a series inherits when it carries no
        # `display` of its own — the QIPI card is `display: "line"` with only
        # `count` overridden to bar, and that override is the whole point.
        raw = str(entry.get("display") or "").strip().lower() or display
        if raw not in _DISPLAY_TO_TYPE:
            return None, None, (
                f"Metabase drew one series as '{raw}', which this converter does "
                "not translate into a chart type")
        item = {"measure": dict(measure), "type": _DISPLAY_TO_TYPE[raw],
                "align": _ALIGN}
        # Metabase's own label. Absent, Insights falls back to the measure name,
        # which is this converter's name rather than the report's.
        label = str(entry.get("title") or "").strip()
        if label:
            item["name"] = label
        if entry:
            overridden.append(measure.get("measure_name"))
        series.append(item)

    if not overridden:
        return None, None, (
            "Metabase recorded no per-series display settings for this card, so "
            "there is nothing to copy — Insights' own defaults apply")

    config = {"x_axis": {"dimension": dict(dimensions[0])},
              "y_axis": {"series": series}}
    return config, _TYPE_TO_CHART[_DISPLAY_TO_TYPE[display]], None
