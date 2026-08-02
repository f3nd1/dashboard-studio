# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

One job: **convert a pasted SQL query into a Frappe Insights v3 query built from clickable operations** — Select Source, Filter Rows, Join Table, Group & Summarize. A migrated report is then maintainable in Insights' own editor rather than being a block of pasted SQL nobody can click.

**One way in.** Paste the SQL; it is parsed and translated for one table, or two joined on a single `a.column = b.column`, with a flat WHERE and a GROUP BY. Further joins, and every ON clause whose two sides cannot be told apart with certainty, are refused *by name*. The Metabase **card id** route was removed — it is in `archive/metabase_mbql_card_path.py` with its HTTP client and tests, and nothing in the app calls Metabase any more.

**Metabase's own wrapper subqueries are flattened first, and only where that is an identity.** Its compiled SQL wraps every joined table in derived tables — `reference/metabase/duration_from_counselling_to_admission.sql` is the real thing, nesting `( select * from `tabX` ) AS `__mb_source`` inside a projection aliased `` `Student Applicant Model - Name` ``. A derived table is replaced by its base table only when it is a *pure projection*: the FROM source is `` `tabX` `` and nothing else, and every item is a plain column optionally aliased to its own name. Such a projection returns exactly the rows of the table it reads, so the swap changes nothing. A WHERE, a GROUP BY, an aggregate, a DISTINCT, a LIMIT, a join, a union, a rename or a literal in there means it is **not** an identity, so it stays a subquery and refuses by name. Without this, essentially every real Metabase report refused.

**A Frappe table is `` `tab<DocType>` `` with a LOWERCASE `tab`, and every pattern matches that prefix case-sensitively (`(?-i:tab)`).** Metabase names a derived table after the *humanized* table name, so joining `` `tabAssessment Result Detail` `` produces the alias `` `TabAssessment Result Detail - Name` `` — capital T. Matched case-insensitively, that alias read as a table called "Assessment Result Detail - Name": a name in no alias map, so the join refused *while insisting the query lacked the shape it plainly had*, plus an invented DocType that `_table_columns` would then refuse on. `table_to_doctype` is case-sensitive for the same reason — a DocType named "Table Layout" was beheaded into "le Layout" by a second strip.

**A join is oriented by table, never by writing order.** `analyze_sql` returns `{doctype, join_type, source_column, join_column}` where `source_column` always belongs to the FROM table — which is what Insights' `join_condition` means. `b.ref = a.po` and `a.po = b.ref` are the same join, so deciding from which side of the `=` a column was typed would silently swap them for half of all real queries. Both column names are then checked against `frappe.get_meta` for their own DocType before anything is written; that check is what makes reading a join out of text safe at all. Related: the source table is the **FROM** table, not the first `` `tab…` `` in the text — a joined table's column can appear in the SELECT list first, and building on that side is a different question with the same row count.

The types Insights needs on every dimension and measure come from **Frappe's own DocType metadata** (`tab<DocType>` → `frappe.get_meta`). A type is never guessed — and the same lookup is what proves a join's two column names are real.

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
pasted SQL
  → parser.analyze_sql                         # tables, join, WHERE, GROUP BY
  → convert._table_columns                     # frappe.get_meta, per DocType
  → sql_ops.operations_from_sql                # → Insights operations
  → convert.convert_sql                        # writes an [UNVERIFIED] query
  → convert.verify_converted_query             # a person clears the marker
