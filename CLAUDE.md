# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Dashboard Studio is a Frappe/ERPNext application with two connected jobs:

1. Import and migrate dashboards from systems such as Metabase into controlled Frappe analytics definitions.
2. Visually create and edit dashboards and diagrams that can be published to viewers such as Sophia/UCC Intelligence Platform.

The product name is generic on purpose. Do not make Metabase, Sophia, UCC, or any single viewer the core architecture — they are one import source and one publish destination.

## Critical environment constraint

**There is no Bench in this repo and no network route to the live site, Metabase, or any database.** The app installs into an *external* Frappe Bench. Everything here is built and tested against fixtures/mocks. When you touch code that would run inside Frappe, keep the pure logic Frappe-free and unit-testable (see the DI seams below). Do not attempt `bench install`/`bench migrate` — they will not work here.

**Live verification happens, but the user runs it, not you.** The working pattern: you write a paste-and-run script, they run it on the real site and send back the output. That loop has settled several things fixtures could not (Insights v3's real chart config, Metabase's MBQL 5 serialisation, the live URL routes). Two rules follow:

- **State fixture-tested vs live-verified explicitly, every time.** Never let a fixture-passing claim read as a live-confirmed one.
- **Console scripts must survive all three ways they get run** — pasted, piped (`bench console < file`), and `exec(open(...).read())`. Put everything inside one function with its imports inside it, and leave **no blank lines inside any indented block**. `bench console` is an *embedded* IPython where `globals()` and `locals()` are different dicts, so a bare `exec` leaves module-level names unreachable from the functions that need them; and IPython reading stdin ends a block at the first blank line. Both faults have already cost a round trip. `scripts/insights_v3_probe.py` is the worked example, and `tests/test_insights_v3_probe.py` enforces both rules.

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

`scripts/` also holds two **read-only diagnostics that only run on the live site** — hand them to the user, don't try to run them here. Both are covered by tests that execute them against a fake Bench.

- `insights_v3_probe.py` — which Insights DocTypes exist, their real field names, a v3 query's `operations` and a v3 chart's `config` printed whole.
- `metabase_table_inventory.py` — which physical tables the Metabase cards read, for narrowing a database GRANT. Withholds its suggested GRANT block whenever anything is unresolved, on purpose.

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

Two ways in, both ending at the same Visualize form. **Flag-don't-guess is the shared contract:** anything that cannot be translated safely sets `supported: false` with named reasons rather than emitting a wrong translation. A silently mistranslated filter migrates a metric that counts the wrong rows.

- **Pasted SQL** — `analyze_sql`/`analyze_sql_file` (`parser.py`) conservatively parse a single SELECT into a structured description (doctypes, COUNT/SUM/AVG, flat WHERE filters, single-column GROUP BY, one simple JOIN). Refuses subqueries, multiple joins, OR clauses, unparsable conditions, window/UNION/HAVING/CASE/DISTINCT.
- **A card read from Metabase's API** — `client.fetch_card` (one GET) → `card.describe_card` → `api.migration.import_metabase_card`. The card already knows its title, chart type and axes, so those arrive as facts and land *Confirmed*; guessing them back out of SQL text is where this flow's bugs came from.

**The SQL lives at `dataset_query.stages[0].native`, not `native.query`.** UCC's Metabase serialises MBQL 5, where the top-level `lib/type` reads `mbql/query` for *every* card — GUI or native alike — so the native check must happen on the **stage**, not the top level. `describe_card` refuses: a GUI question, a multi-stage query (stage 0 alone answers a different question), template tags or `{{…}}`/`[[…]]`, an unmapped `display`, and a card with no `result_metadata`.

**`client.py` can only read.** No method parameter, no generic `request()` helper, no second function — a later caller cannot pass `"POST"` to something that only knows GET. `POST /api/card/:id/query` and `POST /api/dataset` execute SQL against the connected production database and must never be added. `POST /api/dataset/native` compiles MBQL to SQL *without* executing, which is real and tempting — see ADR-006 before reaching for it.

`referenced_tables()` answers "which physical tables does this card read", for narrowing a database GRANT. Over-inclusion is the safe direction there — a surplus table costs one GRANT, a missing one breaks a dashboard — which is why its MBQL side is a recursive scan for `source-table` keys rather than a walk of the documented nesting.

