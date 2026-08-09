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

## ADR-013 — A scale factor is a mutate, and it needed no new evidence

**Decision.** `rating_1 * 5 AS Q1` in a wrapper becomes a `mutate` `Q1 = rating_1 * 5` before the `summarize`, typed from the column it reads.

**Why it was buildable immediately**, where the CASE pattern reported alongside it is not: every fact it needs was already settled. Arithmetic in a mutate expression is what the *first* captured expression was (`(avg_of_idx + avg_of_docstatus) / 2`, ADR-011), and mutate-before-summarize was settled by ADR-012 from a stored operation order. So no new vocabulary and no new ordering — only the wrapper reader learning one more shape.

**It is not ADR-009's `* 1`.** `* 1` leaves every value alone and exists to force a type; `* 5` changes every value. One is a cast, the other a computation, and they are read by different code for that reason.

**Typed from the source column, and refused when that column is text.** The parser has no types, so it emits `data_type: None` meaning "the translator decides". The translator looks the column up and refuses if it is not numeric: `'abc' * 5` is 0 in MySQL, so scaling text would coerce every non-numeric row to zero silently — ADR-009's rule again, applied where it belongs. A numeric column gives `Decimal`, because a scale factor may divide and a Decimal groups and aggregates the same values.

**Exactly one column, with numeric literals.** `a * b` refuses by name. It is expressible in the dialect, but it has not been observed and typing it is a second question; the vocabulary widens to what is seen.

**The original flagship, report 1680, still refuses — and now says something new.** Its `* 5` wrapper lifts; what is left is the outer `CAST( AVG(a) + AVG(b) AS double ) / 2.0`, which ADR-011 refuses for an unchanged reason: `cast` converts a *column*, and that expression converts a result which is never one. Checked in as `fixtures/scale_factor_wrapper.sql` and asserted — the test requires the refusal to name CAST and NOT to say "subquery", so the progress is pinned rather than assumed.

**A test fixture had to move because of this.** `test_subquery_shapes.py` used `* 5` precisely because it kept a query unliftable. It lifts now, so those fixtures use `MONTH(...)` instead — a function outside the allowlist. Worth noting as a pattern: a fixture chosen to be *unsupported* has a shelf life, and when it expires the tests that depend on it fail loudly, which is the right direction.

## ADR-014 — Do not translate the composite-index survey reports; rebuild them in Insights

**Decision.** The survey composite-index reports — `10- - Communication Effectiveness Index--3001` and its family — are **not** translated. They refuse by name, and the recommendation for them is a manual rebuild in Insights rather than a conversion. No "Likert word → number" capability is extracted.

**This was assessed from the real capture**, not from the group summary, and the group summary was misleading: the refusal message reads like a two-branch categorical CASE, and the query is a 9-question weighted composite index.

**What it actually needs.** Counted from the file rather than estimated:

- a **conditional** in the expression language — unknown whether one exists, and unknown how spelled;
- `TRIM`, `LOWER`, `COALESCE`, `NULLIF` — four functions, none confirmed. Only `year` has ever been seen stored;
- `IS NULL` as a test inside an expression — unconfirmed;
- `LIKE` inside an expression — unconfirmed, and `LIKE` is already refused as a filter operator;
- `CAST(TRIM(x) AS signed)` — a CAST over an *expression*, which ADR-011 refuses for a reason nothing here changes;
- **OR in the WHERE** — refused; the inner WHERE ORs three survey titles;
- a **computed column in the WHERE** — `LOWER(CASE WHEN parent LIKE 'UCC-SVR-25%' THEN '2025' END) LIKE '%2025%'`, a filter on a per-row computed value.

**And one thing that is not a missing function at all.** The nine columns are a hand-rolled **pivot**: one row per survey response, each column non-NULL only for the row whose question text matches, then `AVG` per column so the NULLs fall out. Nothing in Insights' operation vocabulary pivots. Even granting every function above, this SQL has no counterpart to translate *into* — the same report in Insights is "group by question, average the score", which is a different query returning a different shape, from which the index is then composed. That is a rebuild, not a translation.

**Why the Likert mapping is not extracted, though it is the most tempting piece.**

- It is **domain content, not converter knowledge**. That `'agree'` means 4 is a fact about UCC's surveys. A converter carrying it has one institution's semantics compiled in.
- Recognising a 5-branch CASE and *asserting* it means Likert is precisely the guess this project refuses. A sixth branch, a "somewhat agree", a 1-7 scale, or a **reverse-coded** item — real and common in surveys — would either refuse (no gain) or map backwards, and a reverse-coded item mapped forwards is a silently inverted score. `SOPHIA_FAULT_PATTERN.md`: they do not fail, they disagree.
- It would not unblock this report. Seven other gaps remain.
- It is **ADR-009's problem one level up**: `response` is free text where a score belongs. If the survey stored a number, the entire inner wrapper collapses to `AVG(score)` grouped by question, which converts today. The fix is in the data model, exactly as it was for `actual_value`.

**Rebuilding these in Insights is arguably better than translating them**, and worth saying rather than treating manual work as the consolation prize: the composite index becomes a visible, clickable chain of operations instead of 400 lines of nested CASE that nobody can edit. That is the entire point of the project.

