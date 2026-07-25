# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Dashboard Studio is a Frappe/ERPNext application with two connected jobs:

1. Import and migrate dashboards from systems such as Metabase into controlled Frappe analytics definitions.
2. Visually create and edit dashboards and diagrams that can be published to viewers such as Sophia/UCC Intelligence Platform.

The product name is generic on purpose. Do not make Metabase, Sophia, UCC, or any single viewer the core architecture — they are one import source and one publish destination.

## Critical environment constraint

**There is no Bench in this repo, and sessions here have had no live Frappe/staging access.** The app installs into an *external* Frappe Bench. Everything is therefore built and tested against fixtures/mocks; nothing has been verified by `bench migrate` or on a real site. When you touch code that would run inside Frappe, keep the pure logic Frappe-free and unit-testable (see the DI seams below), and clearly flag anything that only a live Bench can confirm. Do not attempt `bench install`/`bench migrate` — they will not work here.

## Commands

```bash
# Python tests — plain unittest, no Frappe site needed (pure logic + injected fakes)
python -m unittest discover -s dashboard_studio/tests
# Single test
python -m unittest dashboard_studio.tests.test_ds_metric_execution.TestDSMetricExecution.test_static_filter_maps_to_conditions

# Frontend logic self-checks — pure JS, run under Node (no browser/bundler)
node dashboard_studio/public/js/studio_core.test.js
node dashboard_studio/public/js/studio_charts.test.js

# Lint (config in pyproject.toml: ruff, line-length 110, py310)
ruff check dashboard_studio scripts

# Repo checks (required files, JSON/Python syntax, secret scan) — also: make validate
python scripts/validate_repository.py
```

Do not lint `reference/` — those are Frappe Server Scripts where `frappe` is an injected global; ruff reports hundreds of false `F821` there.

## Architecture

Frappe app layout: the Python package is `dashboard_studio/`, and the Frappe *module* of the same name is nested at `dashboard_studio/dashboard_studio/` (standard Frappe convention). DocTypes are auto-discovered from `.../doctype/<snake_name>/` folders — there is no per-DocType registration in `hooks.py`.

### Two DocType generations coexist — do not conflate them

- **Old placeholder DocTypes** (6, not 5: `Dashboard Definition`, `Dataset Definition`, `Metric Definition`, `Migration Job`, `Migration Mapping`, and `Dashboard Component` — the child table of `Dashboard Definition`, `istable: 1`, easy to miss because nothing references it by name outside that parent) — opaque `*_json` Code fields, System-Manager-only perms. **Frozen: do not modify, rename, or remove.** Served by the old-path API (`build_metric_plan`, `run_metric`) which still reads them. All six ship with the app; none are orphans from another app.
- **New `DS`-prefixed DocTypes** (11: `DS Dashboard`, `DS Dashboard Section`, `DS Chart`, `DS Chart Filter`, `DS Metric`, `DS Metric Filter`, `DS Data Source`, `DS Data Mapping`, `DS Migration Project`, `DS Canvas Node`, `DS Validation Comparison`) — the real target schema, normalized fields, `Dashboard Studio Editor`/`Viewer` role perms. This is what active work builds on.

### Analytics runtime (the core, `dashboard_studio/analytics/`)

The data flow, and the boundary every metric must cross:

```
DS Metric record
  → build_plan_from_ds_metric (query_engine.py)   # adapter: DS Metric → engine config
  → validate_metric_config (validators.py)         # the security gate (see below)
  → build_query_plan (query_engine.py)             # non-executable plan dict
  → execute_query_plan (query_engine.py)           # runs the plan
```

Only the **count-by-single-dimension** slice executes end to end. Joins, multiple dimensions, and aggregations other than `count` are intentionally rejected, not half-implemented.

