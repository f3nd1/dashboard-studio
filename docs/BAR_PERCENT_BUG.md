# Bar charts label counts as percentages

**Part 1** confirms the *adding* case on the live site — read-only, Desk access only.
**Part 1B** detects the *dropping* case, the quiet half of the same split. Run both
on the same tab, back to back.
**Part 2** proposes the fix. Nothing in the Sophia repository has been touched.

---

## What was found

`custom-html-block/JAVASCRIPT.js`, `renderBars` and `renderMatrix`:

```js
<strong>${row[1]}${max<=100?"%":""}</strong>
```

where `chartMax` is `Math.max(...values, 1)`.

**Any bar chart whose largest value is ≤ 100 labels every value as a percentage.**
A count of applicants by year `2, 3, 1` renders as `2%`, `3%`, `1%`. Seventy
charts ship as `type:"bar"`, and counts at this institution's scale are routinely
below 100.

### Why this is provable without knowing what the number should be

The same card renders its value twice, through two different code paths:

| View | Path | Percent rule |
|---|---|---|
| **Diagram** | `renderBars` | `max <= 100` → append `%` |
| **Table** | `metricValue` (`:2508`-ish) | `metric.unit === "percent"` → append `%` |

`metricValue` is unit-aware and correct. `renderBars` is not. So on any affected
chart **the card contradicts itself**: the diagram says `62%` and the table says
`62`, from one dataset, in one card, on screen at the same time.

That makes this confirmable with no reference to intent, no server call, and no
knowledge of what the metric measures.

---

# Part 1 — confirm it on the live site

Read-only. Every step is a DOM read; nothing is written, saved or requested.

## Step 1

Open the Sophia dashboard page in Desk and let it finish loading. Go to a
criterion with bar charts — **Criterion 4 or 5** have the most. Stay on the
Analytics workspace.

## Step 2

Open DevTools → Console. Paste this and press Enter.

```js
(() => {
  const root = document.querySelector('#uccIntelligencePlatform');
  if (!root) return console.error('Platform not found on this page.');
  const dash = [...root.querySelectorAll('[data-demo-dashboard]')]
    .find(d => !d.classList.contains('ucc-hidden'));
  console.log(`criterion=${dash.dataset.demoDashboard} tab=${dash.dataset.demoActiveTab}`);

  const rows = [];
  dash.querySelectorAll('[data-demo-card]').forEach(card => {
    const title = (card.querySelector('.card-title, h2') || {}).textContent || card.dataset.demoCard;
    // Diagram view: the bar/matrix value labels.
    const drawn = [...card.querySelectorAll('.ucc-demo-bar strong, .ucc-demo-matrix strong')]
      .map(n => n.textContent.trim());
    if (!drawn.length) return;                       // not a bar/matrix card
    // Table view of the SAME card, filled from metricValue().
    const tabled = [...card.querySelectorAll('[data-demo-chart-table-body] tr')]
      .map(tr => (tr.children[1] || {}).textContent || '').map(s => s.trim());
    if (!tabled.length) return;                      // card not drawn yet

    const n = Math.min(drawn.length, tabled.length);
    const disagree = [];
    for (let i = 0; i < n; i++) {
      const d = drawn[i], t = tabled[i];
      if (d !== t && d.replace(/%$/, '') === t.replace(/,/g, '')) disagree.push(`${t} shown as ${d}`);
    }
    rows.push({
      chart: title.slice(0, 44),
      diagram: drawn.slice(0, 4).join(', '),
      table: tabled.slice(0, 4).join(', '),
      verdict: disagree.length ? 'MISLABELLED' : (drawn.some(v => /%$/.test(v)) ? 'both %' : 'consistent'),
    });
  });

  if (!rows.length) return console.warn('No bar/matrix cards rendered on this tab — try another.');
  console.table(rows);
  const bad = rows.filter(r => r.verdict === 'MISLABELLED');
  console.log(`\n${bad.length} of ${rows.length} bar/matrix charts label a plain count as a percentage.`);
  console.log(bad.length
    ? '>>> CONFIRMED: the diagram contradicts the table on the same card.'
    : '>>> NOT REPRODUCED here — send the table anyway; every value may exceed 100 on this tab.');
})();
```

## Step 3 — send back

- The `console.table` output.
- The `>>>` line and the count.
- Which criterion and tab.

Worth repeating on two or three criteria: whether it reproduces depends entirely
on whether that tab's largest value happens to exceed 100.

## Reading the result

| Result | Meaning |
|---|---|
| `CONFIRMED`, N > 0 | Real. Those N charts display counts with a `%` suffix. |
| `NOT REPRODUCED` | Every value on that tab exceeded 100, so the heuristic stayed off. It is not disproved — try a tab with smaller numbers. |
| `both %` on every row | The metric genuinely *is* a percentage, and both views agree. Correct behaviour. |

