# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

One job: **convert a GUI-built Metabase question into a Frappe Insights v3 query built from clickable operations** — Select Source, Filter Rows, Join Table, Group & Summarize. A migrated report is then maintainable in Insights' own editor rather than being a block of pasted SQL nobody can click.

Two ways in, one destination. A **Metabase card id** is read and translated from its MBQL structure. **Pasted SQL** is parsed and translated too — same operations, same verification gate — for a single table with a flat WHERE and a GROUP BY. Joins and subqueries are refused on the SQL path *by name*, because `analyze_sql` hands a join condition back as unparsed text with table aliases still in it; splitting that string is how a join gets built that runs, returns rows, and answers a different question. The card path can do joins because Metabase hands the two sides over already separated.

The types Insights needs on every dimension and measure come from Metabase's field metadata on the card path, and from **Frappe's own DocType metadata** on the SQL path (`tab<DocType>` → `frappe.get_meta`). Neither path ever guesses a type.

This was once a much larger product (dashboard builder, source mapping, DocType catalogue, validation centre, governance/publishing). All of it is in `archive/` — see `archive/README.md`. **Nothing in `archive/` is imported, tested, linted or shipped.** Don't fix things in there; if something is needed again, move it back and give it tests.

## Critical environment constraint

**There is no Bench in this repo and no network route to the live site, Metabase, or any database.** The app installs into an *external* Frappe Bench. Everything here is built and tested against fixtures/mocks. Keep pure logic Frappe-free and unit-testable (see the DI seams below). Do not attempt `bench install`/`bench migrate` — they will not work here.

**Live verification happens, but the user runs it, not you.** The pattern: you write a paste-and-run script, they run it on the real site and send back the output. That loop settled Insights v3's real chart config, Metabase's MBQL 5 serialisation, and the live URL routes. Two rules follow:

- **State fixture-tested vs live-verified explicitly, every time.** Never let a fixture-passing claim read as a live-confirmed one.
- **Console scripts must survive all three ways they get run** — pasted, piped (`bench console < file`), and `exec(open(...).read())`. Put everything inside one function with its imports inside it, and leave **no blank lines inside any indented block**. `bench console` is an *embedded* IPython where `globals()` and `locals()` are different dicts, so a bare `exec` leaves module-level names unreachable from the functions that need them; and IPython reading stdin ends a block at the first blank line. Both faults have already cost a round trip. `scripts/metabase_table_inventory.py` is the worked example, and its test enforces both rules.

## Commands

```bash
# Python tests — plain unittest, no Frappe site needed (pure logic + injected fakes)
python -m unittest discover -s dashboard_studio/tests
# Single test
python -m unittest dashboard_studio.tests.test_convert_gate.TestTheGate

# Frontend logic self-check — pure JS, run under Node (no browser/bundler)
node dashboard_studio/public/js/studio_core.test.js

# Lint (config in pyproject.toml: ruff, line-length 110, py310)
ruff check dashboard_studio scripts

# Repo checks (required files, JSON/Python syntax, secret scan) — also: make validate
python scripts/validate_repository.py
```

Do not lint `archive/`, `reference/` or `prototypes/`. The first is dead code by definition; the others are Frappe Server Scripts and UX references where `frappe` is an injected global (ruff reports hundreds of false `F821`).

`scripts/metabase_table_inventory.py` is a **read-only diagnostic that only runs on the live site** — hand it to the user, don't try to run it here. It reports which physical tables the Metabase cards read, for narrowing a database GRANT, and withholds its suggested GRANT block whenever anything is unresolved.

## Architecture

Frappe app layout: the Python package is `dashboard_studio/`, and the Frappe *module* of the same name is nested at `dashboard_studio/dashboard_studio/`. The app now ships **no DocTypes of its own** — it writes Insights' records and reads Metabase's.

The whole flow:

```
Metabase card id
  → client.fetch_card + fetch_table_metadata   # GETs, read-only
  → convert.build_metadata                     # ids → names + data types
  → mbql.translate_card                        # MBQL 5 → Insights operations
       (or) analyze_sql → sql_ops.operations_from_sql   # pasted SQL → the same
  → convert.convert_metabase_card              # writes an [UNVERIFIED] query
  → convert.verify_converted_query             # a person clears the marker
```

### The verification gate — the reason translation is allowed at all

`docs/DECISIONS.md` ADR-006 rejected translation; **ADR-007 reopened it on one condition**, and that condition is load-bearing:

- A converted query is titled `[UNVERIFIED] …`. The marker is in the **title** so it travels into Insights — someone who finds the query there, having never seen this tool, still learns nobody checked it.
- Verifying takes the number from Metabase and the number from Insights. **A mismatch refuses and leaves the marker.** There is no "verify anyway".
- The translated operations are listed in readable form so a wrong translation can be spotted before the query is ever run.

Never weaken any of that. A translation that disagrees with Metabase **does not fail, it returns a different number** — the fault `docs/SOPHIA_FAULT_PATTERN.md` names. The gate is what pays for the risk.

### MBQL 5 → operations (`integrations/metabase/mbql.py`)

