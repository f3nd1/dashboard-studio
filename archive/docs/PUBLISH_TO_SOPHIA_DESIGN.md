# Publish to Sophia — design

**Status:** design only. Nothing built. Decisions required before any code.

Evidence from `f3nd1/intelligence-dashboard` @ `49361a8` and this repo. Everything
below is read from source; **nothing has been run against a live Bench**, and the
publish path in particular has never executed anywhere.

---

## 0. Summary of what the evidence changes

Three findings move this away from the shape the brief assumes:

1. **Sophia's chart→data binding is positional, not by identity.** A published
   chart cannot say *which metric it draws*, because the contract has no field
   for it (§2). This is the blocking finding.
2. **Both "write a script" and "write data" mean editing the same hand-maintained
   file.** The data/script security distinction is real but secondary — the
   transport is the risk (§3).
3. **The deployed Custom HTML Block is the only copy of itself.** It has diverged
   three ways from `src/` and `dist/`; anything published over it is destroyed
   with no other copy (§5). This confirms the worry in the brief and is the
   reason to reject in-place rewriting outright.

---

## 1. What Sophia actually consumes

A "dashboard" on the Sophia side is not one artefact. It is three, in two places:

| Part | Where it lives | Shape |
|---|---|---|
| Criterion config | `custom-html-block/JAVASCRIPT.js` → `CONFIG[criterion_id]` | `{number, title, description, subcriteria[[code,label]], sections{}, filters, apiMethod, defaultSection, apiSections{}, panelMap{}}` |
| Visual definitions | same file → `LIVE_VISUAL_EXPANSION[criterion_id][section]` | `[{id, title, type, description, i, enabled}]` |
| The numbers | `server-scripts/UCC Analytics - Criterion N.py` | `metrics[]`, `sources[]`, `questions[]` via `standardise_response_contract` |

The first two are **JavaScript source inside a Frappe Custom HTML Block field**.
There is no configuration record, no API, and no import seam. `JAVASCRIPT.js` is
3,343 lines and 227 KB; the engine block starts at line 2144.

---

## 2. The blocking finding: chart→metric binding is positional

`metricRows(result, chartIndex, chart)` — `JAVASCRIPT.js:2399`:

```js
const metrics=(result?.metrics||[]).filter(item=>item.status==="available");
...
const size=Math.min(5,metrics.length), start=(chartIndex*size)%metrics.length, rows=[];
for(let i=0;i<size;i++){ const metric=metrics[(start+i)%metrics.length]; rows.push([...]); }
```

with `chartIndex` supplied as `chart.i ?? index` (`JAVASCRIPT.js:2569`).

**A chart plots a rotating five-metric window chosen by its ordinal position** in
`LIVE_VISUAL_EXPANSION`. Its `id`, `title` and `type` do not select its data at
all, except for regex special-cases on the *human-readable title*
(`/source availability|evidence readiness|source readiness/`, `/exception|gap|risk profile/`).
`% metrics.length` wraps, so windows overlap and metrics repeat across charts.

Consequences, all silent:

- A chart titled "Applicants per Country" plots whatever five metrics land at its
  index. Title and content are unrelated by construction.
- Adding, removing or reordering a metric in a Server Script changes what **every
  chart in that section** displays.
- `filter(status==="available")` runs first, so a user who cannot read one source
  gets a *different set of metrics per chart* than a user who can — same chart,
  same page, different numbers, no indication.

**Why this blocks publishing.** A DS Chart carries `metric` (a Link to an
approved DS Metric). The Sophia contract has nowhere to put that. Publishing
could only reproduce a chart's data by controlling the *order* of the metrics
array in the Server Script and hoping no one edits it — which is exactly the
silent-mis-route class this project refuses.

**This cannot be fixed from this repo.** Either Sophia gains identity-based
binding (`chart.metric_id` → `metrics.find(m => m.id === …)`), or publishing
cannot faithfully express what Dashboard Studio models. **Recommend: treat a
Sophia-side change to identity binding as a precondition of publishing**, not as
an optional improvement.

---

## 3. Script or data — the security argument

The brief asks for this argued rather than assumed. The argument does not land
where the framing expects.

### Generating a Server Script

- Runs in Frappe's `safe_exec` sandbox: restricted builtins, no imports.
- Not sandboxed from **data**: the existing scripts call `frappe.get_list`, which
  is permission-aware, so a generated script inherits the caller's permissions
  rather than escalating. Data exposure risk is therefore low.