**The group is not one pattern, and that is now measurable.** `scripts/subquery_shapes.py` reports what each CASE-bearing report is built from — branch count, long string literals (hardcoded question wording), and null logic (COALESCE/NULLIF/IS NULL, which is what an "average of answered" does and a plain label does not). A composite index and a `CASE WHEN answer = 'yes' THEN 1 ELSE 0` come out as different lines. **Run that before deciding anything about the remaining reports**: the ~150 figure covers both, and the simple half may be worth a capability that this one never justified.

## ADR-015 — A date difference is a mutate, and a computed column may read more than one column

**Decision.** `DATEDIFF(a, b) AS Days` in a Metabase wrapper becomes a `mutate` emitted before the summarize, spelled `date_diff(a, b, 'day')`. Both columns it reads are carried by the join. Anything else that computes a duration refuses by name.

**The shape needed nothing new** — it is ADR-012's, a wrapper computing a per-row column that the outer query groups by or averages. That was proved by experiment before any of this was built: with the function's spelling stubbed in, a constructed `DATEDIFF(a, b) AS Days` wrapper already converted end to end, producing `source -> join -> mutate -> summarize`. What it needed was a spelling, and a spelling here is **three facts, not one**: a name, an argument order and a unit.

**All three came off the live site, from two stored expressions**, `bchov0s5ue` and `bke9fgllri`, both holding `date_diff(modified, creation, 'day')`. So: the name is `date_diff` and not `datediff`; there are exactly three arguments with the unit last as a quoted string; and the order is (later, earlier), proven rather than inferred — `modified` is always the later of the two and the values came back **positive**. MySQL's `DATEDIFF(a, b)` is `a - b`, so the arguments carry across in the order they were written.

**The argument order is the whole risk in this translation.** `date_diff(start, end, 'day')` is the same number with the opposite sign. "Days to complete: −14" is a report that runs, renders, and is wrong — `SOPHIA_FAULT_PATTERN.md` exactly. It has its own test, and reversing the arguments turns the suite red.

**`TIMESTAMPDIFF(DAY, a, b)` refuses.** It puts the unit first *and* subtracts the other way round, so reading its two columns as a `date_diff` would negate every value. It has appeared in no capture either, and the vocabulary widens only to what has been observed. A `DATEDIFF` with any other argument count refuses by count — three arguments is some other dialect's, and reading the first two would answer in days whatever unit was asked for.

**The columns have to be dates.** `date_diff` returns a count of days, which is true of dates and not of two strings that happen to look like them. Both arguments are checked, not just the first.

**Piece two — the plumbing — is the part that would have failed silently.** A computed entry carried a single `column`/`table` pair, and `_referenced_columns` added exactly that one, so the join brought `completed_on` across and dropped `raised_on`: the query converted cleanly, listed back correctly, and would have failed the moment somebody opened it. `columns`/`tables` are now lists on every computed entry — the single-column shapes carry a list of one — and the join carries all of them. `requires` moved onto the entry at the same time, so the translator's type check is per-computation ("number" for a scale factor, "date" for a difference, None for `year` and `cast`) rather than a special case for the one shape that had one.

**One refusal-quality fault came out with it.** A refused computation left its alias undefined, so the grouping and the aggregate that read it each added *"'Days' is not a column of Job Requisition or Requisition Stage"* — one fault told three times, two of them pointing at the join rather than at the computation. The alias is now registered even when the computation is refused; nothing is emitted from a refused query, so that costs nothing and the reason list says the one true thing. `scripts/bulk_dry_run.py` gained the two matching groups, placed **before** the join's `is not a column of` — which they would otherwise have matched, filing a computation problem under joins.

Both halves have their mutation proof: carrying only the first column, type-checking only the first column, accepting TIMESTAMPDIFF, reversing the arguments, accepting any arity, dropping the date check, reading a literal as a column, and restoring the cascade each turn the suite red.

## ADR-016 — Read Insights' own source instead of confirming one function per round

**Decision.** The vocabulary and the operation shapes come from two files in the installed Insights app, read directly:

- `insights/insights/doctype/insights_data_source_v3/ibis/functions.py` — every function the expression editor accepts, with signatures and bodies
- `frontend/src2/types/query.types.ts` — every operation shape

Both are public at the installed tag, `github.com/frappe/insights` at **v3.12.2**, so they can be read from here rather than requested from the site.

**Why this is a decision and not just a lookup.** Until now every question about Insights' vocabulary cost a round trip: build one calculated column in the UI, run the probe, read one fact back. That produced `year`, then `date_diff`, and would have produced `month` next — one function per round, each with the same ceremony. The rule behind it was sound (**the vocabulary widens only to what has been observed**) and it stays sound; what changed is that reading the source IS an observation, and a better one than a stored record, because it carries the signature and the implementation rather than one example of the output.

**Verify the file is the file.** Upstream at a tag is not automatically what is installed — a site can carry local patches. The check is cheap and was run: the `^def ` list from the fetched file was compared name-for-name against a `grep` of the installed copy. 85 names, same set, in the same order. Do that again before trusting either file at a new version.