```

### The verification gate — the reason translation is allowed at all

`docs/DECISIONS.md` ADR-006 rejected translation; **ADR-007 reopened it on one condition**, and that condition is load-bearing:

- A converted query is titled `[UNVERIFIED] …`. The marker is in the **title** so it travels into Insights — someone who finds the query there, having never seen this tool, still learns nobody checked it.
- Verifying takes the number from the original report and the number from Insights. **A mismatch refuses and leaves the marker.** There is no "verify anyway".
- The translated operations are listed in readable form so a wrong translation can be spotted before the query is ever run.

Never weaken any of that. A translation that disagrees with the original **does not fail, it returns a different number** — the fault `docs/SOPHIA_FAULT_PATTERN.md` names. The gate is what pays for the risk.

The gate's *presence* is non-negotiable; its **weight** is not. It was deliberately made lighter — one row, "Same number? [ ] = [ ] [Confirm]" — because two labelled fields, a paragraph and a full-width button read like paperwork, and paperwork gets skipped. Both numbers are still typed, the server still refuses a mismatch, and the marker still stays. Keep it one line.

### SQL → operations (`integrations/metabase/parser.py` + `sql_ops.py`)

`analyze_sql` reads the text; `operations_from_sql` types it and builds the operations. Both are Frappe-free and metadata-injected (`columns` is `{DocType: {column: data_type}}`), so the whole translation is unit-testable without a Bench.

**The Insights side was read from source at the installed version** — v3.12.2, `frontend/src2/types/query.types.ts`: `source` / `filter` / `join` / `summarize`, with `TableArgs`, `FilterRule`, `JoinArgs` and `SummarizeArgs`. Those shapes live at the top of `sql_ops.py`; they came from the archived MBQL translator, which is why the comment there says so. Don't change a shape without reading that file — a key Insights doesn't recognise is dropped silently.

**Flag-don't-guess, harder than anywhere else.** Everything off the rule table refuses **by name and hands back no operations** — a partial operation list is a query that answers a different question. Refused: subqueries that are not provable passthroughs, more than one join, CROSS and self joins, an ON clause that is anything but a single equality of two qualified columns, an unqualified column that exists in both joined tables, a computed column in the SELECT list, a row limit, OR, UNION, HAVING, CASE, DISTINCT, window functions, more than one aggregate, LIKE and IN.

Two of those exist because the SELECT list and the LIMIT used to be read and then **silently dropped**: a computed column vanished, so the converted query answered a smaller question, and a `LIMIT 10` became "all of them". The one exception is `LIMIT 1048575`, the row cap Metabase appends to everything it compiles — an exact match on the constant observed in `reference/`, not a threshold, and any other value refuses.

Expected operations are asserted **in full** in the tests, not spot-checked: the failure mode here is a query that runs fine and answers something else, so "the right keys are present" proves nothing.

### Insights plumbing (`api/insights.py`)

What the converter needs and no more: the v3 DocType names, `clamp_title`, `_require_insights`, workbook resolution and `list_insights_workbooks`. The SQL-paste path that used to live here is in `archive/api_insights_sql_path.py`.

**Insights v3 only, and the version guard is subtle.** The v2 DocTypes still ship alongside v3, so `exists("DocType", "Insights Query")` is True on a v3 site — the original guard passed and wrote an orphan nothing could open. Guard on `Insights Query v3`. Same fault twice: the Site DB check must read `Insights Data Source v3`, not the v2 table that happens to hold a row of the same name.

`title` is a Frappe `Data` field — varchar(140) — and Frappe **aborts the insert** rather than trimming. `clamp_title` runs on the resolved name, so a caller-supplied title is clamped too.

### Nothing here calls Metabase

The read-only HTTP client went to `archive/metabase_client_card_path.py` with the card path. If a Metabase call is ever needed again, read ADR-006/007 first: `POST /api/card/:id/query` and `POST /api/dataset` execute SQL against the connected production database and must never be added, and `POST /api/dataset/native` compiles MBQL to SQL without executing — real, and tempting.

`integrations/metabase/card.py` stays, unused by the app: `scripts/metabase_table_inventory.py` imports `referenced_tables` from it, and it in turn imports `TABLE_PATTERN` from `parser.py`.

### Front end (`public/js/`)

**Dependency-free vanilla JS, no bundler.** The Desk page (`.../page/dashboard_studio/`) mounts it via `frappe.require`. Do not add a JS build step or a frontend dependency without explicit sign-off.

- `studio_core.js` — pure logic, Node-testable via `studio_core.test.js`. Put new logic here so it can be checked without a browser.
- `studio_app.js` — the whole UI: SQL in, workbook picker, conversion result, verification panel.

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

- Nothing in the app talks to Metabase at all. `scripts/metabase_table_inventory.py` is the only thing that does, it is hand-run on the live site, and it is GETs only.
- **The Metabase key lives in `site_config.json`** (`metabase_url`, `metabase_api_key`) — per-site, outside this repo. Only `scripts/metabase_table_inventory.py` reads it now, server-side. Never return it to the browser, never log it, never echo it in a refusal — including the 401 path, where "helpful" context puts it into `_server_messages` and into a user's browser. If a Metabase call is ever added back to the app, that rule comes with it.
- **A key's group is a requirement someone has to meet, not a fact you can assert.** Metabase has no read-only key flag; only the group restricts it. A key in Administrators — or any group with `create-queries: query-builder-and-native` — is unrestricted on the Metabase side, making our GET-only client the *only* protection. Metabase's permission UI has been observed **not** to gate `/api/dataset/native` on this instance, so the durable control is a SELECT-only database login.
- `fixtures/role.json` creates `Dashboard Studio Editor` — every `frappe.only_for` depends on it. Don't remove it.
- No personal student data in fixtures or tests.