- The real risk is **wrongness, not breach**: a generation bug emits a script
  that runs cleanly and returns wrong numbers. There is no test between
  generation and a published EduTrust dashboard.
- Directly contradicts two standing rules in `CLAUDE.md`: *"Never build the
  product as one large Server Script"* and *"Never execute arbitrary user- or
  AI-generated SQL"*. Generated Python from user-authored config is the same
  category.
- Writing a Server Script record needs System Manager **and** `server_script_enabled`
  on the site. That is a hard gate, but it also means publishing would require
  handing the Studio a privilege the four-role model deliberately withholds.

### Writing "data"

- The apparent safe option, and it is not, because **the destination is a
  JavaScript field**. `CONFIG` and `LIVE_VISUAL_EXPANSION` are JS object literals
  inside `JAVASCRIPT.js`. Emitting "configuration" there means emitting JS source.
- Any unescaped value — a chart title with `</script>`, a quote, a backslash —
  becomes executable in every viewer's browser. That is stored XSS with a
  governance workflow in front of it.
- Sophia's own renderers escape via `esc()` at render time, but that protects
  values *inside* the runtime; it does nothing for text spliced into the source
  before it loads.

### Recommendation

**Neither, as posed.** Both write into a hand-maintained JS blob, and the choice
between them is less important than the transport. The defensible shapes are, in
order of preference:

1. **Publish to a record Sophia reads.** Dashboard Studio writes a JSON artefact
   (a new DS DocType, or a fixture file); Sophia gains a small reader that merges
   it into `CONFIG`/`LIVE_VISUAL_EXPANSION` at boot. Nothing executable crosses
   the boundary, the artefact is reviewable and diffable, and rollback is a
   record change. **Requires a change in the Sophia repo.**
2. **Publish an export for a human to paste.** Dashboard Studio generates the
   JSON and shows it; a person applies it. No automation, no destruction risk,
   and it works today. Weak, but honest, and it makes the contract concrete
   before anyone commits to option 1.
3. Generating a Server Script — only if a criterion genuinely needs a new metric,
   and even then it should be authored and reviewed as a script, not generated.

Option 2 is the recommended **first** deliverable: it forces the contract to be
specified and validated without touching Sophia at all.

---

## 4. Update and withdraw

There is no answer today, and this is the second reason not to automate writing.

- **Update:** re-publishing means rewriting the same region of a 227 KB file. No
  identifier ties a published section back to the DS Dashboard that produced it,
  so a second publish cannot find what the first one wrote.
- **Withdraw:** nothing marks published content as ours, so nothing can remove it
  selectively.
- **Rollback:** Sophia's only versioning is manual file copies —
  `custom-html-block/archive/JAVASCRIPT_archived_v1.9.7.js` and
  `HTML_archived_c5_cards_v1.9.8.html`. That is a person remembering, not a
  mechanism.

**Design requirement:** every published artefact must carry the DS Dashboard name
and a publish timestamp, so update and withdraw are addressable operations rather
than a search-and-replace. Under §3 option 1 this is free — a record has a key.
Under in-place editing it is not solvable.

`DS Dashboard` already has `published_on`; a `published_revision` or the artefact
record's own name would complete it. **No field should be added until the
transport is decided.**

---

## 5. Overwriting Sophia's hand-edited content

The brief flags this as the biggest worry. **The evidence says the worry is
correct, and stronger than stated.**

Measured with `sha256sum` (recorded in `docs/investigation_analytics_report.md` §4.1–4.2):

| | `src/` + `dist/` | `custom-html-block/` (deployed) |
|---|---|---|
| Analytics engine | `v1.9.6`, 5 criteria in `CONFIG` | **`v2.0.1`, all 7** |
| `registerChartPlugin` calls | **0** | **16** |
| `d3.` references | 57 | **0** |
| JS size | 453 KB built | 227 KB |

`build-manifest.json` claims `src/*` builds into `custom-html-block/*`. It does
not — they are different architectures. `PACKAGE_CHECKSUMS.json` records hashes
for both that match **neither**.

**Therefore: the deployed Custom HTML Block is the only copy of itself.** The
unified engine, the 16 chart plugins and the removal of D3 exist nowhere else.
Anything a publish step overwrote there would be unrecoverable from any
repository.

**Design requirement (non-negotiable):** publishing must never rewrite
`JAVASCRIPT.js`, `CSS.css` or `HTML.html` in place, wholesale or by region.
§3 option 1 satisfies this by construction. If in-place editing is ever
revisited, it must be preceded by committing the deployed files back to their own
repo so a second copy exists.