## What a confirmation means for figures already used

Blunt version:

1. **Any screenshot of an affected bar chart shows a count with a `%` after it.**
   A reader has no way to tell `62` applicants from `62%` of anything.
2. **A figure quoted from a bar chart may have been read as a rate when it is a
   headcount.** If any EduTrust submission, board paper or report quotes a
   percentage sourced from a bar chart on these dashboards, it is worth checking
   against the underlying records.
3. **The table view of the same card has been correct all along.** Anything
   cross-checked against the table, or against ERPNext directly, is unaffected.
4. This does **not** touch the stored data. Nothing in ERPNext is wrong; it is a
   display fault in one renderer.

It is independent of the positional-binding finding in
`docs/VERIFY_POSITIONAL_BINDING.md`, and both can be true at once.

---

# Part 1B — detect the dropping case

Part 1 catches the diagram **adding** a `%` that is not there. This catches the
inverse: the diagram **omitting** a unit the table applies to the same value —
a real percentage drawn as a bare number, `SGD 1,234.5` drawn as `1234.5`,
`4/5` drawn as `4`.

Same shape as Part 1: pure DOM reads, Desk access only, nothing written or
requested.

## Why this needs no API read

An earlier note in the annex said the dropping case would need the metric's
`unit`, which is not in the DOM. **That was wrong, and the correction matters
because it is what makes this runnable at all.** The table cell is *rendered by*
`metricValue`, so a `%`, an `SGD ` prefix, a `/5` suffix or a thousands separator
in the table cell **is** the unit, already applied. Comparing the table's
decorated string against the diagram's raw string tests the same thing without
asking the server anything.

## Step 1

Same tab as Part 1 — do not navigate away. Paste back to back and you get both
halves of the split for one criterion.

## Step 2

```js
(() => {
  const root = document.querySelector('#uccIntelligencePlatform');
  if (!root) return console.error('Platform not found on this page.');
  const dash = [...root.querySelectorAll('[data-demo-dashboard]')]
    .find(d => !d.classList.contains('ucc-hidden'));
  console.log(`criterion=${dash.dataset.demoDashboard} tab=${dash.dataset.demoActiveTab}`);

  // A table value carrying a unit or separators that metricValue applied.
  const decorated = v => /%$/.test(v) || /^SGD\s/.test(v) || /\/5$/.test(v) || /,/.test(v);
  const bare = v => v.replace(/^SGD\s/, '').replace(/%$/, '').replace(/\/5$/, '')
                     .replace(/,/g, '').trim();

  const rows = [];
  let unitBearing = 0;
  dash.querySelectorAll('[data-demo-card]').forEach(card => {
    const title = (card.querySelector('.card-title, h2') || {}).textContent || card.dataset.demoCard;
    const diagram = card.querySelector('[data-demo-chart]');
    if (!diagram) return;
    const drawn = [
      ...[...diagram.querySelectorAll('strong, text.value')].map(n => n.textContent.trim()),
      ...[...diagram.querySelectorAll('.ucc-demo-radar-values span')]
          .map(n => (n.textContent.split(':')[1] || '').trim()),
    ].filter(Boolean);
    const table = [...card.querySelectorAll('[data-demo-chart-table-body] tr')]
      .map(tr => [((tr.children[0]||{}).textContent||'').trim(),
                  ((tr.children[1]||{}).textContent||'').trim()]);
    if (!drawn.length || !table.length) return;

    const withUnits = table.filter(([, v]) => v && v !== '—' && v !== 'missing' && decorated(v));
    if (!withUnits.length) return;            // plain counts only — not evidence either way
    unitBearing += withUnits.length;

    const dropped = withUnits.filter(([, v]) => drawn.includes(bare(v)) && !drawn.includes(v));
    rows.push({
      chart: title.slice(0, 44),
      diagram: drawn.slice(0, 4).join(', '),
      table: withUnits.slice(0, 4).map(r => r[1]).join(', '),
      verdict: dropped.length ? 'DROPPED' : 'consistent',
    });
  });

  if (!unitBearing) {
    console.log('>>> NO UNIT-BEARING METRICS ON THIS TAB — INCONCLUSIVE, NOT A PASS.');
    console.log('    Every value here is a plain count, so there is no unit to drop.');
    console.log('    Try another criterion before drawing any conclusion.');
    return;
  }
  console.table(rows);
  const bad = rows.filter(r => r.verdict === 'DROPPED');
  console.log(`\n${bad.length} of ${rows.length} unit-bearing charts drop the unit in the diagram.`);
  console.log(bad.length
    ? '>>> CONFIRMED: the diagram omits a unit the table applies to the same value.'
    : '>>> NOT REPRODUCED on this tab — the diagram carried the unit.');
})();
```