Frappe-free and metadata-injected, so the whole translation is unit-testable. **Both formats were read from source at the installed versions** — the first attempt at this failed because both ends were assumed:

- Metabase MBQL 5 (`lib/schema.cljc`, `schema/join.cljc`, `schema/ref.cljc`): a stage carries `source-table`, `filters` (**plural**), `aggregation`, `breakout`, `joins`, `expressions`, `fields`, `order-by`, `limit`. A field ref is `[:field opts id]` — **options at position 1, identifier at position 2**. That reversal is what made the first attempt parse nothing. A join's source table is inside the join's own `stages`.
- Insights v3.12.2 (`frontend/src2/types/query.types.ts`): `source` / `filter` / `join` / `summarize`, with `TableArgs`, `FilterRule`, `JoinArgs` and `SummarizeArgs`.

**Flag-don't-guess, harder than anywhere else.** Everything off the rule table refuses **by name and hands back no operations** — a partial operation list is a query that answers a different question. Refused: compound aggregations (ratios), custom columns, row limits, sorts, explicit column selections, questions built on other questions, multi-stage queries, date buckets, unknown ids, field-to-field filters.

Expected operations are asserted **in full** in the tests, not spot-checked: the failure mode here is a query that runs fine and answers something else, so "the right keys are present" proves nothing.

### Insights plumbing (`api/insights.py`)

What the converter needs and no more: the v3 DocType names, `clamp_title`, `_require_insights`, workbook resolution and `list_insights_workbooks`. The SQL-paste path that used to live here is in `archive/api_insights_sql_path.py`.

**Insights v3 only, and the version guard is subtle.** The v2 DocTypes still ship alongside v3, so `exists("DocType", "Insights Query")` is True on a v3 site — the original guard passed and wrote an orphan nothing could open. Guard on `Insights Query v3`. Same fault twice: the Site DB check must read `Insights Data Source v3`, not the v2 table that happens to hold a row of the same name.

`title` is a Frappe `Data` field — varchar(140) — and Frappe **aborts the insert** rather than trimming. `clamp_title` runs on the resolved name, so a caller-supplied title is clamped too.

### Metabase client (`integrations/metabase/client.py`)

**Can only read.** `_get` takes no method parameter, so no later caller can turn it into a POST. `POST /api/card/:id/query` and `POST /api/dataset` execute SQL against the connected production database and must never be added. `POST /api/dataset/native` compiles MBQL to SQL without executing, which is real and tempting — see ADR-006/007 before reaching for it.

`card.py` still imports `TABLE_PATTERN` from `parser.py`, so the SQL parser is load-bearing for reading which tables a card touches even though the SQL path is gone.

### Front end (`public/js/`)

**Dependency-free vanilla JS, no bundler.** The Desk page (`.../page/dashboard_studio/`) mounts it via `frappe.require`. Do not add a JS build step or a frontend dependency without explicit sign-off.

- `studio_core.js` — pure logic, Node-testable via `studio_core.test.js`. Put new logic here so it can be checked without a browser.
- `studio_app.js` — the whole UI: card id in, workbook picker, conversion result, verification panel.

## Working rules

- **The gate is not negotiable.** See above. Nothing may make a conversion look done before a person has compared the numbers.
- Never execute arbitrary user- or AI-generated SQL. This tool executes nothing, anywhere.
- Never store configuration as an opaque JSON blob when a real field would do — a blob is invisible to validation, querying, and per-field diffing.
- Keep `reference/`, `prototypes/` and `archive/` unchanged unless explicitly asked.
- Small, reviewable commits with verification evidence. Commits go directly to `main`, one concern per commit, no PR unless asked.
- New non-trivial logic ships with a failing-first test (Python unittest, or a Node `*.test.js` self-check for pure JS). Run the **full** suite after changes.
- **Prove the check bites.** After a fix, neuter it and watch the suite fail. A test that passes both ways tested nothing — this has caught several, including a test that was passing via the wrong branch entirely.
- **Verify UI fixes by pixels, not by call.** Screenshot and compare; don't assert that the right function ran. A Line chart rendering as bars survived because the DOM was correct by its own lights. Assertions also catch what screenshots miss (a click swallowed by a mid-gesture re-render) — use both.

## Security boundaries

- Read-only against Metabase: GETs only, nothing written there, ever.
- **The Metabase key lives in `site_config.json`** (`metabase_url`, `metabase_api_key`) — per-site, outside this repo. Fetched **server-side only**: the SPA calls our endpoint, our endpoint calls Metabase. Never return it to the browser, never log it, never echo it in a refusal — including the 401 path, where "helpful" context puts it into `_server_messages` and into a user's browser.
- **A key's group is a requirement someone has to meet, not a fact you can assert.** Metabase has no read-only key flag; only the group restricts it. A key in Administrators — or any group with `create-queries: query-builder-and-native` — is unrestricted on the Metabase side, making our GET-only client the *only* protection. Metabase's permission UI has been observed **not** to gate `/api/dataset/native` on this instance, so the durable control is a SELECT-only database login.
- `fixtures/role.json` creates `Dashboard Studio Editor` — every `frappe.only_for` depends on it. Don't remove it.
- No personal student data in fixtures or tests.