**What it settled at once**, none of which needed a round trip:

- **`month`, `quarter`, `day` exist** and are `year`'s shape exactly — `def month(column: ir.DateValue): return column.month()`. MySQL returns the same numbers, so they carry across unchanged.
- **`DAYOFWEEK` must refuse, and that is the finding that pays for the whole exercise.** Insights has a function called `day_of_week`, so the translation looks obviously available — but it returns ibis's `day_of_week.index()`, which counts **0 = Monday**, while MySQL's DAYOFWEEK counts **1 = Sunday**. Matching them by name would have shifted every row with nothing failing. A stored-expression probe would never have shown this; only the body does.
- **`WEEK` must refuse too** — MySQL's takes a mode argument deciding which day starts a week, and `week_of_year` takes none.
- **`date_diff` corroborates ADR-015 rather than contradicting it.** It is `column.delta(other, unit=unit)` — first argument minus second — which is what the live evidence (`date_diff(modified, creation, 'day')` returning positive values) already said. Two independent sources agreeing is the strongest state this project has had on a spelling. It also casts non-date arguments itself, so our Date/Datetime check is stricter than Insights requires, which is the safe direction and stays.
- **There is no cast function.** 85 functions and not one casts, so `CAST(<expression> AS …)` has nothing to translate into — see ADR-017.
- **`OrderBy` and `Limit` are real operations** — see ADR-018.
- **Conditionals exist**: `case(condition, value, *args)`, `cases(*branches, else_=None)`, `if_else`, `one_if`. That retires the wall ADR-014 ran into. It does **not** retire ADR-014's decision, which rested on a hand-rolled pivot and seven other gaps, not on the conditional alone.

**What it does not settle.** `ExpressionMeasure`, `FilterExpression`, `CustomOperation`, `SQL` and `Code` are all real operations that take free text. Being expressible is not being translatable: this converter's whole safety argument is that it emits shapes whose meaning it can state. `SQL = { type: 'sql'; raw_sql: string }` in particular would let any refusal be "solved" by passing the SQL through untranslated, which is the opposite of the product — a report nobody can click. Do not reach for it.

## ADR-017 — Drop a value-preserving CAST around an expression; refuse the rest

**Decision.** `CAST(<expression> AS double | decimal | float | real)` is replaced by `(<expression>)`. `CAST(… AS signed | integer | int | unsigned | char)` still refuses by name.

**Why dropping is the only option, and why it is legitimate.** There is no cast function in the expression language (ADR-016) and the `cast` OPERATION takes a named column — `CastArgs = { column: Column; data_type: ColumnDataType }` — so an expression's result has nowhere to put one. Removing it is therefore the only translation available, and it needs its own proof rather than a shrug. To a **float** type it has one: what is inside is arithmetic over aggregates, which is numeric by the time it converts, and widening a number to a float leaves every value alone. That is exactly what Metabase writes `CAST(… AS double)` for — forcing float division. To an **integer** type there is no such proof: `CAST(5/2 AS signed)` is 2, a truncation, and dropping it would round every value silently. `char` stringifies.

**The brackets are the part that could have gone wrong.** Metabase does not always write the cast outermost — report 1680 has `CAST( AVG(a) + AVG(b) AS double ) / 2.0`, wrapping one operand of a division. Replacing that with `AVG(a) + AVG(b) / 2.0` is a valid expression, converts without complaint, and is a different number. The rewrite keeps the brackets the CAST already had, so it is an identity in the arithmetic as well as in the type. `test_the_BRACKETS_the_cast_had_are_kept` pins it and dropping them turns the suite red.

**Report 1680, the original flagship, now converts end to end** — `source -> join -> join -> filter -> mutate -> mutate -> summarize -> mutate`, ending in `(avg_of_Q1 + avg_of_Q5) / 2.0`. Every earlier refusal on it was correct at the time; this was the last one.

## ADR-018 — Translate ORDER BY and LIMIT, together

**Decision.** An ORDER BY becomes one `order_by` operation per item, after the summarize; a row limit becomes a `limit` operation, after those. Metabase's own `LIMIT 1048575` export cap is still dropped rather than translated.

**Both were held back for the same reason and are released for the same reason.** `OrderBy = { type: 'order_by' } & { column: Column; direction: 'asc' | 'desc' }` and `Limit = { type: 'limit'; limit: number }` are in `query.types.ts`. Before that file was read, the ORDER BY was discarded in silence — recorded one day earlier as a deliberate trade — and the LIMIT refused by name.

**They had to ship together.** The argument for dropping an ORDER BY safely was that a real LIMIT refused, so ordering could never decide *which* rows came back, only their order. Translating LIMIT alone would have destroyed that argument while leaving the ordering on the floor: a converted "top 10" would have been ten arbitrary rows. Shipping the ordering alone would have been harmless but half a feature. This is the shape of trade that only looks safe one clause at a time.

**An ordering is checked against what the query PRODUCES.** After a summarize the result is exactly its dimensions and measures — the source columns are gone — so ordering by one of those is a query that fails the moment it is opened, the same fault as a join carrying a column it dropped. Where there is no summarize the check returns "unknowable" and does not run, because a guess there is worse than no guess and the schema check upstream has already vouched for the names.

