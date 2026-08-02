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

## ADR-007 — Translate MBQL, behind a human verification gate (supersedes ADR-006)

Decision: Dashboard Studio DOES convert a GUI-built Metabase card into Insights v3 operations — and every converted query carries an `[UNVERIFIED]` marker in its title until a person has compared its number against the Metabase card it came from.

Reason: clickable Operations are maintainable in a way a pasted block of SQL is not, and re-pasting SQL for every report is a recurring cost. ADR-006's objection is not withdrawn — a translation that disagrees with Metabase still returns a different number with no error — so it is answered rather than dismissed. The gate is the answer, and it is load-bearing rather than advisory: a mismatch refuses and leaves the marker, there is no "verify anyway", and the marker lives in the title so it travels into Insights where somebody who never saw Studio still sees it.

What made the second attempt viable where the first was not: both formats were read from source at the installed versions (Metabase `lib/schema.cljc`, `schema/join.cljc`, `schema/ref.cljc`; Insights v3.12.2 `query.types.ts`) rather than assumed on either side.

Scope is a rule table, not a compiler. Compound aggregations, custom columns, limits, sorts, explicit column selections, multi-stage queries, date buckets and questions built on other questions all refuse by name and hand back no operations — a partial translation is a query that answers a different question.
