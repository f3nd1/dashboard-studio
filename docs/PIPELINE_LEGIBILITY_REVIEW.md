# Making the pipeline legible from inside a workspace

Investigation only. **Nothing built, no code changed.** Line references are to
the current `main`.

The complaint, restated: four publish preconditions exist and all four are
invisible until they refuse. The rules are right; their timing is wrong.

---

## 1. Where the gate lives, and whether it can be displayed

**Four rules, two places, both inside `advance_status`:**

| Rule | Where | Reads |
|---|---|---|
| Scope is set | `governance.py:114-120`, inline | `DS Dashboard.subcriterion` |
| Scope is a code Sophia knows | `:121-126`, inline | `edutrust.SUBCRITERIA` |
| Every chart has a metric | `_refuse_unpublishable_charts:161` | `DS Chart.metric` |
| Every chart has a passing comparison newer than its last edit | `:171-186` | `DS Validation Comparison` |

**Yes, they can be evaluated for display, and cheaply.** All four are already
pure reads — nothing in the gate mutates anything, and `_refuse_unpublishable_charts`
is a query-and-compare with a `frappe.throw` at the end. Only the presentation
is refusal-shaped.

The refactor is one function, not a second implementation:

```
publish_blockers(dashboard) -> [{rule, blocks, charts: [...]}]   # facts
advance_status(...)  -> if blockers: frappe.throw(...)           # refusal
get_studio_dashboard -> "readiness": {...}                        # display
```

**One definition, two presentations.** This matters more than usual right now:
`docs/SOPHIA_FAULT_PATTERN.md` was written this week about a codebase where the
same figure is computed twice by two code paths. Computing "is this publishable"
separately for the strip and for the gate would reproduce that fault in our own
repo, and the divergence would be invisible until a dashboard displayed *ready*
and then refused.

### Cost

Today the gate costs **2 + N queries**, N = chart count, because of the
per-chart loop already flagged at `governance.py:169`. Batching it —
`filters={"chart": ["in", names]}` — makes it **3 queries flat**, independent of
chart count. So making the rules displayable also retires that ponytail ceiling;
the display path pays for the refusal path.

### Where to put it

**Fold `readiness` into `get_studio_dashboard`'s existing payload. No new
endpoint.** The Builder already calls it on open, after add, after delete and
after reload, so the strip updates on paths that already exist. A separate
endpoint would be right only if we wanted to poll it, and we don't.

Honest cost: three places need to drop the cached readiness so it does not go
stale — after `run_validation` (`studio_app.js:1597` already does exactly this
for `state.comparisons`), after `advance_status`, and after a chart's metric
changes. Same shape as the invalidation already there.

---

## 2. Is the readiness strip the answer? No — wrong place, and partly built

**Two of the four rules are already surfaced in the Builder, passively:**

- `studio_app.js:868` — a card with no metric renders **"No metric linked"**.
- `:709` — the scope selector's hint already says *"Required before publishing —
  an unscoped dashboard has no section to publish into."*

So the Builder is not silent. What it lacks is the *aggregate* and the other two
rules. A canvas strip would be a third rendering of a fact the Builder already
shows twice.

**And the complaint is not Builder-scoped.** "From inside any one workspace I
cannot tell what stage I am at" — a canvas strip answers it in one of five.

### The smaller change

`dss-toolbar` (`:571`) is **the only element rendered in all five workspaces**.
It already hosts a status chip — `dss-savestate` at `:576` — currently gated to
`view === "design"`. The slot exists; it is just narrowly scoped.

Proposed, in order of value per line:

| # | Change | Cost | Coverage |
|---|---|---|---|
| 1 | Stop discarding the reason. `:1915` catches a refusal and toasts **"That move was refused."**, replacing a server message that names every offending chart. | ~2 lines | Governance |
| 2 | Readiness chip in the toolbar: `Draft · 3 of 5 charts ready to publish`, click → Governance. | ~20 lines + the server field | **all five** |
| 3 | The named blocker list on Governance, **above** the transition buttons. | ~15 lines, same payload | Governance |

(1) is worth checking on the live site before doing anything else: Frappe usually
raises its own dialog for a server `throw`, so the named reasons may already be
reaching you underneath a toast that says less. Either way our own message is
worse than the one we already computed.

**No canvas strip.** Skipped: the Builder-only readiness band from the mockup —
(2) covers the Builder and four other workspaces for the same cost.

---

## 3. Dead ends — states that assert a fact and offer no action

| Where | Text | Verdict |
|---|---|---|
| `:1558` Validation | "No chart on this dashboard has a metric, so there is nothing to validate yet." | **Dead end.** Names the blocker, offers no way to Builder. |
| `:1819` Governance | "No dashboard selected." | **Dead end.** The picker exists in the toolbar; this does not say so or open it. |
| `:1396` Data & DocTypes | "Could not load the catalogue." | **Dead end.** No retry. |
| `:1534` Validation | "Could not load comparisons." | **Dead end.** No retry. |
| `:1808` Governance | "Could not load governance." | **Dead end.** No retry. |
| `:2078` Mapping | "No mappings yet." | Soft — the SQL import sits above (`:641`), but the message does not point at it. |
| `:1640` Validation | "No comparisons recorded yet." | **Soft, and your reading was off by one screen** — see below. |
| `:1015` | "Saved, but the dashboard could not be reloaded. Refresh to see it." | Soft. Asks for a manual action instead of offering it. |
| `:1888` Governance | "No changes recorded yet." | Fine. Nothing to offer; Frappe writes Versions itself. |
| `:1686` Validation | "No per-group detail recorded for this run." | Fine. A fact about an old record. |
| `:1587`, `:2123`, `:359`, `:524` | "…needs the server (not available in sample mode)." | Fine. Correct refusal in demo mode. |
| `:280` picker, `:496` empty state | "No dashboard matches…" / "No dashboards yet" | Fine — both offer create. |

