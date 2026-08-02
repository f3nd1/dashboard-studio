# Live verification: does Sophia bind charts to data by position?

**Read-only.** Every step below is a read. Nothing writes, saves, or changes a
record. You need Desk access to the site and nothing else.

Two tests. **Test A** is the priority — it confirms or refutes positional
binding. **Test B** is a two-minute check that the repo's copy of the deployed
Custom HTML Block matches what is actually live.

---

## What is being tested

`custom-html-block/JAVASCRIPT.js:2399`, function `metricRows`:

```js
const metrics=(result?.metrics||[]).filter(item=>item.status==="available");
...
const size=Math.min(5,metrics.length), start=(chartIndex*size)%metrics.length, rows=[];
for(let i=0;i<size;i++){ const metric=metrics[(start+i)%metrics.length]; rows.push([...]); }
```

Read literally, a chart receives a five-metric window selected by its **ordinal
index**, not by anything identifying the chart. If that is what happens at
runtime, a chart's title and the numbers under it are unrelated by construction.

This was found by reading. It has never been run.

---

## Test A — positional binding

### Step 1

Open the Sophia dashboard page in Desk, the one containing the UCC Intelligence
Platform block. Let it finish loading (the progress overlay clears). Stay on the
**Analytics** workspace and pick any criterion — Criterion 4 or 5 give the most
charts. Note which subcriterion tab is active.

### Step 2

Open DevTools → Console. Paste this whole block and press Enter.

```js
(async () => {
  const root = document.querySelector('#uccIntelligencePlatform');
  if (!root) return console.error('Platform not found on this page.');
  const dash = [...root.querySelectorAll('[data-demo-dashboard]')]
    .find(d => !d.classList.contains('ucc-hidden'));
  const criterion = dash.dataset.demoDashboard;
  const tab = dash.dataset.demoActiveTab;
  const cfg = window.UCCLiveAnalytics.config[criterion];
  const section = (cfg.apiSections || {})[tab] || cfg.defaultSection;

  // Read-only API call — the same one the dashboard makes for itself.
  const res = await frappe.call({
    method: cfg.apiMethod,
    args: { payload: JSON.stringify({ action: 'summary', subcriterion: section,
                                      filters: {}, page_size: 100 }) },
    freeze: false,
  });
  let msg = res.message;
  for (let i = 0; i < 3 && typeof msg === 'string'; i++) { try { msg = JSON.parse(msg); } catch (e) { break; } }

  const all = msg.metrics || [];
  const avail = all.filter(m => m.status === 'available');
  console.log(`criterion=${criterion} tab=${tab} apiSection=${section}`);
  console.log(`metrics returned=${all.length}  available=${avail.length}`);
  if (!avail.length) return console.warn('No available metrics — inconclusive here, try another tab.');

  const defs = (window.UCCLiveVisualDefinitions[criterion] || {})[tab] || [];
  const size = Math.min(5, avail.length);
  const SPECIAL = /source availability|evidence readiness|source readiness|exception|gap|risk profile/i;

  const rows = [];
  defs.filter(d => d.enabled !== false).forEach((def, n) => {
    const idx = def.i ?? n;
    const card = dash.querySelector(`[data-demo-card="${CSS.escape(def.id)}"]`);
    if (!card) return;
    const actual = [...card.querySelectorAll('[data-demo-chart-table-body] tr')]
      .map(tr => (tr.children[0] || {}).textContent).filter(Boolean);
    if (!actual.length) return;                        // card not drawn yet
    const start = (idx * size) % avail.length;
    const predicted = Array.from({ length: size },
      (_, k) => avail[(start + k) % avail.length].label);
    rows.push({
      chart: def.title,
      index: idx,
      special_case: SPECIAL.test(def.title) ? 'yes' : '',
      predicted: predicted.join(' | '),
      actual: actual.join(' | '),
      match: SPECIAL.test(def.title) ? 'n/a'
           : (JSON.stringify(predicted) === JSON.stringify(actual) ? 'MATCH' : 'differs'),
    });
  });

  console.table(rows);
  const testable = rows.filter(r => r.match !== 'n/a');
  const matched = testable.filter(r => r.match === 'MATCH').length;
  console.log(`\nPositional prediction matched ${matched} of ${testable.length} testable charts.`);
  console.log(matched === testable.length && testable.length > 1
    ? '>>> CONFIRMED: charts are bound to data by ordinal index.'
    : matched === 0
      ? '>>> REFUTED: charts are not following the positional formula.'
      : '>>> MIXED — copy the whole table back, this needs a closer look.');

  // Second, independent signal: do different charts show identical data?
  const sigs = {};
  testable.forEach(r => { (sigs[r.actual] = sigs[r.actual] || []).push(r.chart); });
  const dupes = Object.values(sigs).filter(v => v.length > 1);
  console.log(dupes.length
    ? `>>> ${dupes.length} group(s) of DIFFERENT charts showing IDENTICAL data:`
    : '>>> No two charts share identical data.');
  dupes.forEach(g => console.log('    ', g.join('  ==  ')));
})();
```

