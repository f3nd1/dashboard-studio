# Architecture Decisions

## ADR-001 — Generic product name

Decision: Use Dashboard Studio as the product and repository identity.

Reason: Metabase is one source and Sophia is one destination. The core capability is generic migration, design, validation, and publishing.

## ADR-002 — Proper Frappe app

Decision: Build a separate Frappe app installed in the same Frappe/ERPNext site.

Reason: The product requires modular Python, managed DocTypes, permissions, background jobs, tests, and secure server integrations.

## ADR-003 — Metadata-driven dashboards

Decision: Store datasets, metrics, components, layouts, and filters as structured records.

Reason: Normal dashboard changes should not require replacement of large Python and JavaScript files.

## ADR-004 — AI proposes, server validates

Decision: AI produces structured proposals only.

Reason: Prevent arbitrary SQL execution, restricted-field exposure, and unapproved publishing.

## ADR-005 — Incremental migration

Decision: Keep existing dashboards and migrate one validated vertical slice at a time.

Reason: Reduces operational risk and enables result-parity checks.

## ADR-006 — Do not translate Metabase MBQL into Insights operations *(superseded by ADR-007)*

Decision: A GUI-built Metabase card is handled by taking SQL that **Metabase itself** produced — a human copying it from the View-SQL panel today, or `POST /api/dataset/native` if that permission is ever granted. Dashboard Studio does not translate MBQL into Frappe Insights' `Operation` list.

Reason: Both vocabularies were read from source before deciding (Metabase `lib/schema.cljc`, `lib/schema/ref.cljc`; Insights v3.12.2 `query.types.ts`). Translation is mechanically possible for simple shapes and requires: resolving `source-table` and every field ID through two new Metabase endpoints; mapping MBQL 5 clauses, whose options map sits at position 1 rather than last; and supplying a `data_type` on every `Dimension` and `Measure`, which MBQL does not carry.

The cost is not the code, it is the ownership. A translated query that disagrees with what Metabase shows produces a **different number with no error** — the fault `docs/SOPHIA_FAULT_PATTERN.md` names: *"they do not fail, they disagree."* Taking Metabase's own SQL keeps Metabase the authority on what a question computes.

The coverage argument does not survive contact either: translation is unambiguous exactly where a human could rewrite the query in a minute (single table, one breakout, one count), and reaches for `ExpressionMeasure` / `CustomOperation` — generating query-language text — exactly where automation would be worth having. Its safety is inversely correlated with its usefulness.

Revisit only if Metabase's compiled-SQL endpoint is ruled out permanently AND a specific, counted set of cards is blocked by nothing else.

## ADR-007 — Translate MBQL, behind a human verification gate (supersedes ADR-006; *gate removed by ADR-008*)

Decision: Dashboard Studio DOES convert a GUI-built Metabase card into Insights v3 operations — and every converted query carries an `[UNVERIFIED]` marker in its title until a person has compared its number against the Metabase card it came from.

Reason: clickable Operations are maintainable in a way a pasted block of SQL is not, and re-pasting SQL for every report is a recurring cost. ADR-006's objection is not withdrawn — a translation that disagrees with Metabase still returns a different number with no error — so it is answered rather than dismissed. The gate is the answer, and it is load-bearing rather than advisory: a mismatch refuses and leaves the marker, there is no "verify anyway", and the marker lives in the title so it travels into Insights where somebody who never saw Studio still sees it.

What made the second attempt viable where the first was not: both formats were read from source at the installed versions (Metabase `lib/schema.cljc`, `schema/join.cljc`, `schema/ref.cljc`; Insights v3.12.2 `query.types.ts`) rather than assumed on either side.

Scope is a rule table, not a compiler. Compound aggregations, custom columns, limits, sorts, explicit column selections, multi-stage queries, date buckets and questions built on other questions all refuse by name and hand back no operations — a partial translation is a query that answers a different question.

## ADR-008 — Remove the verification gate (supersedes ADR-007's condition)

**Decision.** The number-comparison step and the `[UNVERIFIED]` title marker are removed. A converted query is written to Insights under the title the user chose, with nothing recording whether anybody has checked it.

**Requested explicitly**, superseding ADR-007's condition: *"Remove the verification row entirely — the 'Same number? [x] = [y] Confirm' control, and the number-comparison gate behind it. This supersedes the earlier decision to keep it; the check is being dropped by choice."*