### Frappe Insights handoff (`dashboard_studio/api/insights.py`)

Writes a pasted/imported SQL query into Insights as a real, queryable Query. Studio **never executes it** — Insights runs it later under its own permissions. That boundary is the reason the module refuses anything that is not a single read-only statement.

**Insights v3 only.** v2 was removed, not branched on. The v2 DocTypes still ship alongside v3, which is why the original version guard was unsound: `exists("DocType", "Insights Query")` is True on a v3 site, so it passed and wrote an orphan invisible to the v3 UI. Guard on `Insights Query v3`. Same fault, same fix, twice: the Site DB check must read `Insights Data Source v3`, not the v2 table that happens to hold a row of the same name.

Shapes below are **read back from real records on the live site**, not reasoned to — treat them as fixed points and re-verify against a real record before changing any of them:

- A query needs a **Workbook** (reqd Link) and carries its SQL inside `operations`: `[{"type": "sql", "raw_sql": …, "data_source": "Site DB"}]`.
- URL is `/insights/workbook/{workbook}/query/{name}` — the v2 path resolves to an empty shell.
- Chart `config` is `{"x_axis": {"dimension": {column_name, data_type, dimension_name}}, "y_axis": {"series": [{"measure": {aggregation, column_name, data_type, measure_name}, "type": …}]}}`.

**v3 never persists a query's result** (confirmed live: zero `Insights Query Result` rows reference a v3 query). So there is nothing to read back after the person presses Run, and automatic axis application is gone with it. The per-column `data_type` that v3 requires now comes from the only honest source available — a Metabase card's `result_metadata` via `describe_card`. Without columns, `apply_insights_chart` **refuses rather than guessing**, because v3 accepts any config and then silently draws nothing.

`_mask_sql`/`_normalised_sql` are the SELECT-only guard, and they are quote-aware on purpose: strip-then-check is a bypass (`SELECT '/*' AS a FROM t; DROP TABLE t`). Every ambiguity resolves toward *code*, never toward comment.

## Working rules (project direction — still in force)