## Step 3 — send back

- The `console.table` output.
- The `>>>` line and the count.
- Which criterion and tab (the first `console.log` prints it).

## Reading the result

| Result | Meaning |
|---|---|
| `CONFIRMED`, N > 0 | Real. Those N charts draw a unit-bearing value with the unit stripped. |
| `NOT REPRODUCED` | The diagram carried the unit on this tab. Real evidence of absence for **this tab only** — a different chart type may still drop it. |
| `NO UNIT-BEARING METRICS` | **Not a pass.** Every value on that tab is a plain count, so there was no unit to drop and the test could not have failed. Try another criterion. |

The third verdict is the one to be careful with, and it is why it prints in
capitals with its own explanation rather than as an empty table. A tab of pure
counts produces a clean-looking run that proves nothing.

## What it does not catch

- A value the diagram never draws (charts whose labels are hover-only).
- A unit dropped *and* the number reformatted, so no bare match exists.
- Cases where the diagram and table happen to show different rows.

All three make it under-report, never over-report. A `DROPPED` verdict is
therefore trustworthy; a `consistent` one is weaker.

## The test was tested

Run against four seeded pages before being handed over, to prove a null result
means something:

| Seeded page | Verdict printed |
|---|---|
| diagram drops the `%` | `CONFIRMED` |
| diagram carries the `%` | `NOT REPRODUCED` |
| plain counts only | `NO UNIT-BEARING METRICS — INCONCLUSIVE, NOT A PASS` |
| `SGD` + thousands separators dropped | `CONFIRMED` |

---

# Part 2 — fix proposal (nothing built, Sophia untouched)

## The change

Two lines, one file, `custom-html-block/JAVASCRIPT.js`.

Delete the heuristic in `renderBars` and `renderMatrix`:

```js
-  <strong>${row[1]}${max<=100?"%":""}</strong>
+  <strong>${row[1]}</strong>
```

**Recommended: delete, do not replace.** The correct suffix depends on the
metric's `unit`, which `renderBars` does not receive — `rows` carries only
`[label, value]` pairs. Guessing is what created the bug. A bare number is
never wrong; a wrong suffix is.

### If a percent suffix is genuinely wanted on the diagram

It has to come from the metric, not from the values' magnitude. `metricRows`
already puts the metric object at `row[2]`, so the honest version is:

```js
const suffix = row[2] && row[2].unit === "percent" ? "%" : "";
```

matching `metricValue`'s rule exactly. That is a slightly larger change —
`renderBars` currently ignores `row[2]` — and it should only be made if someone
confirms percent-suffixed bar labels are actually wanted. Deleting is sufficient
and strictly safer.

## How it is verified

Re-run Part 1's snippet after deploying. Expected outcome: every row reports
`consistent` or `both %`, and **zero** report `MISLABELLED`. That is the same
test proving the opposite result, which is the cheapest possible regression check.

Also confirm at least one genuinely-percentage chart still shows `%` in **both**
views, so the fix has not removed a correct suffix.

## How it interacts with the deployed-block problem

This is the part that needs care, and it is why the proposal stops at a diff.

`custom-html-block/JAVASCRIPT.js` is committed in the intelligence-dashboard repo
at `49361a8` — so it is **backed up**. But it is **not derivable**: `src/` is a
different architecture (v1.9.6, five criteria, 57 `d3.` references, no plugin
registry) and cannot rebuild the deployed v2.0.1 engine. `build-manifest.json`
claims otherwise and is wrong; `PACKAGE_CHECKSUMS.json` matches neither.

Consequences for deploying this fix:

1. **Do not rebuild from `src/`.** It would revert the unified engine, all
   sixteen chart plugins and the D3 removal in one step. This fix must be applied
   to `custom-html-block/JAVASCRIPT.js` directly.
2. **Confirm the repo copy matches the live block first.** Run Test B in
   `docs/VERIFY_POSITIONAL_BINDING.md`. If the live block has drifted from
   `49361a8`, editing the repo copy and pasting it would silently revert whatever
   that drift was.
3. **Deploy is a paste**, so the whole 227 KB field is replaced. Keep the archive
   convention already in use — `custom-html-block/archive/JAVASCRIPT_archived_v*.js`
   — and take a copy of the live field before pasting.
4. **Commit the edit to the intelligence-dashboard repo in the same change**, so
   the repo copy and the live block do not diverge again.

Given all of that, the two-line deletion is about as small and reversible as a
change to that file can be, and it is a good candidate for re-establishing a
clean repo-to-live sync while the diff is trivially reviewable.

---

# Annex — other same-value-two-paths splits

Asked before running Part 1: is there anywhere else the same value is rendered by
two paths with different rules? **Yes — and the bar bug is one corner of a wider
split, not an isolated case.** All read from source; none run.