Refused: an ORDER BY of anything that is not a plain column (an expression is a different operation, and guessing at one silently reorders the rows a chart reads), and two different LIMITs in one statement (which one bounds the result depends on where each sits, and that is not read here).

## ADR-019 — An all-OR WHERE becomes a filter group; AND and OR mixed refuses

**Decision.** A WHERE whose conditions are all OR-ed becomes one `filter_group` with `logical_operator: "Or"`. All-AND stays as it was — one `filter` operation per condition. A clause containing both refuses by name.

**The old refusal was based on a belief, not a reading.** The comment said *"OR cannot map to the engine's AND-only conditions"*. `query.types.ts` at v3.12.2 has `FilterGroup = { type: 'filter_group' } & { logical_operator: LogicalOperator; filters: FilterArgs[] }` and `LogicalOperator = 'And' | 'Or'`. It has had one all along; nobody had looked.

**Two details of the shape are asserted in full**, because an unrecognised key is dropped silently and a wrong one fails identically while looking fixed:

- the members are bare `FilterArgs` and carry **no `type` key**. `Filter = { type: 'filter' } & FilterArgs` has one because it is an Operation; a group member is not.
- `logical_operator` is **capitalised** — `'Or'`, not `'or'`. It is the odd one out among these shapes, where every other string is lowercase.

**Why mixing refuses, and why that is not conservatism.** `filters` is a FLAT list of `FilterArgs`, and `FilterArgs` is a rule or an expression — never another group. So the type can express "all of these" and "any of these" and nothing else. `a AND b OR c` means `(a AND b) OR c` in SQL; flattening it into one group under either operator produces a clause that reads plausibly and selects different rows, which is the exact fault this converter exists to avoid. Nested groups are the thing that would make this translatable, and they are not in the type.

**AND-ed conditions deliberately do NOT become a group of one operator.** Insights' own editor produces a row per AND-ed condition, and each row is something a person can read and click — which is the entire point of converting to operations rather than pasting SQL. A group around them would be a wrapper adding nothing.

Brackets are stripped around the whole clause and around each condition. That is only safe because a mixed clause has already refused: where one operator governs, grouping brackets change nothing.

## ADR-020 — A CASE that maps values to labels becomes a `case(...)` mutate; ADR-014 stands

**Decision.** A searched `CASE WHEN <column-or-date-part> <op> <literal> THEN <literal> … [ELSE <literal>] END` becomes a `mutate` whose expression is `case(cond, value, cond, value, …)`. Every other CASE refuses by name — including the composite-index survey reports of ADR-014, which are **not** reopened.

