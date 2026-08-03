# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

One job: **convert a pasted SQL query into a Frappe Insights v3 query built from clickable operations** — Select Source, Filter Rows, Join Table, Group & Summarize. A migrated report is then maintainable in Insights' own editor rather than being a block of pasted SQL nobody can click.

**One way in.** Paste the SQL; it is parsed and translated for one table, or any number joined each on a single `a.column = b.column`, with a flat WHERE and a GROUP BY. Every ON clause whose two sides cannot be told apart with certainty is refused *by name*. The Metabase **card id** route was removed — it is in `archive/metabase_mbql_card_path.py` with its HTTP client and tests, and nothing in the app calls Metabase any more.

**Metabase's own wrapper subqueries are flattened first, and only where that is an identity.** Its compiled SQL wraps every joined table in derived tables — `reference/metabase/duration_from_counselling_to_admission.sql` is the real thing, nesting `( select * from `tabX` ) AS `__mb_source`` inside a projection aliased `` `Student Applicant Model - Name` ``. A derived table is replaced by its base table only when it is a *pure projection*: the FROM source is `` `tabX` `` and nothing else, and every item is a plain column optionally aliased to its own name. Such a projection returns exactly the rows of the table it reads, so the swap changes nothing. A WHERE, a GROUP BY, an aggregate, a DISTINCT, a LIMIT, a join, a union, a rename or a literal in there means it is **not** an identity, so it stays a subquery and refuses by name. Without this, essentially every real Metabase report refused.

**Metabase wraps an AGGREGATING question's joins too, and that wrapper is lifted rather than unwrapped.** When a question aggregates over joined tables the joins become a derived table and the aggregate runs outside it, over columns the wrapper has *renamed* (`` `Child_3c522490`.`metric` AS `Child_a3e4a16b` ``). That is not a passthrough, so `unwrap_derived_tables` correctly leaves it alone — but it is still removable for a different and equally provable reason: it neither filters nor aggregates, so it returns the same *rows* as the query inside it, and a rename is a bijection on columns. `lift_renaming_wrapper` maps the outer references back through the wrapper's own `X AS Y` list and folds it into one flat statement. Both rules are needed and they are not the same rule. `dashboard_studio/tests/fixtures/quality_performance_outcomes.sql` is the real capture. Not lifted: an outer WHERE, a wrapper that groups/aggregates/limits, an item that is not a rename, an outer reference the wrapper does not define, and — a narrow one — grouping by an alias defined as `col * 1`, since `'abc' * 1` is 0 in MySQL and the types are not known at that point.

**`col * 1` on a TEXT column REFUSES, and the reason is worth reading before trying again — ADR-009 and its amendment.** Metabase writes `* 1` to cast before aggregating; at UCC it does that to `actual_value`, a Frappe **Data** field. ADR-009 allowed it to unblock the report, and that allowance could not be delivered: `data_type` on a measure describes the result, it does not convert anything, so Insights' engine reached the text column and died on `'StringColumn' object has no attribute 'mean'`. **Do not try again by setting a type or a flag — it needs the `cast` OPERATION**, whose `CastArgs` shape has not been read from `query.types.ts` (only `source`/`filter`/`join`/`summarize` were), and an unrecognised key is dropped silently, so a guess fails identically while looking fixed. The real fix is retyping the Frappe field to Float or Currency, which also makes the non-numeric rows visible instead of silently zero.

**A Frappe table is `` `tab<DocType>` `` with a LOWERCASE `tab`, and every pattern matches that prefix case-sensitively (`(?-i:tab)`).** Metabase names a derived table after the *humanized* table name, so joining `` `tabAssessment Result Detail` `` produces the alias `` `TabAssessment Result Detail - Name` `` — capital T. Matched case-insensitively, that alias read as a table called "Assessment Result Detail - Name": a name in no alias map, so the join refused *while insisting the query lacked the shape it plainly had*, plus an invented DocType that `_table_columns` would then refuse on. `table_to_doctype` is case-sensitive for the same reason — a DocType named "Table Layout" was beheaded into "le Layout" by a second strip.

