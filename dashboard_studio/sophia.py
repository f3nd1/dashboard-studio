"""Which DS Chart types the receiving platform can actually draw.

Same shape and same limitation as ``edutrust.SUBCRITERIA``: this is a **copy** of
a list that lives in another repo, with no seam to validate it against. It must
be rechecked when Sophia's ``registerChartPlugin`` calls change. The full table,
with the usage counts it was read from, is ``docs/CHART_TYPE_MAPPING.md``.

Why it exists in code and not only in the doc: Sophia's ``renderChart`` falls
back to ``bar`` for any type it does not know —

    const renderer = CHART_PLUGINS.get(type) || CHART_PLUGINS.get("bar");

— so an unmapped type does not fail on the Sophia side, it quietly becomes a bar
chart. A document cannot prevent that. This module is what the chart picker and
the export both consult so the refusal happens here instead.
"""

# DS Chart.chart_type -> Sophia plugin id, or None when Sophia has no plugin.
# Order matches the chart_type Select in ds_chart.json.
CHART_PLUGINS = {
    "KPI Card": None,            # Sophia renders KPIs from metrics[], not via a plugin
    "Bar Chart": "bar",
    "Line Chart": None,          # `trend` is the nearest and is not the same thing
    "Donut Chart": "donut",
    "Table": None,               # every Sophia card already has a table view
    "Trend Chart": "trend",
    "Gauge": "gauge",
    "Funnel": "funnel",
    "Lifecycle": "lifecycle",
    "Flow": "flow",              # registered, but shares renderLifecycle with `lifecycle`
    "Matrix": "matrix",
    "Radar": "radar",
    "Decision Diagram": "decision",
    "Network Diagram": "network",
    "Reconciliation Diagram": "reconciliation",
    "Maturity Ladder": "ladder",
    "Risk Matrix": "risk-matrix",
}

# Why each unsupported type is unsupported, shown to whoever hits the refusal.
# A refusal that does not say what to do instead is a dead end.
UNSUPPORTED_REASON = {
    "KPI Card": (
        "Sophia renders KPIs from the metrics[] array, not through a chart "
        "plugin — a published KPI is a different artefact, not a chart with a type."
    ),
    "Line Chart": (
        "Sophia has no line plugin. `trend` is the nearest and is not the same "
        "thing: it draws one horizontal line with point labels and no Y axis."
    ),
    "Table": (
        "Sophia has no table plugin. Every card already has a table view, "
        "produced by the card shell rather than by a chart type."
    ),
}


def plugin_for(chart_type):
    """The Sophia plugin id for a DS chart type, or None if there is not one."""
    return CHART_PLUGINS.get(chart_type)


def is_supported(chart_type):
    return bool(CHART_PLUGINS.get(chart_type))


def unsupported_types():
    """Every DS chart type Sophia cannot draw, in Select order."""
    return [name for name, plugin in CHART_PLUGINS.items() if not plugin]


def refusal_for(chart_type):
    """Why this type cannot be published, or None if it can."""
    if is_supported(chart_type):
        return None
    if chart_type not in CHART_PLUGINS:
        return (
            f"'{chart_type}' is not a DS chart type at all, so there is nothing "
            "to publish it as."
        )
    return UNSUPPORTED_REASON.get(chart_type, f"Sophia has no plugin for '{chart_type}'.")
