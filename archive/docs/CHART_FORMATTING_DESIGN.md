# Per-chart formatting controls — investigated, held

**Status:** investigated, **nothing built, no fields added**. Held until the
publish contract exists. This records the reasoning so it is not re-derived.

Requested: Power BI style per-chart controls — show/hide legend, show/hide X and
Y axis, edit axis labels, edit data labels, change label format, change colours.

---

## 1. The deciding question: can Sophia honour any of it?

**No. Not one of the seven.**

`renderChart` (`custom-html-block/JAVASCRIPT.js:2316`) passes the chart
definition to a plugin as a third argument. But of the sixteen registered
plugins (`:2300–2315`), **fifteen declare arity `(node, rows)` and discard it**:

```js
registerChartPlugin("bar",   (node,rows)=>renderBars(node,rows));
registerChartPlugin("donut", (node,rows)=>renderDonut(node,rows));
…
registerChartPlugin("risk-matrix",(node,rows,chart)=>{…});   // the only one
```

`risk-matrix` is the sole exception, and it uses the argument only to synthesise
a 25-cell array. So a formatting option published inside a chart definition would
reach exactly one renderer.

**Our own renderers are no better.** Every function in `studio_charts.js` takes
`(rows)` only, and none draws a legend, an axis, or a visible data label —
values appear solely in `<title>` hover tooltips and the `table` renderer.

### Buckets

| Option | Sophia today | Studio today | Bucket |
|---|---|---|---|
| Show/hide legend | only `renderDonut`, unconditional | none | **3 — impossible** |
| Show/hide X axis | only `trend`, `radar`, `admission-*`; **`bar` has no axis at all**, and 70 charts ship as `type:"bar"` | none | **3** |
| Show/hide Y axis | only `admission-line` / `admission-column`; `renderTrend` draws a horizontal line and no Y axis | none | **3** |
| Edit axis labels | axis text *is* the dimension value from `rows`; no label slot exists | none | **3** |
| Edit data labels | always drawn, unconditional, content = raw value | none | **3** |
| Change label format | hardcoded heuristic (§4) | raw values, table only | **3** |
| Change colours | six fixed CSS vars on `.ucc-platform`, `index%6` wrap, used by **donut only** — bars take a flat class colour | `COLORS` / `COLORS_SEQ` constants | **3** |

**Bucket 1 (publishable) is empty. Bucket 2 (Studio-only) is also empty**, because
nothing is renderable in the Studio today either without building it first.

Note: an option whose only honoured value happens to match Sophia's fixed
behaviour is not a control, it is decoration.

---

## 2. Decision: hold everything, do not offer preview-only

Rejected explicitly. A control marked *preview-only* still teaches an Editor that
the Studio governs appearance and then silently does not. On a tool whose output
is audit evidence, an authorable setting that never reaches the artefact is the
confidently-wrong failure mode, in our own app this time.

Sequencing: this queues **behind** identity-based binding, which is already the
stated precondition for publishing at all
(`docs/PUBLISH_TO_SOPHIA_DESIGN.md` §2). Making sixteen hand-written string
builders honour an options object is realistically a larger change to the Sophia
repo than that binding change.

---

## 3. Storage, if it is ever built: individual fields

Recorded now because the argument is the general one, not specific to charts.

### Why not a `chart_options` JSON blob

**`deploy_check`, the schema test and the test fake's `reqd` enforcement all
operate on fields. A JSON blob is invisible to every protection built into this
repo.** It cannot be validated by Frappe, queried, diffed per-field by
`track_changes`, or checked for drift against a live site.

That is precisely why the six placeholder DocTypes are frozen: their `*_json`
fields are unreachable by all of it. A `chart_options` blob would rebuild the
exact thing this repo spent a week making impossible.

### The shape it would take

Roughly **eight fields** on DS Chart:

| Field | Type |
|---|---|
| `show_legend` | Check |
| `show_x_axis` | Check |
| `show_y_axis` | Check |
| `x_axis_label` | Data |
| `y_axis_label` | Data |
| `show_data_labels` | Check |
| `label_format` | Select — **but see §5; this belongs on DS Metric** |
| `colour_scheme` | Select — **but see §5; colour is platform-level** |

DS Chart carries 13 fields today, so ~21. Unremarkable for Frappe. Type-specific
relevance is handled natively by `depends_on: "eval:doc.chart_type=='Donut Chart'"`,
which a blob cannot express. If the count ever passed ~20 formatting fields that
would signal the chart-type set is too broad, not that the storage is wrong.

**No fields are added now.** Schema that encodes a promise the output cannot keep
is worse than no schema; storage is downstream of the publish contract.

---

## 4. What the investigation turned up: a live bug

`renderBars` and `renderMatrix`:

```js
<strong>${row[1]}${max<=100?"%":""}</strong>
```

**Any bar chart whose largest value is ≤ 100 labels every value as a percentage.**
Applicants by year `2, 3, 1` renders as `2%`, `3%`, `1%`. Seventy charts ship as
`type:"bar"`, and counts at this institution's scale are routinely under 100.

Tracked separately in `docs/BAR_PERCENT_BUG.md` — confirmation procedure and fix
proposal. It is the strongest evidence that label format is a real need, and also
the clearest demonstration that the fix belongs in Sophia rather than behind a
Studio toggle.

---

## 5. Two items that are the wrong shape, not just deferred

Both are recorded as standing decisions in `CLAUDE.md`.

**Per-chart colour: dropped permanently.** Consistent encoding across the seven
criteria is part of the evidence — a reviewer must not relearn what blue means
between Criterion 4 and Criterion 7. Sophia's palette is deliberately
platform-wide (`--ucc-chart-*` on `.ucc-platform`). If colour ever becomes
configurable it is one palette for the platform, never a per-chart property.

**Label format belongs to DS Metric.** Whether a figure is a count or a
percentage is a fact about what it measures, not how it looks, and
`DS Metric.calculation_type` already carries `Count / Sum / Average / Percentage`
on the *approved* object. A chart-level control would let an Editor display an
approved count of 62 as "62%" with no review — the same governance hole that the
locked metric-ownership decision exists to prevent. Derive it from the metric.
Not built; queued behind the publish contract.