**A join is oriented by table, never by writing order.** `analyze_sql` returns a LIST of `{doctype, join_type, source_table, source_column, join_column}` where `join_column` always belongs to the table being joined and `source_column` to one already in scope — which is what Insights' `join_condition` means, its `left_column` being a column of the result so far. N joins are N operations for exactly that reason: each join adds its table to the scope the next one may attach to, so the second is not a harder problem than the first. Refused: a join attaching to a table the query has not reached yet, and the same DocType joined twice (`columns` is keyed by DocType, so two copies cannot be told apart). `b.ref = a.po` and `a.po = b.ref` are the same join, so deciding from which side of the `=` a column was typed would silently swap them for half of all real queries. Both column names are then checked against `frappe.get_meta` for their own DocType before anything is written; that check is what makes reading a join out of text safe at all. Related: the source table is the **FROM** table, not the first `` `tab…` `` in the text — a joined table's column can appear in the SELECT list first, and building on that side is a different question with the same row count.

The types come from **Frappe's own DocType metadata**, and the column list from the **database itself** (`frappe.db.get_table_columns`, falling back to `get_db_table_columns`). Both are needed and neither substitutes for the other. `meta.fields` returns the fields somebody *defined* — not `parent`, which is the only column a child-table join can use, so without a seed those joins refused.

**A DocType's fields are never a substitute for its table's columns, and there is no fallback to them.** They drift in both directions, and both have shipped a query that converted cleanly and then failed the moment it was opened:

- Frappe's `_user_tags`, `_comments`, `_assign`, `_liked_by` are its OPTIONAL columns and are not on every table — assuming them gave *"Column '_comments' is not found in table"*.
- A field can outlive the column it used to have. `corrective_action` is still on the DocType and gone from the table, and it reached a join's `select_columns` — *"Column 'corrective_action' is not found in table"*. That came from a "safe" fallback to DocType fields when the schema read was unavailable, which was neither safe nor needed.

So: ten framework columns are unconditional (`name`, `owner`, `creation`, `modified`, `modified_by`, `docstatus`, `idx`, `parent`, `parentfield`, `parenttype`), everything else is whatever the schema says, and if the schema cannot be read the conversion **refuses**. A guessed column list is precisely what produces a query that fails on open.

`select_columns` on a join needs no separate validation because it IS that column list — but only while there is no path that builds it from anything else. The `reference/` SQL is a useful sample and **not a schema**: it happens to show a table carrying all four optional columns, which is what made assuming them look safe.

**`tests/test_schema_drift.py` is a standing category, not a bug list.** Both column faults were found by a person opening a query and reading the error, one table at a time. That file builds a table whose schema drifts from its DocType, runs whole queries through the real converter, and asserts *generically* that no column outside the real list appears anywhere in the operations — walking every operation shape rather than naming a column. When a new shape of drift appears, add a **scenario** there; do not add a test for the column that happened to expose it. The walker raises on an operation type it does not recognise, so a new operation cannot slip past it silently.

**A join carries the columns the query READS, and that is the systemic answer to schema drift.** `select_columns` used to be every column of the joined table, so a disagreement about ANY column broke the report on open — even one nothing referenced. Both live failures came in that way, and neither column was used: the Quality Performance query reads 3 columns from one child table and 1 from the other, and was carrying 22 and 19. `_referenced_columns` collects what the filters, groupings, aggregates and join conditions actually name. That shrinks the category from "any column anywhere disagreeing" to "a column this query reads disagrees" — which is a real error worth refusing on rather than noise to survive.

**Insights keeps no column list of its own**, checked on the live site: `Insights Table v3` (1809 rows) holds sync/import configuration — `stored`, `sync_mode`, `last_synced_on`, `row_limit` — and no per-column child table; every column-shaped Insights DocType is empty. So a stale view lives in the query engine's connection, not in a record, and there is nothing here to resync. `scripts/insights_schema_check.py` reports that, plus Frappe's own redis `table_columns` cache, which everything reading through `frappe.db` shares — a stale entry there would make the converter and the site agree with each other and both be wrong.

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
python -m unittest dashboard_studio.tests.test_convert_gate.TestSqlConversion

# Frontend logic self-check — pure JS, run under Node (no browser/bundler)
node dashboard_studio/public/js/studio_core.test.js

# Lint (config in pyproject.toml: ruff, line-length 110, py310)
ruff check dashboard_studio scripts