**The shape came from source, not from a guess.** `case(condition, value, *args)` in `functions.py` at v3.12.2 takes its pairs **flat**, with an optional trailing else, and its body is `ibis.cases(*branches)` — with no `else_` when the argument count is even. A SQL CASE with no ELSE returns NULL and so does that, so the no-ELSE capture translates exactly rather than needing an invented default. (`cases` is the sibling that takes tuples; writing one shape into the other's name would read a condition as a value.) The comparison spelling came from the same docstrings: `status == 'Active'`, Python's `==`, not SQL's single `=`.

**Accepted is far narrower than `case` can express**, because this becomes text a query engine evaluates:

- a condition is **one** column, or one date part of one column, compared against **one** literal, using `=` `!=` `<>` `<` `<=` `>` `>=`;
- a result is a plain number or a quoted label — not a column, not an expression;
- all branches must return the same kind, since a column holds one type;
- the date-part allowlist is the same `_DATE_PARTS` table the standalone computations use, so `DAYOFWEEK`'s 0-Monday-against-1-Sunday problem cannot be walked around by putting it inside a CASE.

Refused by name: a compound condition (`AND`/`OR`/`NOT`), `IS NULL`, `LIKE`, `IN`, `BETWEEN`, the simple `CASE x WHEN 1` form (it compares x against each value rather than evaluating each condition — reading one as the other changes what every branch tests), and a result that is not a literal.

**The literal rule is the injection boundary and is worth stating as one.** A quoted label may not contain a quote, a double quote, a backslash or a backtick. The expression is a string that Insights evaluates; a literal that cannot terminate itself early cannot become code. Brackets and commas inside a label are harmless for the same reason and are allowed, since real labels have them.

**How a translated CASE stops tripping the global CASE refusal.** It does not need special-casing: `_UNSUPPORTED_MARKERS` scans the statement *after* the wrapper rules have run, and lifting a wrapper removes its item text from the statement. A CASE anywhere the readers do not look — in a WHERE, inside an aggregate — is still in the statement at that point and still refuses. `test_a_CASE_somewhere_the_reader_never_looks_still_refuses` pins that.

**Why this is not a reversal of ADR-014.** That decision was never "there is no conditional". It rested on a hand-rolled **pivot**, which nothing in Insights' operation vocabulary expresses, plus `TRIM`/`LOWER`/`COALESCE`/`NULLIF`, `IS NULL` inside an expression, `LIKE` inside an expression, a CAST over an expression, an OR'd WHERE and a computed column in the WHERE. The conditional was one item on a list of eight. A composite-index report still refuses here — on `LOWER(TRIM(response))`, which is not a column or a date part — and the recommendation for those is still a rebuild.

**The distinction the classifier already drew turned out to be the right one.** `scripts/subquery_shapes.py` reports CASE-bearing reports by branch count, long string literals and null logic; the month-label report and the composite index share a branch count and differ on the other two. This was translated on the strength of that separation, and the group that was declined is the one that still refuses.

## ADR-021 — A plain-English question box, whose safety argument is the read-back

**Decision.** A question box proposes an Insights setup and creates nothing. The model emits SQL, which goes through the existing converter unchanged; the one-line summary the user reads is composed by our code from the emitted operations, never by the model.

**The honest finding first, because it decides the rest.** The existing validation is **referential, not semantic**. It checks that a column exists on the real table and is the right kind of thing. It cannot check that the model picked the column somebody meant. `sales_income`, `net_income` and `commission_amount` all exist and are all numeric; `posting_date`, `transaction_date` and `creation` are all Date. A confidently wrong proposal passes every check this project has, and returns a different number without failing — `SOPHIA_FAULT_PATTERN.md` exactly. Pasted SQL carried a human's semantic choices out of Metabase. A proposal carries a model's. Named gaps, all real: which column, which date, join fan-out, an absent `docstatus` filter, and sum-versus-avg.

**So the gate is the read-back, and it is load-bearing.** `describeProposal` in `studio_core.js` composes one sentence from the operations that will run — "sum of sales_income for each agent_name and Year, from tabSales Invoice, where docstatus = 1, highest sum_of_sales_income first". Change which column is aggregated and the sentence changes with it; a JS assertion holds that property, because it is the whole reason reading the line is a check at all. **If the model wrote that sentence it would describe its intention while the operations did something else, and the review would verify nothing.** The endpoint therefore returns no free text from the model, and an AST test asserts the reply's key set, so adding one fails rather than being noticed later.

**Three structural guarantees, none of them by convention:**

- `integrations/llm/question.py` **does not import frappe**, so there is no path from it to a row. Sample values are not withheld by care — they are unreachable. Tested by reading its import list from the syntax tree.
- `api/propose.py` has **no write path**: no `get_doc`, `insert`, `save` or `convert_sql`, asserted by walking its call graph. Creation stays in `convert_sql`, behind a button pressed after reading the proposal.
- Exactly **one** `requests.post` in the app, its URL checked at the call site — the shape `metabase_export_sql.py` already uses.

**The validation strip states both halves.** Green reports what was verified by name; the line under it says *"Not checked: whether these are the columns you meant."* A strip that reports only what it checked implies an assurance nobody can give, and would invite the one thing this cannot survive — somebody not reading the proposal.

**Join fan-out is named, and only where it is provable.** Joining a parent to a child table gives the parent one output row per child, so a SUM after it counts the parent's value once per child: too big, and entirely ordinary-looking. `rows_multiplied_by` reports joins to DocTypes Frappe marks `istable`, and only under a summarize — warning about a plain join would train people past the warning. **It does not detect an ordinary one-to-many between two normal DocTypes**, which fans out identically and is not marked in metadata. That limit is in the docstring rather than approximated, because a warning that looks complete is worse than none.

**Two pieces of the requested design were not built, rather than approximated.** There is no chart-type picker: this app creates no charts — that code is in `archive/` — so the control would have done nothing. And the workbook picker is not repeated inside the proposal card; the existing one below already feeds `convert_sql`, and two controls meaning one thing is worse than one.

**Reused as-is**: the whole converter and every refusal in it, `_table_columns`, `describeOperation`, `refusalMessage`, the workbook picker, `convert_sql`, `DS_WRITE_ROLES`. What is new is one pure module, one endpoint, one summary function and a panel.

**Not verified live.** The HTTP call is injected and unit-tested against fakes; there is no network route or Bench here. Nobody has yet run a real question against a real site — that is the user's step, and the first thing to watch is whether the model's SQL lands inside the supported subset often enough to be worth the round trip.

## ADR-022 — Lift an inline GROUP BY expression into a named column

**Decision.** `GROUP BY MONTH(`t`.`d`)` in a FLAT query becomes a `mutate` named `month_of_d`, with the SELECT list, the GROUP BY and the ORDER BY all rewritten to that name. Nothing is added to the function allowlist.

**Why it is a different shape from the one already solved.** Wrapped, Metabase names the expression inside a subquery and the outer query groups by that name — ADR-012, `lift_renaming_wrapper`. Flat, the same function appears inline in three clauses at once, and the converter produced three refusals for one cause: an unreadable ORDER BY, a GROUP BY that is not a plain column, and a SELECT item with no aggregate in it.

**One expression, one mutate.** Only the GROUP BY is scanned; each expression found there is then rewritten wherever it appears in the SELECT list and the ORDER BY. Two mutates would be two columns holding the same number with the summarize grouping by one of them. A repeat within one GROUP BY collapses too, and that has its own test — the first version of it passed for a structural reason rather than because the guard worked, which the mutation run caught.

**A WHERE is deliberately not rewritten.** The mutate is emitted after the filters, so a filter naming it would reference a column that does not exist yet. Left alone, such a WHERE refuses with the message it always had.

**The generated name is not Metabase's.** It writes `MONTH(`d`) AS `d`` — naming the result after the column it reads. A mutate creating `d` from `d` either reads itself or shadows the source, so the name is `<function>_of_<column>`, which cannot collide with the column it reads. `sql_ops` refuses when it collides with any other real column. The output column is therefore named differently from the original report; renaming output columns is already what the wrapper lift does.

**Position, not vocabulary.** Only calls `_computed_column` already accepts are lifted. `DAYOFWEEK` (0 = Monday against MySQL's 1 = Sunday), `WEEK` and anything else refuse by name, unchanged, and a test asserts it.

**The reported query still refuses, on something else.** `AVG(CAST(col AS double))` alongside a second aggregate reads as an expression-over-aggregates rather than a plain aggregate, so the two collide as "two questions in one query". That reproduces with none of this code and is ADR-009's problem in a different spelling: the column is text and the CAST is doing real work, so dropping it under ADR-017 would turn a working report into a refusal rather than fixing it. Not built — it needs the cast-operation path, which is its own decision.

## ADR-023 — The user chooses the DocTypes; `propose_from_question` cannot

**Decision.** `doctypes` is a **required** argument of `propose_from_question`, with no default. A separate `propose_tables` returns DocType **names only**, and the page shows them as an editable confirm step **before** any query exists. Manual mode skips the picker entirely. A model that names a table outside the confirmed set is refused by name.

**What went wrong.** A question about recruitment agents converted cleanly against ERPNext's sales-commission tables — `tabSales Team` and `tabSales Invoice`. Every column real, every type right, every join legal. UCC's recruitment agents live in `tabAgent`, which the query never touched. Nothing in the referential validation could object, because nothing was referentially wrong.

**Why the table is the one decision that cannot be verified here.** The rest of the pipeline checks a column exists and is the right type. There is no check for "this is the table you meant" — it is not a fact about the schema, it is a fact about the organisation. So it is the one choice a person makes.

**Names only, and before the query.** A rationale would describe the model's *intention*, and the intention is exactly what needs checking, so the picker shows bare names. It comes before a query exists because a table confirmed underneath a finished-looking result gets rubber-stamped — the same reason ADR-021 composes its summary from the operations rather than the model's prose.

**The server half is the one that bites.** Columns used to be re-typed from whatever tables the emitted SQL mentioned, so a model widening past the confirmed set was silently accepted. It now refuses, naming the table it was not given.

## ADR-024 — `YEAR()` in a GROUP BY is a dimension GRANULARITY; a date part in a WHERE is a mutate before the filter

**Decision.** Two capabilities that had to ship together, because both turn on *where* a lifted operation is emitted.

1. Every `mutate` is now emitted **before** the filters. ADR-009's `cast` stays where it was, immediately before the summarize.
2. `WHERE YEAR(`d`) = 2025` lifts into a mutate the filter then names — ADR-022's lift, extended to the WHERE it previously left alone.
3. `GROUP BY YEAR(`d`)` emits **no mutate at all**: the dimension is the date column carrying `granularity: "year"`.

**What made (1) safe, read rather than recalled.** `ibis_utils.py` at v3.12.2 applies operations in list order — `perform_operation` in a loop, its errors naming "the operation at position N" — and `apply_mutate` returns `query.mutate(...)` while `apply_filter` returns `query.filter(...)` on the query *so far*. So a filter may name a mutated column, provided the mutate comes first. ADR-022's note that "a WHERE is deliberately not rewritten" was correct about the code as it stood and is now superseded by moving the mutate.

**Why the cast did not move with them.** ADR-009 puts it immediately before the summarize because that is where `* 1` sat in the SQL — scoped to the aggregate, not to the WHERE. Moving it up would retype the column the filters were already compared against. So `computed` entries now split by kind into two positions rather than one.

**The decisive fact behind (3), and it is the reason MONTH does not follow.** `Dimension` in `query.types.ts` carries `granularity?: GranularityType`, and `translate_dimension` applies it as `column.truncate(unit)` cast back to the column's own date type. `truncate("Y")` partitions rows by calendar year exactly as `YEAR()` does — same rows, same count, only the label differs, so the two are equivalent. `truncate("M")` is month **within** year, while `MONTH()` pools every January across every year: twelve rows against forty-odd. Those are different questions, so `_GRANULARITY_OF` contains **only** `YEAR`, and MONTH, QUARTER and DAY keep the numeric mutate.

**The named limitation, said out loud rather than worked around.** A numeric month-of-year is not a date, and Insights' chart X axis only offers date-compatible columns — so a MONTH grouping is correct and cannot be charted. `describeOperation` says so on the operation itself, because otherwise the unchartable result reads as a converter fault. Regrouping to `truncate("M")` to satisfy the axis would answer a question nobody asked, which is the trade this project always refuses.

**Two refusals guard the granularity route.** A granularity on a column that is not Date/Datetime refuses — `truncate` needs a date, and grouping the raw column instead would convert cleanly and answer something else. And a granularity the parser lifted that never reached a dimension refuses too: the parser has by then rewritten `YEAR(`d`)` to a bare `` `d` ``, so a dropped granularity is a grouping by every distinct **day**.

**The bug the tests caught, which is the whole reason both halves needed the same round.** `WHERE YEAR(d) = 2025 GROUP BY YEAR(d)` needs the granularity *and* the mutate from one call. De-duplicating the two routes against a shared record dropped the mutate, and the WHERE rewrite then left a filter comparing the raw date column against `2025` — supported, runnable, and returning nothing. Each route now de-duplicates against its own record, and the WHERE region is rewritten with the mutate name even where the GROUP BY took the granularity: a granularity is a property of a dimension, and a filter has none.

## ADR-025 — The chart's series come from a sidecar the export writes, not from a call to Metabase

**Decision.** `metabase_export_sql.py` writes `<report>--<id>.json` beside every `<report>--<id>.sql`, carrying the card's `series_settings`, its `display` and its id. Convert reads that sidecar when given one and creates an `Insights Chart v3` alongside the query, each series carrying the type and label Metabase had. **Studio still makes no network call in the convert path**, and a test asserts it.

**The live-call approval was granted and not spent.** Felix approved dashboard_studio calling Metabase during conversion, as a scoped exception. It turned out to be unnecessary: Convert has no card id to fetch by — `convert_sql(sql, title, workbook)` takes pasted text — so a live call would have needed a card id supplied anyway, and once one is being supplied the sidecar is already beside the file. Writing it in the SAME export pass is strictly better than fetching later, because the pair is then guaranteed to correspond rather than matched. `TestStudioMakesNoNetworkCall` holds the outcome, since "we did not need it" erodes unless something says so.

**Matching is by filename and nothing else.** The picker takes a `.sql` and a `.json` in one selection and pairs them on the basename; a sidecar whose name does not match is not read. Matching on the query TEXT was never an option: the export is full of near-identical variants of one report — `- delete`, `- retain`, `- Duplicate` — so a text match would apply another report's chart settings in silence.

**Metabase keys a series by its result column name, and we match on the AGGREGATION.** The real QIPI card (id 2424) carries `avg` and `count`; this converter names the same measures `avg_of_<column>` and `count`. Both sides state the aggregation, so that is the join. It names only the *function*, so two measures sharing one — `AVG(a)` and `AVG(b)`, which are `avg` and `avg_2` there — cannot be told apart, and that abandons the chart for the whole card rather than picking one.

**This DEGRADES where the rest of the converter refuses, and that is a considered difference rather than a softening.** A wrong chart is visible the moment somebody looks at it — bars where a line belongs. A wrong query returns a number nobody can tell is wrong. So the cost of being wrong differs in kind, and the fallback is Part 3's "check this manually" flag with the query still written. What remains forbidden is inventing a bar/line split Metabase did not state.

**Every series goes on the LEFT axis.** Metabase stores `axis` only when overridden; its default is `null`, and the split happens at render time via `graph.y_axis.auto_split`. The QIPI card confirmed it from real data — two visible axes, no `axis` key on either series. There is nothing to read, so a Right assignment would be this converter's invention.

**Only `bar` and `line` translate.** Metabase's vocabulary is `line | area | bar`; Insights' `Series.type` is `'line' | 'bar'`. An `area` series is a line plus a `show_area` fill, which is a different field, so `area` falls back rather than being bent into the nearest match.

**The combo-card risk was measured, not assumed.** Of 2003 cards, 4 are `display: "combo"`, and all 4 have one metric and no `series_settings` — so the feared "2+ series, type computed from array position, nothing stored" shape does not exist in real UCC data. `combo` is not in the display map, so if one ever appears it falls back rather than guessing.

## Known unsupported — recorded, not scheduled

**Quality Performance Outcomes** (real UCC report) is no longer blocked. It refused for three reasons; all three are now handled, and the real SQL is checked in at `dashboard_studio/tests/fixtures/quality_performance_outcomes.sql` so the suite converts it rather than an approximation of it.

- **an unparsed WHERE condition** — a bug. The WHERE region ran past the `)` closing the wrapper it lived in, so `` `tabX`.`name` = 'literal' `` arrived as `` … 'literal' ) AS `__mb_source` ``. Worse than it looked: on one line it still *parsed*, with the wrapper's tail swallowed into the value.
- **two joins** — a conservative cap, not a constraint. N joins are N Insights operations.
- **the outer wrapper** — genuinely not a passthrough (it renames every column, carries the WHERE, and its FROM is a join), so `unwrap_derived_tables` was right to leave it. It is removable for a *different* reason: it neither filters nor aggregates, so it returns the same rows as the query inside it, and a rename is a bijection on columns. `lift_renaming_wrapper` maps the outer references back through the wrapper's own `X AS Y` list. That is the narrow, provable shape this file previously said should not be built against a reconstruction — it was built once the real SQL arrived.

One judgement call worth naming: Metabase writes `` `col` * 1 `` for a custom numeric field, and the lift treats that as the column. `x * 1` IS `x` for a number, but MySQL coerces `'abc' * 1` to 0, and the column's type is not known at that point — so it is allowed as an aggregate argument and **refused in a GROUP BY**, where grouping by a coerced zero would not be grouping by the column.

**DATEDIFF — assessed 2026-08-06 as TWO pieces rather than one; both are now built, see ADR-015.**

The shape is the ADR-012 one: a wrapper computing a per-row column, averaged or grouped outside. Proved by experiment rather than assumed — with the function's spelling stubbed into `_computed_column`, a constructed `DATEDIFF(a, b) AS Days` wrapper converts end to end through the existing machinery, producing `source -> join -> mutate -> summarize`. So no new operation, no new ordering, no pivot.

**Piece one: the spelling, and it is three unknowns rather than one.** `year(x)` was a single fact. A date difference has a *name*, an *argument order* and a *unit*, and getting the order wrong negates every value silently — `DATEDIFF(end, start)` in MySQL is `end - start`, and a function spelled `date_diff(start, end, 'day')` is the same number with the opposite sign. "Days to complete" coming out as −14 is the failure mode this project exists to refuse.

**Piece two: a computed column may currently name only ONE source column, and DATEDIFF names two.** The experiment caught this: the join carried `['completed_on', 'parent']` and dropped `raised_on`, because `_computed_column` entries carry a single `column` key and `_referenced_columns` adds exactly that one. The query converted cleanly with a mutate referencing a column the join never brought across. That plumbing had to widen before any two-argument function could be accepted, and it is independent of the spelling — it was not built speculatively, because until DATEDIFF nothing produced a two-column entry and an unused generalisation is a check nobody can test.

**What settled piece one, and it was exactly one thing to build.** In the Insights UI, on any table, add a calculated column computing the difference in days between `modified` and `creation` — every Frappe table has both, and `modified` is always the later one, so a correct result is **≥ 0** and the sign reveals the argument order. Save it, then run `scripts/insights_operations_probe.py`, which prints every stored expression whole. That one column yields the name, the argument order and the unit together.

Still unsupported, unchanged: a wrapper that filters, an outer WHERE alongside an inner one, the same DocType joined twice, computed columns in the SELECT list, and a row limit other than Metabase's own cap.

**ORDER BY is dropped — recorded 2026-08-06, and SUPERSEDED the next day by ADR-018, which translates it.** The reasoning below was sound on the evidence it had and is kept because the shape of the mistake is worth recognising: the trade looked safe only because the clause next door refused. What actually settled it was reading Insights' own `query.types.ts`, which has had an `order_by` operation all along.

**The original note, as written:** It is used only as a clause boundary and never translated, so three of the four checked-in captures carry one that goes nowhere. It survived unrecorded and untested, which is exactly how the dropped LIMIT and the dropped computed column survived.

What makes it a different case from those two is the row limit next door. **An ORDER BY changes which rows come back only in company with a LIMIT, and a real LIMIT refuses** — so a surviving ORDER BY leaves both the rows and every value alone and only reorders them. Refusing it would block essentially every compiled Metabase report for a difference no number can show. One honest edge: Metabase's own `LIMIT 1048575` cap is allowed through, so a report returning more than 1,048,575 rows would have its ORDER BY decide which of them survive. Nothing here is near that.

It costs something real anyway — `ORDER BY \`Month No\` ASC` is what makes a chart run Jan to Dec — so this is a trade, not a free pass. `TestOrderByIsDroppedOnPurpose` pins it so that widening it is a change somebody makes on purpose. **What would settle it: whether Insights stores an order operation of its own.** `scripts/insights_operations_probe.py` reads the stored operation lists and would show one if it exists.

**A third wrapper rule (2026-08-03): the same question compiled the other way up.** Metabase also emits an already-complete aggregating query wrapped in an outer projection that only re-selects its output columns by name. `lift_renaming_wrapper` correctly declines it — the inner GROUP BY stops the lift, and there is no outer aggregate to fold down — so it refused as a subquery. `drop_passthrough_wrapper` removes it on a proof of its own: the outer carries no clause at all, renames nothing, and its column set equals the set the inner produces, so it returns exactly the inner's rows and exactly its columns. Reported capture at `dashboard_studio/tests/fixtures/aggregated_then_reselected.sql`.

The rewrite is textual and does **not** require the inner query to convert first. That is deliberate: the removal is provable on its own, and a query whose inner half is unsupported then refuses naming *that*, rather than naming `__mb_source`.

It also unblocked a case the suite had written down as unsupported — `SELECT `w`.`n` FROM ( SELECT COUNT(*) AS `n` FROM `tabX` ) AS `w`` used to refuse. Refusing it was the conservative answer, not the correct one.

**Known and not fixed: nothing strips SQL comments.** A comment line inside the outer SELECT list stops the wrapper being read, and a comment mentioning a clause name is read as that clause. It refuses rather than converting wrongly, and Metabase's compiled SQL carries no comments, so the cost of leaving it is a puzzling refusal on hand-annotated SQL — not a chart with the wrong number in it. `TestACommentIsNotStripped` records it where it will be found again.
