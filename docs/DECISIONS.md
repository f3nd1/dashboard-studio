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

## Known unsupported — recorded, not scheduled

**Quality Performance Outcomes** (real UCC report) is no longer blocked. It refused for three reasons; all three are now handled, and the real SQL is checked in at `dashboard_studio/tests/fixtures/quality_performance_outcomes.sql` so the suite converts it rather than an approximation of it.

- **an unparsed WHERE condition** — a bug. The WHERE region ran past the `)` closing the wrapper it lived in, so `` `tabX`.`name` = 'literal' `` arrived as `` … 'literal' ) AS `__mb_source` ``. Worse than it looked: on one line it still *parsed*, with the wrapper's tail swallowed into the value.
- **two joins** — a conservative cap, not a constraint. N joins are N Insights operations.
- **the outer wrapper** — genuinely not a passthrough (it renames every column, carries the WHERE, and its FROM is a join), so `unwrap_derived_tables` was right to leave it. It is removable for a *different* reason: it neither filters nor aggregates, so it returns the same rows as the query inside it, and a rename is a bijection on columns. `lift_renaming_wrapper` maps the outer references back through the wrapper's own `X AS Y` list. That is the narrow, provable shape this file previously said should not be built against a reconstruction — it was built once the real SQL arrived.

One judgement call worth naming: Metabase writes `` `col` * 1 `` for a custom numeric field, and the lift treats that as the column. `x * 1` IS `x` for a number, but MySQL coerces `'abc' * 1` to 0, and the column's type is not known at that point — so it is allowed as an aggregate argument and **refused in a GROUP BY**, where grouping by a coerced zero would not be grouping by the column.

Still unsupported, unchanged: a wrapper that filters or aggregates, an outer WHERE alongside an inner one, the same DocType joined twice, computed columns in the SELECT list, and a row limit other than Metabase's own cap.