**The marker went too, rather than staying as a permanent label.** Both were offered. A marker that no mechanism can ever clear would be on 100% of converted queries, so it would distinguish nothing — it would read as a warning while carrying no information, and the first person to notice that would strip it by hand. Removing it is the honest version of the same state.

**What this costs, stated plainly so nobody rediscovers it as a surprise.** ADR-006's objection was never withdrawn, only answered; the gate was the answer, and it is now gone. A translation that disagrees with the original **does not fail, it returns a different number** — `SOPHIA_FAULT_PATTERN.md`, *"they do not fail, they disagree."* Nothing in the tool now detects that case, and nothing on the record marks a converted query as unchecked.

**What still stands in its place**, and is therefore now the whole of the safety argument:

- The refusal table in `integrations/metabase/sql_ops.py` and `parser.py`. Anything that cannot be translated with certainty refuses **by name** and writes **no operations**. That is the only remaining protection, so softening a refusal to make a query go through now costs more than it did before this ADR.
- Column names are checked against the table's real schema before anything is written, so a query that would not run refuses here rather than in Insights.
- The operations are listed back in readable form after conversion. That was never part of the number check — it is how somebody spots a wrong translation by reading it, and it remains.

**If the gate is ever wanted back**, it is intact in `archive/api_convert_verification_gate.py` with its tests in `archive/test_convert_gate_verification.py`. The non-obvious part is `_THOUSANDS`: it stops `"12,34"` being read as 1234, which across most of Europe means 12.34 — a hundredfold disagreement passing silently, inside the one function whose job was catching a disagreement.

## ADR-009 — Allow an explicit `* 1` cast on a text column, because the source field is mistyped

**Decision.** `AVG(`col` * 1)` where `col` is a text column converts, rather than refusing. The measure records `coerced_from: "String"`, and Studio's operations list says *"String coerced to a number"* next to it.

**Why.** Metabase writes `* 1` to cast a column to a number before aggregating it. At UCC it does this to `actual_value` on *Quality Performance Actual Value Parameter Childtable*, which is a Frappe **Data** field — so the live report has been averaging a text column by silent MySQL coercion all along. Refusing it blocks a real, in-use report; the cast is the only reason that report works.

**Why it is recorded rather than waved through.** Every row whose value is not a number coerces to `0` and is averaged in as zero. That behaviour is inherited from Metabase, not introduced here — but nothing else about the converted query would show it, and someone reading the Insights query a year from now would see an average over a field they assume is numeric. So it is stated in the measure and on screen.

**Still refused in a GROUP BY.** Grouping by `col * 1` groups every non-numeric row together under `0`, which is not grouping by the column. That refusal names the coercion explicitly rather than falling back to a generic "subquery".

**The proper fix is not here.** `actual_value` should be a **Float** or **Currency** field in Frappe. Then the coercion disappears from Metabase's SQL, the average is over real numbers, and rows that are currently silently zero become visible as bad data instead.

**AMENDMENT 1 (live testing).** The allowance could not be delivered as first written. A measure's `data_type` DESCRIBES the result; it does not ask Insights to convert anything. The converted query reached the engine with the text column untouched and failed at run time with `'StringColumn' object has no attribute 'mean'` — the conversion looked successful and broke a step later, which is the failure mode this project refuses to ship. It was made to refuse by name rather than guess `CastArgs`, since an unrecognised key is dropped silently and a guess would fail identically while looking fixed.

**AMENDMENT 2 (the shape, read from source).** `query.types.ts` at v3.12.2 gives `Cast = { type: 'cast' } & CastArgs` and `CastArgs = { column: Column; data_type: ColumnDataType }`, with `ColumnDataType` including `'Decimal'`. So the conversion is an **operation of its own**, not an attribute of the measure. The converter now emits

```json
{"type": "cast", "column": {"type": "column", "column_name": "actual_value"}, "data_type": "Decimal"}
```

**after the filters and immediately before the `summarize` that reads the column** — which is where `* 1` sat in the original SQL: scoped to the aggregate, not to the WHERE. Casting earlier would retype the column the filters were already compared against as text. `coerced_from` is back on the measure and back on screen; it is not part of Insights' `ColumnMeasure` and is dropped there, and it exists so the operations list can say the source field is text.

