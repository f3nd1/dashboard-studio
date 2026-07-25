# Bar charts label counts as percentages

**Part 1** confirms it on the live site — read-only, Desk access only.
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

## Sequencing

Independent of everything else. It does not touch chart binding, the publish
contract, or any Dashboard Studio schema, and it can ship before or after the
positional-binding question is settled.