- Store dashboard logic as managed records and structured JSON, not chart-specific Python. Never build the product as one large Server Script or Custom HTML Block.
- **Metric definition stays on DS Metric — settled, do not reopen.** Source DocType, dimension, measure and aggregation belong to the *approved* DS Metric, never to DS Chart. The Sophia mockup draws them as per-chart properties; where the mockup and the governance model conflict, the governance model wins. DS Metric's approval gate is the only thing standing between an unreviewed number and a published EduTrust dashboard, and per-chart metric config would route around it. A chart selects a metric and controls presentation (title, type, layout, result order, filters) — nothing else.
- **Chart filters stay scoped per chart.** Dashboard-level filters are deferred; if they return it will be as a UI that fans out to per-chart filters, not as a new dashboard-level filter store.
- **Never store configuration as an opaque JSON blob.** `deploy_check`, the schema test and the test fake's `reqd` enforcement all operate on **fields** — a JSON blob is invisible to every protection in this repo. It cannot be validated by Frappe, queried, diffed per-field by `track_changes`, or checked for drift against a live site. That is precisely why the six placeholder DocTypes are frozen: their `*_json` fields are unreachable by all of it. New configuration goes in real fields, using `depends_on` where relevance is type-specific.
- **Chart colour is platform-level, never per chart — settled, do not reopen.** Consistent encoding across the seven criteria is part of the evidence: a reviewer must not have to relearn what blue means between Criterion 4 and Criterion 7. Sophia's palette is deliberately platform-wide (`--ucc-chart-0..5` on `.ucc-platform`). If colour ever becomes configurable it is one palette for the platform, not a per-chart property.
- **Label format (count vs percentage) belongs to DS Metric, not DS Chart.** Whether a figure is a count or a percentage is a fact about what it measures, derivable from the approved `calculation_type`. A chart-level format control would let an Editor display an approved count of 62 as "62%" with no review — the same governance hole as per-chart metric config. Not built; queued behind the publish contract.
- **The workspace tabs carry no stage state — settled, do not reopen.** Stage belongs to the *dashboard*, not to the workspaces, and it is shown by the toolbar readiness chip, which renders in all five. Three reasons the tabs must not: only three of the five have per-dashboard state at all (Data & DocTypes is a site-wide catalogue and Metabase Migration is a project), so two ticks would be invented for visual symmetry; a Validation tick would decay silently, because a pass older than the chart's last edit does not count and there is no event to repaint on — a stale tick is worse than none, because it is trusted; and it would assert an order the product does not have, since a hand-built dashboard never touches Migration.
- **The publish rules have one definition, `governance.publish_readiness`.** `advance_status` throws on the blockers it returns and `get_studio_dashboard` displays them. Never add a second, cheaper computation for the display path: an indicator that disagreed with the gate would show *ready* and then refuse, which is the two-code-paths fault in `docs/SOPHIA_FAULT_PATTERN.md` rebuilt in our own repo.
- **Never translate another tool's query language — take the text that tool produced.** ADR-006: Dashboard Studio does not compile Metabase MBQL into Insights operations. It is mechanically possible for simple shapes, and it makes *us* the authority on what a question computes; a translation that disagrees produces a different number with no error, which is the `docs/SOPHIA_FAULT_PATTERN.md` fault — *"they do not fail, they disagree."* Translation is also unambiguous exactly where a human could rewrite the query in a minute, and reaches for generated expression strings exactly where automation would be worth having: its safety is inversely correlated with its usefulness.
- Never execute arbitrary user- or AI-generated SQL. AI may *propose* structured configs; the server validates; a user approves.
- Metabase migration must include source mapping and result comparison before publishing.
- Keep `reference/` (production legacy: the Custom Block + seven Criterion Server Scripts) and `prototypes/` (UX references only) unchanged unless explicitly asked.
- Small, reviewable commits with verification evidence. Commits go directly to `main`, one concern per commit, no PR unless asked.
- New non-trivial logic ships with a failing-first test (Python unittest, or a Node `*.test.js` self-check for pure JS logic). Run the **full** suite after changes, not just new tests.
- **Prove the check bites.** After a fix, neuter it and watch the suite fail. A test that passes both ways tested nothing, and this has caught several — including a `ruff --fix` that silently reintroduced a blank line into a paste-safe script seconds after it was written.
- **Verify UI fixes by pixels, not by call.** Screenshot the thing and compare, don't assert that the right function ran. The Line-renders-as-Bar bug survived because the DOM was correct by its own lights; a hash comparison of the rendered area caught it immediately. A screenshot also catches what assertions miss (a layout rendered as giant ellipses while every DOM assertion passed) — and assertions catch what screenshots miss (a click swallowed by a mid-gesture re-render). Use both.

## Security boundaries

- No unrestricted SQL editor for ordinary users; only approved aggregations/operators.
- No field outside the allowlist; no join outside an approved relationship.
- No silent formula or denominator changes; no publishing without explicit approval.
- No API credentials in source control; no AI provider keys in browser code; no personal student data in fixtures or tests.
- **The Metabase key lives in `site_config.json`** (`metabase_url`, `metabase_api_key`) — per-site, outside this repo, unreachable by a fixture export. It is fetched **server-side only**: the SPA calls our endpoint, our endpoint calls Metabase. Never return it to the browser, never log it, and never echo it in a refusal — including the 401 path, where "helpful" context puts it into `_server_messages` and straight into a user's browser.
- **A key's group is a requirement someone has to meet, not a fact you can assert.** Metabase has no read-only key flag; only the group restricts it. If the configured key is in Administrators — or any group with `create-queries: query-builder-and-native` — nothing on the Metabase side restricts it and our GET-only client is the *only* protection, not the second line. Metabase's own permission UI has been observed **not** to gate `/api/dataset/native` on this instance, so the durable control is a SELECT-only database login, not a Metabase setting.

## Deeper background

`docs/` holds the project's design record — start with `MASTER_PROJECT_HANDOVER.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `SECURITY_AND_GOVERNANCE.md`. Note the docs describe the intended end state and predate parts of the current build, so trust the code for what exists today and the docs for direction.