The emitted dict is asserted **in full** — exactly `type`, `column`, `data_type` — in `test_sql_to_operations.TestACoercedTextColumn` and end to end over the real report fixture in `test_metabase_unwrap.TestTheRealReportEndToEnd`, because an extra key Insights drops in silence fails at run time in exactly the way the cast was added to prevent.

Two narrowings that came out of it: `COUNT(col * 1)` emits **no** cast (counting text is fine, and converting first would change what is counted), and `GROUP BY col * 1` is refused generically now — a grouping item that is not exactly one column is refused rather than skipped, because `_QUALIFIED` is anchored and the item was previously dropped in silence.

**Fixture-tested, not live-verified.** Running the cast in Insights is a step only the user can take from the live site.

**How big is the problem before anyone retypes anything.** `actual_value` was found by one report failing. `scripts/numeric_fields_typed_as_text.py` reports every text field on the site holding numbers, judged by its **values** and not its name, and separates the wholly-numeric fields (retype cleanly) from the mostly-numeric ones (retyping surfaces rows that coerce to 0 today — a content decision, not a schema one). Read-only, hand-run on the live site. Retyping is a decision to take with that list in hand, not one field at a time as reports break.

**This rule exists only because the source field is mistyped.** If `actual_value` (or any other field this applies to) is corrected, revisit this rather than leaving it as permanent behaviour: an allowance for a specific defect should not outlive the defect. The narrow scope is deliberate — an *explicit* `* 1` in the SQL, as an aggregate argument only. Averaging a text column without that cast still refuses by name.

## ADR-010 — Use `POST /api/dataset/native` to export GUI-built cards, and only that

**Decision.** `scripts/metabase_export_sql.py` asks Metabase to compile a GUI-built card's MBQL to SQL, so all ~200 reports can be exported in one run instead of copied one at a time out of the View-SQL panel. Every other Metabase call in this project stays a GET.

**This is ADR-006's own route, not a new one.** ADR-006 decided that a GUI card is handled *"by taking SQL that Metabase itself produced — a human copying it from the View-SQL panel today, or `POST /api/dataset/native` if that permission is ever granted"*. The reason it gave still holds and is the reason to prefer this over translating MBQL ourselves: taking Metabase's own compiled SQL keeps **Metabase** the authority on what a question computes. The alternative — skipping GUI cards — would export almost nothing, since every capture UCC has produced so far is compiled MBQL.

**What the endpoint does and does not do.** It compiles and returns text. It does not execute, so no rows are read from the production database and no load is put on it, and it writes nothing to Metabase.

**The risk is not the endpoint, it is its neighbours.** `POST /api/dataset` and `POST /api/card/:id/query` differ by one word and both EXECUTE against production. So the protection is structural rather than careful:

- one `requests.post` in the file, asserted by count in the test;
- its path checked **at the call site**, not merely stored in a variable, so redirecting it means deleting a line that says what it protects — a mutation that changes the constant makes the run refuse rather than post;
- the test greps the source for the executing spellings and asserts the recorded calls are exactly one, to `/api/dataset/native`;
- `compile_gui_cards = False` gives a GET-only run, tested, in which GUI cards are listed by name for manual export and nothing is POSTed at all.

**A 403 is an answer, not a failure.** Metabase has no read-only key flag; whether the key's group may compile is a fact about the key. If it answers 403 the cards are listed under PERMISSION and the rest of the run still exports. The durable control on the Metabase side remains a SELECT-only database login, which is unaffected by any of this.

**Not verified live from here.** This container has no route to Metabase, so the endpoint's behaviour is asserted against a recording stub and taken from Metabase's documented contract and ADR-006's reading of it. `card_limit` exists so the first real run can be a handful of cards rather than 200.

## ADR-011 — Translate arithmetic over aggregates into a `summarize` + a `mutate`

**Decision.** A SELECT item that computes over aggregates — `( AVG(a) + AVG(b) ) / 2`, `SUM(x) * 100 / COUNT(*)` — is translated. Its aggregates become the measures of one `summarize`, and the item itself becomes a `mutate` after it. Everything else in a computed item still refuses **by name**.

**The shape was read, not guessed**, out of a hand-built Insights query's own Operations JSON at v3.12.2:

```json
{"type": "mutate", "new_name": "combined_avg", "data_type": "Auto",
 "expression": {"type": "expression",
                "expression": "(avg_of_idx + avg_of_docstatus) / 2"}}
```

