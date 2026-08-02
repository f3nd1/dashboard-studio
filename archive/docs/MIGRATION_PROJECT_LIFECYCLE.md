# Migration Project Lifecycle — design plan

Status: **proposal, not built.** This decides how a DS Migration Project is created and how
mappings get saved to it. No code, schema, or Mapping-view behaviour changes as part of this plan.

Scope note: this covers *how a mapping gets created and saved*. It does **not** design the
`Validating` / `Ready to Publish` stages' comparison logic — that is the DS Validation Comparison
feature, deferred separately. Those states appear below only as destinations, never as mechanics.

## The two schema facts this plan is built on

Both were read from the existing DocTypes, and together they answer most of the design:

1. **DS Data Mapping does not link to DS Migration Project.** It links to `data_source` only.
   Mappings are therefore scoped to a *data source*, not to one migration effort.
2. **DS Canvas Node is already a child table of DS Migration Project** (`canvas_nodes`).
   Node positions are therefore already per-project.

That asymmetry looks accidental but is defensible, and this plan keeps it — see §2 and §3.

## 1. Lifecycle

**Creation: use the native Frappe form. Do not build a creation UI.**
DS Migration Project is an ordinary DocType, so Frappe already gives us list/create/edit for free.
A Data Mapper creates the project, sets `project_name` and `data_source`, and saves. That is the
whole creation story; anything more is scaffolding nobody asked for.

**States and what moves between them:**

| State | Means | Transition into it |
|---|---|---|
| `Not Started` | Project exists, `data_source` chosen, nothing mapped yet | Default on insert |
| `Mapping` | Mappings are being drawn and confirmed | **Automatic** on the first successful mapping save |
| `Validating` | Mapper says the mapping set is complete | **Manual** (user action) |
| `Ready to Publish` | Validation passed | Out of scope — DS Validation Comparison decides |
| `Published` | Migrated dashboard is live | Out of scope |

Only one transition is automatic, and deliberately so: "a mapping was saved, so mapping has
started" is an unambiguous fact the system can observe. "Am I finished mapping?" is a human
judgement the system cannot infer, so `Mapping → Validating` is a button, not a heuristic.

**Locking — keep it minimal:**

- Before `Validating`: nothing locked. Mapping is messy work; let it be messy.
- From `Validating` onward: **`data_source` becomes read-only.** Changing it would silently
  invalidate every mapping the project depends on (they are resolved through it — see §2).
- Mappings themselves are *not* locked by project state, because they are shared across projects
  (§2) and one project's stage should not freeze another project's work.

No approval workflow, no docstatus/submit, no per-field permissions. If governance is wanted later,
that is a separate decision — Frappe's native Workflow doctype would be the tool, not custom code.

## 2. Where mappings live — recommendation: change nothing

When someone draws a connection and saves, which project owns it? Per fact #1, **none** — the
mapping belongs to the `data_source`. A project's mapping set is *derived*:

```
project's mappings = DS Data Mapping where data_source == project.data_source
```

**Options considered:**

- **(a) Add a `migration_project` Link to DS Data Mapping** — mappings become per-project.
- **(b) Keep as-is; scope mappings by data source, derive the project's set.** ← recommended
- (c) Both fields, project link optional. Rejected: two sources of truth, no clear winner at read time.

**Why (b).** "Metabase table `tabStudent Applicant` maps to DocType `Student Applicant`" is a fact
about the source system, not about one migration effort. Migrating the Admissions dashboard and
later the Employee Satisfaction dashboard will touch the same tables; re-confirming identical
mappings per project is duplicated work and invites two projects to disagree about the same table.
Option (b) also needs **no schema change** — the cheapest correct answer.

**The tradeoff, stated plainly:** mapping status is shared, so if project A flips a mapping to
`Rejected`, project B sees it too. That is mostly the point (one shared truth about the source),
but it does mean a mapping's status is not "project A's opinion". If per-project opinions are ever
genuinely needed, *that* is the moment to add the link — not now, on speculation.

**Does the Mapping view need a project selector?** No new selector UI. Entry point:
a button on the DS Migration Project form ("Open Mapping View") that routes to the Studio page
carrying the project name. The project supplies both things the view needs: its `data_source`
(scopes which mappings to load) and its own identity (scopes canvas layout).

*Small implementation detail to settle at build time:* the Studio page's route already consumes one
segment as a DS Dashboard name, so the project needs disambiguating — a `?project=<name>` query
param is the least invasive option and avoids reinterpreting the existing route.

## 3. Canvas node persistence — the current shape is correct

The question raised was whether the same source table appearing in multiple projects at different
positions would conflict. **It does not.** Because `canvas_nodes` is a child table, each
DS Migration Project holds its own rows; two projects can both contain a node `src:tabStudent
Applicant` at completely different coordinates with no interference. Child rows are owned by their
parent by definition.

So the asymmetry from §2 is coherent and worth keeping:

- **Where you dragged the box** = a per-project view preference → child table of the project ✅
- **What maps to what** = a shared fact about the source → standalone, keyed by data source ✅

One consequence to accept: deleting a project discards its layout (correct — it is just a view),
while its mappings survive (also correct — they were never the project's to own).

## 4. Minimal API surface — two endpoints

The Mapping view has exactly one save action, which already emits both payloads together. The API
should match that action rather than pre-splitting it:

**`save_migration_mapping_set(project, mappings, canvas_nodes)`** — write. One call, because the UI
does one thing. Upserts DS Data Mapping rows for the project's `data_source`, and replaces the
project's `canvas_nodes` child rows wholesale (the client always sends the full node set, and
rebuilding child rows is the pattern `save_chart` already uses).

**`get_migration_project(project)`** — read. Returns the project, its `data_source`, its existing
mappings, and its saved node positions, so work can be resumed. Not speculative: without it the
view cannot reopen previous work.

That is all. Explicitly **not** proposed: a `create_migration_project` endpoint (the native form
does it), delete/archive endpoints, per-mapping CRUD, or bulk import.

Both follow existing conventions: write gated to `Dashboard Studio Editor` / System Manager, read to
`Editor` / `Viewer` / System Manager; the write endpoint accepts only an allowlisted field set and
rebuilds child rows from sanitised copies, exactly as `save_chart` does.

**Upsert key — a genuine judgement call.** DS Data Mapping has no autoname (hash-named), so an
upsert needs an explicit natural key. Proposed: **`(data_source, external_table, external_field)`**
→ updates `target_doctype` / `target_field` / `mapping_status`. Note the Mapping view currently
produces *table-level* mappings only (`external_table` + `target_doctype`; it never sets
`external_field`), so in practice today the key is `(data_source, external_table)` with an empty
field. The endpoint should handle what the UI actually sends and not invent field-level behaviour
that has no UI yet.

## 5. Explicitly not decided here

- Any validation or result-comparison logic — DS Validation Comparison, deferred separately.
- What `Ready to Publish` requires, or what publishing does.
- Field-level (as opposed to table-level) mapping, which no UI produces yet.
- Governance/approval on the project itself (native Workflow if ever wanted).

## Decisions needed before this is built

1. **§2 — confirm mappings stay data-source-scoped** (recommended), accepting that mapping status is
   shared across projects rather than per-project.
2. **§1 — confirm the single automatic transition** (`Not Started → Mapping` on first save) and that
   everything onward is a manual button.
3. **§4 — confirm the upsert key** `(data_source, external_table, external_field)`.
4. **§2 — confirm the `?project=` query param** for carrying project identity into the Studio page.