`validate_metric_config` is the single security chokepoint — both the old and DS paths route through it. It enforces: an aggregation/operator allowlist; a **field allowlist** (referenced fields must be listed); **field-name syntax** (`[A-Za-z_][A-Za-z0-9_]*`, because field names are interpolated into ORM `fields`/`order_by`); and it returns *normalized* conditions, never the raw input. Never weaken these. `build_plan_from_ds_metric` adds **block-by-default**: a DS Metric with no `allowed_fields` refuses to run (a pure count's `name` measure is the one auto-exempt field). Field *existence* validation against real DocType metadata is deferred — it needs a live Bench.

**Dependency-injection seams (why tests work without a Bench):** `execute_query_plan(plan, *, fetch=None, permission_check=None)` — production defaults call Frappe (`frappe.only_for`, `frappe.get_all`); tests pass a fixture `fetch` and a no-op check. `build_plan_from_ds_metric` takes a plain dict (`frappe.get_doc(...).as_dict()` shape), so it is Frappe-free.

### API layer (`dashboard_studio/api/`, whitelisted endpoints)

Two-level roles (`Dashboard Studio Editor`/`Viewer`, System Manager as superuser) are enforced on the **DS-facing** endpoints only: `get_studio_dashboard`/`run_ds_metric`/`list_ds_metrics` (read = Editor/Viewer/SysMan), `save_chart` (write = Editor/SysMan). `save_chart` only writes an allowlisted field set and rebuilds child `chart_filters` from sanitized copies. Old-path endpoints stay System-Manager-only. Note: `run_ds_metric` passes a no-op `permission_check` to the engine because the endpoint already authorized the caller (the engine default would re-require System Manager).

### Visual editor SPA (`dashboard_studio/public/js/`)

**Dependency-free vanilla JS, no bundler.** The Desk page (`.../page/dashboard_studio/`) mounts it via `frappe.require` (loads assets page-scoped). Do not add a JS build step or a frontend dependency without explicit sign-off — this is a deliberate constraint, not an accident.

- `studio_core.js` / `studio_charts.js` — **pure logic** (grid math, edit validation, filter/operator rules, hand-built SVG chart rendering, mapping-node shapes). UMD-style; Node-testable via the matching `*.test.js`. Put new logic here so it can be checked without a browser.
- `studio_app.js` — DOM layer: Design view (drag/resize chart grid, diagram editor) and Mapping view (source-table → DocType node map).
- `studio_mock.js` — **all mock data lives here, clearly `MOCK`-marked.** The app falls back to it whenever no live backend is reachable (i.e. always, in this repo). Mapping persistence and live metric results are mocked.

### Metabase import (`dashboard_studio/integrations/metabase/`)

`analyze_sql`/`analyze_sql_file` (`parser.py`) conservatively parse a single SELECT into a structured description (doctypes, COUNT/SUM/AVG, flat WHERE filters, single-column GROUP BY, one simple JOIN). **Flag-don't-guess is the contract:** anything it can't safely translate — subqueries, multiple joins, OR clauses, unparsable conditions, window/UNION/HAVING/CASE/DISTINCT — sets `supported: false` with reasons rather than emitting a wrong translation. Preserve that; a silently mistranslated filter migrates a metric that counts the wrong rows.

## Working rules (project direction — still in force)

- Store dashboard logic as managed records and structured JSON, not chart-specific Python. Never build the product as one large Server Script or Custom HTML Block.
- **Metric definition stays on DS Metric — settled, do not reopen.** Source DocType, dimension, measure and aggregation belong to the *approved* DS Metric, never to DS Chart. The Sophia mockup draws them as per-chart properties; where the mockup and the governance model conflict, the governance model wins. DS Metric's approval gate is the only thing standing between an unreviewed number and a published EduTrust dashboard, and per-chart metric config would route around it. A chart selects a metric and controls presentation (title, type, layout, result order, filters) — nothing else.
- **Chart filters stay scoped per chart.** Dashboard-level filters are deferred; if they return it will be as a UI that fans out to per-chart filters, not as a new dashboard-level filter store.
- **Never store configuration as an opaque JSON blob.** `deploy_check`, the schema test and the test fake's `reqd` enforcement all operate on **fields** — a JSON blob is invisible to every protection in this repo. It cannot be validated by Frappe, queried, diffed per-field by `track_changes`, or checked for drift against a live site. That is precisely why the six placeholder DocTypes are frozen: their `*_json` fields are unreachable by all of it. New configuration goes in real fields, using `depends_on` where relevance is type-specific.
- **Chart colour is platform-level, never per chart — settled, do not reopen.** Consistent encoding across the seven criteria is part of the evidence: a reviewer must not have to relearn what blue means between Criterion 4 and Criterion 7. Sophia's palette is deliberately platform-wide (`--ucc-chart-0..5` on `.ucc-platform`). If colour ever becomes configurable it is one palette for the platform, not a per-chart property.
- **Label format (count vs percentage) belongs to DS Metric, not DS Chart.** Whether a figure is a count or a percentage is a fact about what it measures, derivable from the approved `calculation_type`. A chart-level format control would let an Editor display an approved count of 62 as "62%" with no review — the same governance hole as per-chart metric config. Not built; queued behind the publish contract.
- **The workspace tabs carry no stage state — settled, do not reopen.** Stage belongs to the *dashboard*, not to the workspaces, and it is shown by the toolbar readiness chip, which renders in all five. Three reasons the tabs must not: only three of the five have per-dashboard state at all (Data & DocTypes is a site-wide catalogue and Metabase Migration is a project), so two ticks would be invented for visual symmetry; a Validation tick would decay silently, because a pass older than the chart's last edit does not count and there is no event to repaint on — a stale tick is worse than none, because it is trusted; and it would assert an order the product does not have, since a hand-built dashboard never touches Migration.
- **The publish rules have one definition, `governance.publish_readiness`.** `advance_status` throws on the blockers it returns and `get_studio_dashboard` displays them. Never add a second, cheaper computation for the display path: an indicator that disagreed with the gate would show *ready* and then refuse, which is the two-code-paths fault in `docs/SOPHIA_FAULT_PATTERN.md` rebuilt in our own repo.
- Never execute arbitrary user- or AI-generated SQL. AI may *propose* structured configs; the server validates; a user approves.
- Metabase migration must include source mapping and result comparison before publishing.
- Keep `reference/` (production legacy: the Custom Block + seven Criterion Server Scripts) and `prototypes/` (UX references only) unchanged unless explicitly asked.
- Small, reviewable commits with verification evidence. Commits go directly to `main`, one concern per commit, no PR unless asked.
- New non-trivial logic ships with a failing-first test (Python unittest, or a Node `*.test.js` self-check for pure JS logic). Run the **full** suite after changes, not just new tests.

## Security boundaries

- No unrestricted SQL editor for ordinary users; only approved aggregations/operators.
- No field outside the allowlist; no join outside an approved relationship.
- No silent formula or denominator changes; no publishing without explicit approval.
- No API credentials in source control; no AI provider keys in browser code; no personal student data in fixtures or tests.

## Deeper background

`docs/` holds the project's design record — start with `MASTER_PROJECT_HANDOVER.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `SECURITY_AND_GOVERNANCE.md`. Note the docs describe the intended end state and predate parts of the current build, so trust the code for what exists today and the docs for direction.