The finding that makes this tractable at all: `expression.expression` is **plain text maths referencing the `measure_name`s the preceding `summarize` defines** — not a nested AST, not a special function syntax. So the translation is: build the measures, then write their names into the string.

**The names are taken from the measures, never rebuilt.** The parser leaves numbered slots where the aggregate calls were, and `_expression_measures` fills them with the `measure_name` the summarize actually emitted. Rebuilding `avg_of_x` in a second place is how the two drift, and the drift only shows up as a run-time error in Insights.

**`data_type` is `"Auto"`**, which is what Insights itself stored. Naming a type there would claim a conversion this does not perform — ADR-009 is the scar.

**What is allowed is an ALLOWLIST, because the output is text Insights evaluates.** With the aggregate calls removed, what remains may be only `+ - * / ( )`, numbers and whitespace. A token nobody has read the meaning of must not travel into a string a query engine will execute. `CAST`, `YEAR`, `CONCAT`, a bare column, a string literal — each refuses naming the token that stopped it.

**CAST: asked directly, and the answer is that it needs its own evidence.** `CAST( AVG(a) + AVG(b) AS double ) / 2.0` is the common Metabase spelling and it refuses. Three routes were considered and none is provable today:

- *Put `cast(...)` in the expression string.* Whether Insights' expression language has a cast function, and what it is called, has not been read. A wrong guess is silently dropped and fails at run time while looking fixed — exactly ADR-009's first delivery.
- *Use the existing `cast` OPERATION.* It is not interchangeable: `CastArgs` is `{column, data_type}`, so it converts a **named column**. `CAST(<expression> AS double)` converts the result of an expression, which is not a column at any point in the pipeline.
- *Cast each measure first, then add.* Arithmetically equivalent for numeric aggregate outputs, and it would need one fact nobody has: that a `cast` operation applies to a **measure** column after a `summarize`. That has never been observed; every cast this project has emitted sits before one.

So CAST refuses, and the refusal says outright that the cast operation is not the answer, because that is the first thing a reader will reach for. **One live check settles it**: build a calculated column in the Insights UI that casts, and read back what it stores — the same loop that produced the chart config, the `cast` shape and this expression dialect.

**Dropping the CAST was rejected.** In MySQL `CAST(x AS double)` before a `/` is defensive rather than semantic, so dropping it would *probably* return the same number. "Probably the same number" is the thing this project refuses to ship: a translation that disagrees does not fail, it disagrees.

**Narrower than it looks, and the flagship capture still refuses.** `Staff Onboarding Survey … --1680.sql` has an arithmetic-only outer SELECT and is still blocked, because its inner wrapper renames with `qn_1 * 5` and `_WRAPPER_ITEM` allows `* 1` only. A scale factor inside an aggregate's argument is a *different* capability — Insights' measure is `{column_name, aggregation}` with nowhere to put `* 5` — and it would need a `mutate` BEFORE the `summarize`, whose ordering is likewise unobserved. So "703 reports have an arithmetic-only outer SELECT" is not "703 reports now convert"; re-running the dry run is what says how many do.

Also refused, deliberately: an aggregate inside a computed column *and* another standing alone (two questions in one query), and arithmetic with no aggregate in it (a per-row computed column, which is not a measure).

**AMENDMENT (2026-08-05) — the expression LANGUAGE is still one captured example wide.** The capture that settled this shape, `"(avg_of_idx + avg_of_docstatus) / 2"`, is pure arithmetic. It says nothing about whether the language has `YEAR()`, `CONCAT()`, `CAST()` or any function at all, so the allowlist stays arithmetic-only and every function refuses by name. `scripts/insights_operations_probe.py` prints every `mutate` expression Insights has actually stored and tallies the functions in them; one that calls a function widens the allowlist to exactly the functions seen, and no further. Finding none is reported as **"NO FUNCTION SEEN — and that is not 'the language has none'"**, with the UI step that settles it.

**A wider allowlist would not, by itself, unblock the date/label reports.** The `tabQuality Action` capture is the worked example:

```sql
SELECT `__mb_source`.`Year`, AVG(`__mb_source`.`custom_..._api`)
FROM ( SELECT CAST(`tabQuality Action`.`custom_..._api` AS double) AS `custom_..._api`,
              CONCAT('', YEAR(`tabQuality Action`.`custom_proposed_date`)) AS `Year`
       FROM `tabQuality Action` ) AS `__mb_source`
GROUP BY `__mb_source`.`Year`
```