---

## 6. Where the parity check fits

Publishing without proving the new numbers match the old ones would defeat the
Validation Centre. It should not be a second gate — the existing one should
become a precondition.

What exists: `DS Validation Comparison` with `chart` (Link), `comparison_date`,
`status` (Match / Discrepancy / Flagged / Accepted), `accepted_reason`,
`reviewed_by`, and per-group `comparison_rows`. `Accepted` is never computed —
only a person sets it, with a reason.

**Proposed rule, for decision:**

> A dashboard may not move to `Published` unless **every chart with a metric** has
> a `DS Validation Comparison` whose status is `Match` or `Accepted`, and whose
> `comparison_date` is not older than the chart's `modified`.

- `Discrepancy` and `Flagged` block. `Flagged` especially: it means a value could
  not be compared at all.
- The recency condition stops a stale pass from covering an edited chart.
- Charts without a metric are exempt — there is nothing to compare.

**Open question for you:** whether an unvalidated chart *blocks* the dashboard or
is *excluded* from the published output. Blocking is safer and simpler; excluding
publishes a partial dashboard, which may be worse than publishing none.

---

## 7. Recommended sequence

1. **Precondition — Sophia gains identity-based binding** (§2). Without it,
   publishing cannot express a chart's metric. Sophia-repo change.
2. **Specify the artefact.** JSON, carrying dashboard name, subcriterion,
   charts with explicit `metric_id`, and a publish timestamp.
3. **Build export-only** (§3 option 2). Generates and shows the artefact;
   validates the subcriterion against Sophia's real keys — **this is where the
   `edutrust.py` "validates against our copy, not against Sophia" limitation gets
   closed, and that closure is an acceptance criterion of this work.**
4. **Add the parity precondition** (§6).
5. **Only then** consider automated delivery, and only into a record Sophia reads.

---

## Annex — other silent-failure paths on the Sophia side

Found while reading, not while running. **None verified against a live site.**
Listed because several bear on what publishing can safely assume. Read-only
observations; no changes were made to either repository.

| # | Path | Effect | Confidence |
|---|---|---|---|
| 1 | Positional chart→metric binding (§2), `JAVASCRIPT.js:2399` | title and plotted data unrelated; a metric reorder silently changes every chart | **Verified by reading** |
| 2 | Permission-filtered metrics shift the same window, `:2404` | two users see different numbers in the same chart, no indication | **Verified by reading** |
| 3 | `renderChart` falls back to `bar` for unknown types, `:2316` | a typo'd `type` renders a plausible wrong chart instead of failing | **Verified by reading** |
| 4 | `metricRows` special-cases on the human-readable **title**, `:2407` | retitling a chart to/from "Source Availability" / "Evidence Readiness" / "Source Readiness" silently changes its data source | **Verified by reading** |
| 5 | `standardise_response_contract` defaults `ok` to `True` (`C5.py:3094`) | a script failing before setting `ok` still satisfies the client's `if(message&&message.ok)` gate at `:2345` | **Verified by reading** |
| 6 | `apiSection()` returns `state.lastSection \|\| defaultSection` for the `quality`/`sources` tabs, `:2232` | Sources & Data Quality reports on whichever section was last loaded, not the one on screen | **Verified by reading** |
| 7 | `panelInsertPoint` finds its DOM anchor by regex on `textContent` "Management Questions and Data-Based Answers", `:2238` | changing that heading silently relocates every generated chart grid | **Verified by reading** |
| 8 | `resolve_source` records `fallback_used` when a non-first candidate DocType resolves (`C5.py:2364`); `grep -c fallback_used` on the deployed JS returns **0** | the dashboard can silently read a *different DocType* than intended, and the UI never says so | **Verified by reading** |
| 9 | 5.4 / 5.5 cache miss (`docs/investigation_analytics_report.md` §4.5) | those two tabs refetch on every visit | **Verified by reading** |
| 10 | `renderKpis` pads to six tiles with summary placeholders, `:2508` | a criterion with fewer than six metrics shows filler tiles that read like metrics | Reading, lower confidence — depends on how the tiles are styled at runtime |
| 11 | Chart colour vars `--ucc-chart-0..5` wrap at 6 (`renderDonut`, `:2302`) | a 7+ series donut repeats colours; two slices look like one series | **Verified by reading**, cosmetic |

Items 1, 2, 4 and 8 are the ones that would let a *published* dashboard show the
wrong number without anyone noticing.
