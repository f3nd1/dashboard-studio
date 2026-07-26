# DS Chart type → Sophia plugin

Reference only. **No decision is made here** about the mismatches — this exists
so the next person is not surprised by them.

Read from source, not inferred:
- DS side: `DS Chart.chart_type` options in
  `dashboard_studio/dashboard_studio/doctype/ds_chart/ds_chart.json`, and
  `CHART_TYPES` in `public/js/studio_core.js`, which mirrors it.
- Sophia side: the `registerChartPlugin(...)` calls in
  `custom-html-block/JAVASCRIPT.js` (lines 2300–2315 as committed at `49361a8`).

**17 DS types. 16 Sophia plugins. Seven do not line up.**

---

## The table

| DS Chart type | Sophia plugin | Notes |
|---|---|---|
| KPI Card | **NONE** | Sophia renders KPIs from the `metrics[]` array via `metricValue`, not through a chart plugin at all. A published KPI is a different artefact, not a chart with a type. |
| Bar Chart | `bar` | 70 uses in `CONFIG`. Also the fallback for any unknown type (see below). |
| Line Chart | **NONE** | `trend` is the nearest, and it is not the same thing — `renderTrend` draws one horizontal line with point labels, no Y axis. |
| Donut Chart | `donut` | 78 uses, the most common. The only plugin that draws a legend. |
| Table | **NONE** | Every Sophia card already has a table view, produced by the card shell rather than by a plugin. "Table" as a *chart type* has no counterpart. |
| Trend Chart | `trend` | 20 uses. |
| Gauge | `gauge` | 10 uses. |
| Funnel | `funnel` | 43 uses. |
| Lifecycle | `lifecycle` | 39 uses. |
| Flow | `flow` | Registered, but `flow` and `lifecycle` share one renderer (`renderLifecycle`). 1 use. |
| Matrix | `matrix` | 32 uses. `renderMatrix` carries the percent-suffix bug — see `docs/BAR_PERCENT_BUG.md`. |
| Radar | `radar` | 28 uses. |
| Decision Diagram | `decision` | 2 uses. |
| Network Diagram | `network` | 1 use. |
| Reconciliation Diagram | `reconciliation` | 1 use. |
| Maturity Ladder | `ladder` | 7 uses. |
| Risk Matrix | `risk-matrix` | 1 use. The only plugin that reads the chart definition (`chart`) rather than just `rows`. |

### Sophia plugins with no DS Chart type

| Sophia plugin | Uses in `CONFIG` |
|---|---|
| `admission-line` | 3 — Criterion 4 admission intelligence |
| `admission-column` | 2 — same |

Both are Criterion-4-specific and read `result.admission_intelligence`, which is
the bespoke path documented in `docs/BAR_PERCENT_BUG.md`. A DS Chart cannot
currently express either.

### A type in use with no plugin at all

`"type":"month"` appears **3 times** in `CONFIG` and is not registered.
`renderChart` falls back to `bar` for anything unregistered:

```js
const renderer = CHART_PLUGINS.get(type) || CHART_PLUGINS.get("bar");
```

So those three charts render as bars and always have. Nothing errors. This is
the same silent-fallback shape as the rest of `docs/SOPHIA_FAULT_PATTERN.md`,
and it is why an unmapped DS type would not fail loudly either — it would
quietly become a bar chart.

---

## What this means for publishing

Three of the seventeen DS types (**KPI Card, Line Chart, Table**) have nowhere
to go. A publish contract that emits `chart_type` verbatim would send a value
Sophia does not know, and Sophia would draw a bar chart without complaining.

That is a decision for the publish work
(`docs/PUBLISH_TO_SOPHIA_DESIGN.md`), not for this file. The options, unranked
and undecided:

1. Refuse to publish a chart whose type has no plugin, naming the type.
2. Map the three to their nearest plugin and record the substitution.
3. Add plugins on the Sophia side — a Sophia-repo change, currently out of scope.

Whichever is chosen, **the silent bar-chart fallback must not be the mechanism.**

---

## Keeping this from drifting

`CHART_TYPES` in `studio_core.js` and the `chart_type` Select in `ds_chart.json`
both carry a pointer to this file. Neither is validated against Sophia — there
is no seam to validate against — so this table is a **manual** record with the
same limitation `dashboard_studio/edutrust.py` documents about `SUBCRITERIA`:
it is a copy, and it must be rechecked when Sophia's registrations change.

Recheck it when: a `registerChartPlugin` call is added or removed, or a DS Chart
type is added.