Its functions are in the **inner** wrapper, computing per-row columns BEFORE the aggregate — they are not arithmetic over aggregates, and the outer expression check is never reached. Traced through all three wrapper rules: `unwrap_` declines (the inner computes, so it is not a pure projection), `drop_` declines (the outer aggregates), `lift_` declines (`_WRAPPER_ITEM` takes a qualified column with an optional `* 1`, not a function call). The refusal is "subquery", and it is correct.

Unblocking that shape needs **two** things beyond the dialect: `lift_renaming_wrapper` accepting a computed inner item, and a `mutate` emitted **before** the `summarize` so the grouping has a real column to name. Mutate-before-summarize has never been observed — every mutate this project emits sits after one — and it is the same unobserved ordering the `qn_1 * 5` case needs. So this is one capability short of ADR-011, not one allowlist entry short of it.

**AMENDMENT (2026-08-05, second) — two of the three unknowns are now settled, by a query built by hand in Insights.**

1. **The expression language HAS functions, and `year` is spelled lowercase.** A calculated column `year(custom_proposed_date)` was built on `tabQuality Action` and returned 2023/2024/2025/2026. So the allowlist is not permanently arithmetic-only; it may widen to functions that have been *seen*, exactly as this file already said.
2. **A `mutate` may precede a `summarize`.** That calculated column was then used as the grouping of a Group & Summarize (avg by `year_col`, returning 2023→1, 2024→0.84, 2025→0.69, 2026→0.36). It ran, so the ordering is valid — and it has to be, since a grouping cannot name a column that does not exist yet. This retires "mutate-before-summarize has never been observed", which was blocking both the `qn_1 * 5` case and the date/label family.

**What is still missing, and why it is not a formality.** Metabase does not write `YEAR(date)` on its own — it writes `CONCAT('', YEAR(date))`, and the `CONCAT` is load-bearing: it turns the year into a **text label** so the chart gets a categorical axis. Translating that as `year(date)` alone would change the column's type, which lands straight on the one question still open — whether `DIMENSION_DATA_TYPES` genuinely excludes a numeric grouping. So this shape needs one of:

- the `data_type` Insights stored for the `year_col` dimension in the query above (if it is Integer or Decimal, the dimension restriction is ours and comes out), **or**
- `concat` confirmed in the expression language the same way `year` was.

Both come from the same place: the stored Operations JSON of the query that was just built. `scripts/insights_operations_probe.py` reads exactly that — every mutate expression whole, the dimension data_types with examples, and the stored operation ORDER — so no screenshot or hand-copying is needed.

**Nothing has been built on these two facts yet, deliberately.** Emitting a pre-summarize mutate needs a `data_type` for the dimension it feeds, and choosing one without reading what Insights stored is the guess ADR-009 paid for twice.

## ADR-012 — A wrapper that COMPUTES becomes operations before the summarize

**Decision.** A Metabase wrapper whose items compute rather than rename is lifted, and each computed item becomes an operation placed **before** the `summarize` that reads it: `CONCAT('', YEAR(d)) AS Year` → a `mutate` `Year = year(d)`, `CAST(v AS double) AS v` → a `cast`. `DIMENSION_DATA_TYPES` is deleted, so a grouping may be a number.

**Three facts made this possible, and all three were read off the live site rather than reasoned about** (probe output 2026-08-05):

- **Insights accepts a numeric grouping.** Query `s39rc7j648` stores a dimension typed `Integer` (`year_col`). `DIMENSION_DATA_TYPES` came from the archived chart path, where its own comment said *"these are not our rules, they are the ones the CHART RENDERER applies"* — it picked a chart's x-axis there. Applied to `summarize.dimensions` it was ours, and it was wrong. Gone.
- **The expression language has functions, and `year` is lowercase.** Two stored expressions on the site, one of them `year_col = year(custom_proposed_date)`. The allowlist widens to **exactly `year`** — `MONTH`, `DAY` and `QUARTER` refuse by name however reasonable they look, because the vocabulary widens only to what has been observed.
- **A `mutate` may precede a `summarize`.** Stored order on that query: `source -> mutate -> summarize`. Read from the record, not the UI's display list.