### One correction to the premise

**Validation is not actionless.** `buildValidationRun` (`:1541`) renders a full
"Step 1 — reference result" form with a chart picker, a paste box and a **Run
validation** button, above the results table. What you'll have hit is the
collapse at `:1556-1560`: it filters to charts that *have a metric*, and if none
do, the whole form is replaced by a single note.

That branch became reachable **because of the 417 fix**. Dropping `reqd` from
`DS Chart.metric` was the right call — `create_chart` had to be able to insert a
card before a metric is chosen — but it created a state that did not previously
exist: a dashboard whose charts have no metric. Three surfaces dead-end on it
(Validation collapses, the card shows "No metric linked", publishing refuses),
and none of them says *link a metric in the panel on the right*, which is the
one sentence that resolves all three.

**Pattern for the whole table:** every one of these knows the remedy at the point
it prints the fact. The fix is not new UI, it is finishing the sentence.

---

## 4. Stage state on the tabs — argue both, then decide

**For.** The tabs are the only persistent navigation. The work genuinely is a
pipeline. A dot per tab costs almost nothing and is the most obvious place to
look.

**Against, three reasons, and they win:**

1. **Only three of the five workspaces have per-dashboard state at all.**
   Builder, Validation and Governance do. **Data & DocTypes is a site-wide
   catalogue** (`catalogue.get_catalogue`, no dashboard argument) and
   **Metabase Migration is a project**, not a stage of the open dashboard.
   Marking those two would mean inventing state to fill the row — a lie in
   service of visual symmetry.
2. **A tick on Validation would decay silently.** The rule is per chart *and*
   recency-sensitive: a pass older than the chart's last edit does not count
   (`governance.py:182`). So "done" becomes false the moment someone drags a
   card, with no event to repaint on. A tick that goes stale is worse than no
   tick, because it is trusted.
3. **It would assert an order the product does not have.** A hand-built
   dashboard never touches Migration; showing it "not started" reads as debt.

**Position: no stage state on the tabs.** The stage belongs to the *dashboard*,
not to the workspaces. One chip that names the dashboard's stage and its blockers,
in the toolbar, says everything the tab dots would say — without claiming the
tabs are sequential, and without inventing state for the two workspaces that
have none.

That is also why it is cheaper: one chip to keep fresh, not five.

---

## 5. Copy patterns — proposed, not applied

### a. Save verbs

Not one pattern — **two families, and the confusion is that they look alike:**

- **`Save <noun>`** — writes the open record. "Save layout", "Save mappings".
  Already consistent, and the noun is honest: `saveLayout` really does write
  every chart (`:2283`).
- **`<verb> <object>`** — does something with a consequence. "Run validation",
  "Submit for technical review", "Approve and publish", "Accept…".

**"Submit for technical review" should not become a Save.** It is not one — it
hands work to someone else and changes who may edit it. The pattern to apply is
*visual*: the two families should not share `dss-btn-primary` in the same
toolbar, so a transition never looks like a save.

### b. Picker accessible name — "1234Draft"

Two sibling spans, no separator (`:309-310`), so the button's accessible name is
their concatenation.

**Pattern: any row composed of visual fragments gets an explicit `aria-label`
naming the parts, comma-separated.**

```
row.setAttribute("aria-label", core.dashboardTitle(d) + ", " + (d.status || "Draft"));
```

Applies to any future composite row, not just this one. Do not fix it with
whitespace — that repairs the reading and leaves the structure fragile.

### c. "— Not scoped —"

**Pattern: an empty option is a prompt, phrased as an instruction and marked with
an ellipsis; never a value phrased as a state.**

→ **"Choose a subcriterion…"**

The state is already carried twice elsewhere — the hint below (`:709`) says it is
required, and the kicker at `:620` disappears when unscoped. The option does not
need to carry it a third time.

### d. Palette hint

> "Adds a card below the existing ones. Drag it to position, then link a metric
> in the panel on the right."

Three instructions on a control that does one thing.

**Pattern: a hint states the control's immediate effect, once. Consequences move
to where they happen.**

- Keep: *"Adds a card below the existing ones."*
- "Drag it to position" — the cards are visibly draggable; drop it.
- "link a metric in the panel on the right" — **this is the sentence the card at
  `:868` should be saying**, where the empty card is, at the moment it matters.
  Moving it also fixes dead end #1 in §3.

---

## The cheapest change that fixes the complaint

Three things, in this order:

1. **`publish_blockers()` extracted from the gate** — one definition, batched to
   3 queries, returned inside `get_studio_dashboard`'s existing payload.
2. **A readiness chip in `dss-toolbar`**, present in all five workspaces, naming
   the stage and the blocker count, clicking through to Governance.
3. **Finish the sentence in every dead-end state** — each already knows the
   remedy at the point it prints the fact.

(3) needs no server work at all and fixes most of the felt problem. (1) and (2)
are the part that makes "what blocks publishing right now" answerable before
Governance refuses.

Skipped: the mockup's canvas readiness strip, stage state on tabs, and any
change to the four rules themselves. Not touched here: the data catalogue,
filter strip and properties-panel items — separate conversation, as instructed.