## The root split

`metricRows` builds each row as `[label, value, metric]` (`:2431`):

```js
rows.push([metric.label, finiteNumber(metric.value,0), metric]);
```

The metric object — carrying `unit` — is at index **2**. **All fourteen diagram
renderers ignore it**, using only `row[0]` and `row[1]`. Every other display path
(`table`, KPI strip, Q&A answers, CSV export) goes through `metricValue`, which
is unit-aware.

So the diagram can never apply a unit rule, and everything else always does.

## Direction of error, by chart type

| Type | Diagram shows | `metricValue` shows | Error |
|---|---|---|---|
| `bar`, `matrix` | `62%` for a count | `62` | **adds** a unit that is not there |
| `donut`, `funnel`, `trend`, `radar`, `gauge`, `lifecycle`, `admission-*` | `62` for a `unit:"percent"` metric | `62%` | **drops** a unit that is there |
| any, for `unit:"SGD"` | `1234.5` | `SGD 1,234.5` | drops currency and separators |
| any, for `unit:"rating"` | `4` | `4/5` | drops the scale |
| any, large numbers | `1234.5` | `1,234.5` | drops thousands separators |

**The bar bug is the loud half; the quiet half is every other chart type
under-formatting.** A genuine percentage in a donut or trend chart renders as a
bare number with no `%` — the inverse mistake, and harder to notice because a
missing suffix looks like a plain count rather than an obvious contradiction.

The Part 1 snippet detects the **adding** case only, because that is the one the
table contradicts visibly.

~~The dropping case would need the metric's `unit`, which is not in the DOM — it
would need an API read to confirm.~~ **Corrected.** The table cell is rendered by
`metricValue`, so the unit is already applied and present in the DOM as a `%`,
an `SGD ` prefix, a `/5` or a thousands separator. Part 1B detects the dropping
case with DOM reads only.

## A genuinely separate pair: the KPI strip has two implementations

- Generic (`:2507`): `metricValue(metric)` → `Number(v).toLocaleString()`,
  default 3 fraction digits.
- Criterion 4 / 4.1.1 admission (`:2504`):
  `Number(v).toLocaleString(undefined,{maximumFractionDigits:2})` plus its own
  `unit==="percent"?"%":""`.

Measured: `96.7742` renders as **`96.774`** through the first and **`96.77`**
through the second.

**Update — the overlap is confirmed from source, and it is worse than a rounding
difference.** `CONFIG['4.1.1']['metrics']` and `admission_intelligence.kpis`
carry the **same four metric IDs**:

| ID | Label | `CONFIG` path | `admission_intelligence` path |
|---|---|---|---|
| `c411-applicants-total` | No. of Student Applicants | generic `evaluate_metric`, source `applicant`, mode `all` | bespoke count in `build_admission_intelligence` |
| `c411-shortlisted-approved` | No. of Shortlisted | mode `equals` | bespoke |
| `c411-enrolled-admitted` | No. of Enrolled Students | mode `equals` | bespoke |
| `c411-success-rate` | Success Rate | mode `ratio_status` | `round(admitted/applicants*100, 2)` |

Both are built by `UCC Analytics - Criterion 4.py` and both ship in the **same
API response**. So on Criterion 4 the KPI strip renders one computation and the
charts and tables render a different, independently-written computation of the
same four figures. The `96.774` / `96.77` pair is the visible symptom, not the
problem: the rounding differs because the *code* differs.

Two independent implementations of one figure will agree only for as long as
nobody edits one of them. **Parked deliberately, not closed** — no further
investigation until the two percentage procedures have been run.

## A third inconsistency, inside the "correct" function

`metricValue` is not internally consistent either (`:2364`):

```js
if(metric.unit==="percent") return String(value)+"%";     // no separators
if(metric.unit==="rating")  return String(value)+"/5";    // no separators
if(metric.unit==="SGD")     return "SGD "+Number(value).toLocaleString();
return Number(value).toLocaleString();
```

`1234.5` renders as `1234.5%` as a percentage but `1,234.5` as a count. Cosmetic,
but it means "go through `metricValue`" is not by itself a guarantee of
consistency.

## What this implies for the fix

It strengthens the case for **deleting** the heuristic rather than replacing it.
Adding a unit-aware suffix to `renderBars` alone would fix one corner and leave
the other thirteen renderers still dropping units — a partial fix that makes the
inconsistency harder to spot, not easier. If unit-aware diagram labels are ever
wanted, the change is to pass `row[2]` into all fourteen renderers and route them
through one shared formatter, which is a Sophia-side refactor well beyond this
two-line deletion.

## Sequencing

Independent of everything else. It does not touch chart binding, the publish
contract, or any Dashboard Studio schema, and it can ship before or after the
positional-binding question is settled.