### Step 3 — send me back

- The whole `console.table` output (right-click → *Copy table*, or screenshot).
- The three `>>>` lines.
- Which criterion and tab you ran it on.

Repeat on a second criterion if the first returns few metrics.

### How to read the result

| Result | Meaning |
|---|---|
| `CONFIRMED` **and** duplicate groups listed | Positional binding is real. Chart titles do not describe their contents. |
| `CONFIRMED` but no duplicates | Positional binding is real; this section happens to have enough metrics that windows do not overlap. Still confirmed. |
| `REFUTED` | The rendered data comes from somewhere my reading missed. Send the table anyway — the `actual` column tells me what it really binds to. |
| `MIXED` | Some charts follow it, some do not. Most likely more title special-cases than the two regexes I found. |
| "No available metrics" | Inconclusive on that tab — every source is permission-blocked or unresolved for your account. Try another. |

### Optional Test A2 — the permission variance

Only if Test A confirms. Have a **second person with fewer permissions** run the
same snippet on the **same criterion and tab**, and send back just these two
lines:

```
metrics returned=…  available=…
```

If their `available` count differs from yours, the window start positions shift
for them, so **the same chart shows them different metrics under the same
title**, with nothing on screen indicating it. That is the more serious half of
the finding.

---

## What a confirmation would mean, in plain terms

If Test A confirms:

1. **A chart's heading does not describe the numbers beneath it.** "Applicants
   per Country" displays whichever five metrics fall at that card's position in
   the list. Any apparent match between a title and its data is coincidence, or
   the result of someone having ordered the metrics to make it look right.

2. **Editing a Server Script silently rearranges every chart in that section.**
   Adding one metric, removing one, or reordering them shifts every window.
   Nothing errors, nothing warns, and the dashboards keep rendering.

3. **Two members of staff can see different figures under the same heading.**
   Permission filtering runs *before* the window is chosen, so a colleague who
   cannot read one source does not simply lose that metric — their windows shift
   and every chart in the section shows them something different.

4. **For EduTrust evidence specifically:** any figure taken from these dashboards
   and used as evidence is only as trustworthy as the coincidence in point 1.
   A screenshot of a chart is not proof of what its title claims. Until this is
   settled I would not cite a number from an affected dashboard without checking
   it against the underlying records directly.

If Test A refutes it, points 1–4 do not apply and I will correct the finding in
`docs/PUBLISH_TO_SOPHIA_DESIGN.md` §2 and the annex, and the publish design's
"identity binding is a precondition" conclusion needs revisiting.

**Nothing has been changed in either repository to address this.** No fix is
proposed until it is confirmed.

---

## Test B — is the repo's copy of the deployed block current?

Separate concern, two minutes. `custom-html-block/` **is** committed in
`f3nd1/intelligence-dashboard` (at `49361a8`), so it is not unbacked. What is
unknown is whether that commit matches what is live right now —
`PACKAGE_CHECKSUMS.json` records hashes matching neither the repo nor `dist/`,
so it cannot answer this.

Paste into the same console:

```js
(async () => {
  const list = await frappe.db.get_list('Custom HTML Block', { fields: ['name'], limit: 50 });
  console.log('Blocks on this site:', list.map(b => b.name).join(', '));
  for (const b of list) {
    const doc = (await frappe.call({ method: 'frappe.client.get',
      args: { doctype: 'Custom HTML Block', name: b.name } })).message;
    for (const field of ['html', 'style', 'script']) {
      const text = doc[field] || '';
      if (!text) continue;
      const buf = new TextEncoder().encode(text);
      const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', buf))]
        .map(x => x.toString(16).padStart(2, '0')).join('');
      console.log(`${b.name} | ${field} | len=${text.length} | sha256=${hash}`);
    }
  }
})();
```

Send back every line it prints. Compare against the committed copy:

| Field | File | Length | SHA-256 |
|---|---|---:|---|
| `html` | `HTML.html` | 16003 | `7997cc42…12dcea4` |
| | *(no trailing newline)* | 16002 | `97daedce…4437768b` |
| `style` | `CSS.css` | 151220 | `ca4e28df…4e0e5c2f` |
| | *(no trailing newline)* | 151219 | `738efbb7…de0a6076` |
| `script` | `JAVASCRIPT.js` | 227328 | `266c6b9b…2d4a823e` |
| | *(no trailing newline)* | 227327 | `53b0d2f5…3f1d00b6` |

A length within a byte or two with a non-matching hash usually means line-ending
or trailing-whitespace differences and is fine. A **materially different length**
means the live block has drifted from the commit, and the live version is the one
that should be captured.