**`CONCAT('', x)` is dropped, and that is a judgement worth stating.** Metabase writes it to turn the year into a TEXT label so the chart axis is categorical. Since Insights groups by a number quite happily, the wrapper goes and the value keeps its own type — the rows are the same years either way, only the column's type differs. `CONCAT('FY', x)` is a different matter and **refuses**: that prefix is part of the label, and dropping it would relabel every row silently.

**`CAST` here is the operation, not the expression.** `CAST(v AS double) AS v` becomes a real `cast`, which converts a column in place. `CAST(v AS double) AS renamed` refuses: `CastArgs` is `{column, data_type}` with nowhere to put a new name, so casting and renaming is two things and only one is expressible. This is the same reason ADR-011 still refuses `CAST(<expression> AS double)` — that one converts a result that is never a column, and nothing has changed about it.

**What the join carries is the column the computation READS**, never the name it produces. `Year` is created by the mutate and belongs to no table; `custom_proposed_date` has to come across the join or the mutate has nothing to read. Both directions are tested.

`dashboard_studio/tests/fixtures/year_label_then_group.sql` is the reported capture, asserted end to end.

**Still refused, and worth knowing before assuming this generalises**: any function but `year`, a `CONCAT` that really concatenates, a `CAST` that renames, and a computed item this cannot read at all. Each names the token that stopped it.

## Known unsupported — recorded, not scheduled

**Quality Performance Outcomes** (real UCC report) is no longer blocked. It refused for three reasons; all three are now handled, and the real SQL is checked in at `dashboard_studio/tests/fixtures/quality_performance_outcomes.sql` so the suite converts it rather than an approximation of it.

- **an unparsed WHERE condition** — a bug. The WHERE region ran past the `)` closing the wrapper it lived in, so `` `tabX`.`name` = 'literal' `` arrived as `` … 'literal' ) AS `__mb_source` ``. Worse than it looked: on one line it still *parsed*, with the wrapper's tail swallowed into the value.
- **two joins** — a conservative cap, not a constraint. N joins are N Insights operations.
- **the outer wrapper** — genuinely not a passthrough (it renames every column, carries the WHERE, and its FROM is a join), so `unwrap_derived_tables` was right to leave it. It is removable for a *different* reason: it neither filters nor aggregates, so it returns the same rows as the query inside it, and a rename is a bijection on columns. `lift_renaming_wrapper` maps the outer references back through the wrapper's own `X AS Y` list. That is the narrow, provable shape this file previously said should not be built against a reconstruction — it was built once the real SQL arrived.

One judgement call worth naming: Metabase writes `` `col` * 1 `` for a custom numeric field, and the lift treats that as the column. `x * 1` IS `x` for a number, but MySQL coerces `'abc' * 1` to 0, and the column's type is not known at that point — so it is allowed as an aggregate argument and **refused in a GROUP BY**, where grouping by a coerced zero would not be grouping by the column.

Still unsupported, unchanged: a wrapper that filters, an outer WHERE alongside an inner one, the same DocType joined twice, computed columns in the SELECT list, and a row limit other than Metabase's own cap.

**A third wrapper rule (2026-08-03): the same question compiled the other way up.** Metabase also emits an already-complete aggregating query wrapped in an outer projection that only re-selects its output columns by name. `lift_renaming_wrapper` correctly declines it — the inner GROUP BY stops the lift, and there is no outer aggregate to fold down — so it refused as a subquery. `drop_passthrough_wrapper` removes it on a proof of its own: the outer carries no clause at all, renames nothing, and its column set equals the set the inner produces, so it returns exactly the inner's rows and exactly its columns. Reported capture at `dashboard_studio/tests/fixtures/aggregated_then_reselected.sql`.

The rewrite is textual and does **not** require the inner query to convert first. That is deliberate: the removal is provable on its own, and a query whose inner half is unsupported then refuses naming *that*, rather than naming `__mb_source`.

It also unblocked a case the suite had written down as unsupported — `SELECT `w`.`n` FROM ( SELECT COUNT(*) AS `n` FROM `tabX` ) AS `w`` used to refuse. Refusing it was the conservative answer, not the correct one.

**Known and not fixed: nothing strips SQL comments.** A comment line inside the outer SELECT list stops the wrapper being read, and a comment mentioning a clause name is read as that clause. It refuses rather than converting wrongly, and Metabase's compiled SQL carries no comments, so the cost of leaving it is a puzzling refusal on hand-annotated SQL — not a chart with the wrong number in it. `TestACommentIsNotStripped` records it where it will be found again.