# Repo checks (required files, JSON/Python syntax, secret scan) — also: make validate
python scripts/validate_repository.py
```

Do not lint `archive/`, `reference/` or `prototypes/`. The first is dead code by definition; the others are Frappe Server Scripts and UX references where `frappe` is an injected global (ruff reports hundreds of false `F821`).

`scripts/insights_schema_check.py` and `scripts/metabase_table_inventory.py` are **read-only diagnostics that only run on the live site** — hand them to the user, don't try to run them here. The first compares Insights' own idea of a table's columns against the database's; the second reports which physical tables the Metabase cards read, for narrowing a database GRANT, and withholds its suggested GRANT block whenever anything is unresolved.

## Architecture

Frappe app layout: the Python package is `dashboard_studio/`, and the Frappe *module* of the same name is nested at `dashboard_studio/dashboard_studio/`. The app now ships **no DocTypes of its own** — it writes Insights' records and reads Metabase's.

The whole flow:

```
pasted SQL
  → parser.analyze_sql                         # tables, join, WHERE, GROUP BY
  → convert._table_columns                     # frappe.get_meta, per DocType
  → sql_ops.operations_from_sql                # → Insights operations
  → convert.convert_sql                        # writes the Insights query
```

### No verification gate — and what carries the risk instead

`docs/DECISIONS.md` ADR-006 rejected translation; ADR-007 reopened it behind a human number check; **ADR-008 removed that check on request**. There is no `[UNVERIFIED]` marker and no comparison step. The gate is intact in `archive/api_convert_verification_gate.py` if it is ever wanted back.

Read ADR-008 before changing anything in the refusal path, because the trade it records is now load-bearing:

- A translation that disagrees with the original **does not fail, it returns a different number** — `docs/SOPHIA_FAULT_PATTERN.md`. Nothing detects that any more.
- So the refusal table IS the safety argument. Anything off it refuses **by name and hands back no operations**. Softening one refusal to make a query go through costs more than it did when a person was checking the number afterwards.
- Column names are checked against the table's **real schema** (`frappe.db.get_table_columns`) before anything is written, so a query that would not run refuses here rather than in Insights.
- The operations are listed back in readable form after conversion. That was never part of the number check — it is how a wrong translation gets spotted by reading it — and it stays.

### SQL → operations (`integrations/metabase/parser.py` + `sql_ops.py`)

`analyze_sql` reads the text; `operations_from_sql` types it and builds the operations. Both are Frappe-free and metadata-injected (`columns` is `{DocType: {column: data_type}}`), so the whole translation is unit-testable without a Bench.

**The Insights side was read from source at the installed version** — v3.12.2, `frontend/src2/types/query.types.ts`: `source` / `filter` / `join` / `summarize`, with `TableArgs`, `FilterRule`, `JoinArgs` and `SummarizeArgs`. Those shapes live at the top of `sql_ops.py`; they came from the archived MBQL translator, which is why the comment there says so. Don't change a shape without reading that file — a key Insights doesn't recognise is dropped silently.

**Flag-don't-guess, harder than anywhere else.** Everything off the rule table refuses **by name and hands back no operations** — a partial operation list is a query that answers a different question. Refused: subqueries that are not provable passthroughs, more than one join, CROSS and self joins, an ON clause that is anything but a single equality of two qualified columns, an unqualified column that exists in both joined tables, a computed column in the SELECT list, a row limit, OR, UNION, HAVING, CASE, DISTINCT, window functions, more than one aggregate, LIKE and IN.

Two of those exist because the SELECT list and the LIMIT used to be read and then **silently dropped**: a computed column vanished, so the converted query answered a smaller question, and a `LIMIT 10` became "all of them". The one exception is `LIMIT 1048575`, the row cap Metabase appends to everything it compiles — an exact match on the constant observed in `reference/`, not a threshold, and any other value refuses.

Expected operations are asserted **in full** in the tests, not spot-checked: the failure mode here is a query that runs fine and answers something else, so "the right keys are present" proves nothing.

**A WHERE or GROUP BY stops at the `)` that closes the subquery it lives in.** Both are found by scanning forward to the next keyword, which runs straight past the end of a Metabase wrapper: a perfectly ordinary `` `tabX`.`name` = 'literal' `` came back as `` … = 'literal' ) AS `__mb_source` `` and refused as unparsed. Conditions are whitespace-normalised for the same class of reason — `_CONDITION`'s value is `.+?` with no DOTALL, so one wrapped across two lines matched nothing.

**A refusal is only useful if its reasons are the real ones.** Qualifiers that resolve to nothing are collected apart and dropped when a subquery survived — inside a wrapper that could not be flattened, every alias is unknown by construction, and `'__mb_source' is not a table or alias` three times buries the line that says what is actually wrong under an identifier nobody typed. Reasons are de-duplicated for the same reason: one fault found in the WHERE, the GROUP BY and the aggregate is one fault.

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

- **Refusals are the safety argument now** (ADR-008). Anything that cannot be translated with certainty refuses by name and writes nothing. Do not soften one to make a query go through.
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
