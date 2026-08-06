# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

One job: **convert a pasted SQL query into a Frappe Insights v3 query built from clickable operations** — Select Source, Filter Rows, Join Table, Group & Summarize. A migrated report is then maintainable in Insights' own editor rather than being a block of pasted SQL nobody can click.

**One way in.** Paste the SQL; it is parsed and translated for one table, or any number joined each on a single `a.column = b.column`, with a flat WHERE and a GROUP BY. Every ON clause whose two sides cannot be told apart with certainty is refused *by name*. The Metabase **card id** route was removed — it is in `archive/metabase_mbql_card_path.py` with its HTTP client and tests, and nothing in the app calls Metabase any more.

**Metabase's own wrapper subqueries are flattened first, and only where that is an identity.** Its compiled SQL wraps every joined table in derived tables — `reference/metabase/duration_from_counselling_to_admission.sql` is the real thing, nesting `( select * from `tabX` ) AS `__mb_source`` inside a projection aliased `` `Student Applicant Model - Name` ``. A derived table is replaced by its base table only when it is a *pure projection*: the FROM source is `` `tabX` `` and nothing else, and every item is a plain column optionally aliased to its own name. Such a projection returns exactly the rows of the table it reads, so the swap changes nothing. A WHERE, a GROUP BY, an aggregate, a DISTINCT, a LIMIT, a join, a union, a rename or a literal in there means it is **not** an identity, so it stays a subquery and refuses by name. Without this, essentially every real Metabase report refused.

**A derived table is only swapped for its table where a TABLE belongs — after FROM or JOIN (`_TABLE_POSITION`).** "This subquery returns exactly the rows of `` `tabX` ``" is a fact about a *row source*; parentheses elsewhere mean something else. Without that check, `` WHERE `name` = ( SELECT `name` FROM `tabChild` ) `` became `` WHERE `name` = `tabChild` `` and **converted cleanly** into a filter comparing a column against the literal text `` `tabChild` `` — a report that returns no rows and says nothing. Every check downstream was happy, because by then the subquery was gone. Found by `scripts/subquery_shapes.py` on its own smoke test.

**Metabase wraps an AGGREGATING question's joins too, and that wrapper is lifted rather than unwrapped.** When a question aggregates over joined tables the joins become a derived table and the aggregate runs outside it, over columns the wrapper has *renamed* (`` `Child_3c522490`.`metric` AS `Child_a3e4a16b` ``). That is not a passthrough, so `unwrap_derived_tables` correctly leaves it alone — but it is still removable for a different and equally provable reason: it neither filters nor aggregates, so it returns the same *rows* as the query inside it, and a rename is a bijection on columns. `lift_renaming_wrapper` maps the outer references back through the wrapper's own `X AS Y` list and folds it into one flat statement. `dashboard_studio/tests/fixtures/quality_performance_outcomes.sql` is the real capture. Not lifted: an outer WHERE, a wrapper that groups/aggregates/limits, an item that is not a rename, an outer reference the wrapper does not define, and — a narrow one — grouping by an alias defined as `col * 1`, since `'abc' * 1` is 0 in MySQL and the types are not known at that point.

**Metabase also compiles the same question the other way up, and that wrapper is DROPPED — a third rule, not a variation of the second.** When the compiled query is already complete, it still gets wrapped and its output columns re-selected by name (`` `__mb_source`.`avg` AS `avg` ``). `lift_renaming_wrapper` cannot touch it: the inner GROUP BY stops it, correctly, since there is no aggregate out here to fold down. `drop_passthrough_wrapper` removes it on its own proof — the outer has no clause of its own at all, renames nothing, and its column set equals the set the inner produces, so it returns exactly the inner's rows and exactly its columns. The three rules cannot fire on each other's shapes: unwrap_ needs the source to be `` `tabX` ``, lift_ needs an outer that aggregates, drop_ needs an outer that does nothing. `dashboard_studio/tests/fixtures/aggregated_then_reselected.sql` is the reported capture. Kept as a subquery: any outer clause (a WHERE, GROUP BY, ORDER BY or LIMIT), a rename, a narrowing projection, an item qualified by something other than the wrapper, and an inner item whose output name cannot be read (`COUNT(*)` with no `AS` — the name is the database's to choose, not ours to guess).

The rewrite is textual and deliberately does **not** require the inner to convert. Removing the wrapper is provable on its own, so a query whose inner half is unsupported now refuses naming that half, instead of naming `__mb_source` — an identifier nobody typed.

**Nothing strips SQL comments.** A comment line inside the outer SELECT list lands in an item and stops the wrapper being read, and a comment containing a clause name is read as that clause (`unparsed WHERE condition: , --`). It **refuses** rather than converting wrongly, so this is recorded and not fixed: Metabase's compiled SQL carries no comments. `aggregated_then_reselected.sql` therefore has no comment header, unlike its siblings — `TestACommentIsNotStripped` pins both halves.

**`col * 1` on a TEXT column emits a real `cast` OPERATION, and the two failed attempts before it are worth reading — ADR-009 and its amendments.** Metabase writes `* 1` to cast before aggregating; at UCC it does that to `actual_value`, a Frappe **Data** field. ADR-009 first delivered that by setting the measure's `data_type` to Decimal — which describes the *result* of the aggregate and converts nothing, so Insights' engine reached the text column and died on `'StringColumn' object has no attribute 'mean'`. **A type or a flag on the measure cannot do this.** The conversion is its own operation, read from `query.types.ts` at v3.12.2: `Cast = { type: 'cast' } & CastArgs`, `CastArgs = { column: Column; data_type: ColumnDataType }` — exactly two keys, and it is asserted in full because an unrecognised key is dropped silently and would fail identically while looking fixed. It is emitted **after the filters and immediately before the `summarize`**, where `* 1` sat in the SQL: scoped to the aggregate, not the WHERE. `COUNT(col * 1)` emits no cast — counting text is fine and converting first changes what is counted. Fixture-tested end to end over the real report; running it in Insights is the user's step. The real fix is still retyping the Frappe field to Float or Currency, which also makes the non-numeric rows visible instead of silently zero.

**Arithmetic over aggregates is translated into a `summarize` + a `mutate` — ADR-011.** `( AVG(a) + AVG(b) ) / 2` becomes two measures and `{"type": "mutate", "new_name": …, "data_type": "Auto", "expression": {"type": "expression", "expression": "( avg_of_a + avg_of_b ) / 2"}}`, read out of a hand-built query's own Operations JSON at v3.12.2. The expression is **plain text referencing the `measure_name`s the preceding summarize defines**, which is the whole reason this is translatable. The slots are filled from the measures that were actually emitted, never from a name rebuilt alongside them. What may appear in that string is an **allowlist** — `+ - * / ( )`, numbers, whitespace — because it is text a query engine will evaluate: `CAST`, `YEAR`, `CONCAT`, a bare column and a string literal all refuse naming the token that stopped them. **CAST is refused on purpose and the refusal says the `cast` operation is not the answer**: `CastArgs` converts a named *column*, and `CAST(<expression> AS double)` converts a result that is never a column. Dropping it was rejected — probably-the-same-number is what this project refuses to ship. **A wrapper that COMPUTES becomes operations before the summarize — ADR-012.** `CONCAT('', YEAR(d)) AS Year` becomes a `mutate` `Year = year(d)` and `CAST(v AS double) AS v` becomes a `cast`, both emitted BEFORE the `summarize` that groups by and aggregates over them. Three facts off the live site made it possible, none of them guessed: Insights stores an **Integer dimension** (query `s39rc7j648`), so `DIMENSION_DATA_TYPES` — a chart-renderer rule that had been gating queries — is **deleted**; the expression language has functions and `year` is **lowercase**, seen in a stored expression; and the stored operation order on that query is `source -> mutate -> summarize`, read from the record rather than the UI's list. The allowlist widened to **exactly `year`** — `MONTH`/`DAY`/`QUARTER` refuse by name, because the vocabulary widens only to what has been observed. `CONCAT('', x)` is dropped (it only made the year a text label, and a numeric grouping is fine) but `CONCAT('FY', x)` refuses, since that prefix is part of the label. A `CAST` that also renames refuses: `CastArgs` converts a column in place with nowhere to put a new name. A join carries the column the computation READS, never the alias it produces.

**A scale factor `col * 5` is a mutate, and it needed no new evidence — ADR-013.** Arithmetic in a mutate expression was the FIRST captured expression, and mutate-before-summarize came from ADR-012, so this was only the wrapper reader learning one more shape. It is **not** ADR-009's `* 1`: `* 1` leaves every value alone and forces a type, `* 5` changes them. The parser emits `data_type: None` — it has no types — and the translator types it from the column it reads, **refusing when that column is text**, since `'abc' * 5` is 0 in MySQL. One column with numeric literals only; `a * b` refuses by name. Report 1680, the original flagship, now refuses naming the OUTER `CAST(<expression> AS double)` instead of "subquery" — that half is ADR-011 and unchanged.

**`_AGGREGATE_ITEM` matches ONE aggregate call and nothing else.** `.*` between the parentheses matched `SUM(a) * 100 / COUNT(*)` — it starts with an aggregate name and ends with a bracket — so a whole expression read as a plain aggregate and its arithmetic was skipped in silence.

**A GROUP BY item that is not exactly one column REFUSES.** `_QUALIFIED` is anchored, so `` `c`.`actual_value` * 1 `` matched nothing and the item was **skipped in silence** — turning a grouping by a coerced value (0 for every row that is not a number) into a grouping by the raw column, a different question answered without a word. Same class as the dropped computed column and the dropped LIMIT.

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

# Where is the effort worth spending? Every exported report's SQL, refusals
# grouped by reason. Creates nothing. Deeper on a site (see below).
python scripts/bulk_dry_run.py path/to/exported_sql/
```

Do not lint `archive/`, `reference/` or `prototypes/`. The first is dead code by definition; the others are Frappe Server Scripts and UX references where `frappe` is an injected global (ruff reports hundreds of false `F821`).

**`scripts/bulk_dry_run.py` answers "what should we fix first" and is the one diagnostic that also runs here.** Point it at a directory of exported `.sql` files, one per report; it runs each through `analyze_sql` (+ `operations_from_sql` on a site), creates nothing, and prints refusals **grouped by reason** with example report names. Two numbers per group: how many reports it blocks, and how many it is the *sole* blocker for — the second is the one to steer by, since a blocker that stops 40 reports but is never the only one unblocks nothing on its own. A refusal message it does not recognise is printed **verbatim under "matched no group"**, never filed under the nearest match; add new messages to the `groups` table in the script. Off a Bench it says "no SHAPE blocker" rather than "converts cleanly" and names what it could not check — the operator, type and column checks all need a site, so a shape-only pass overcounts, and the overcount looks like good news.

**Both bulk scripts take their directory from `$DASHBOARD_STUDIO_SQL_DIR` under `bench console`, and from argv ONLY when run as a script.** Setting a `directory` variable before `exec()` cannot work — the function declares its own and shadows it — and scanning argv for "anything that is a directory" read `grc` out of `bench --site grc console` and reported confidently on the two files in that site folder. Twice. Every run prints the resolved path and which source it came from.

**`scripts/subquery_shapes.py` drills into one dry-run group.** When one blocker stops hundreds of reports, it groups those reports by the *shape* of the wrapper the three rules left behind — the outer clauses, the kind of each outer SELECT item, what the inner query does, how deep the nesting goes — so the next rule is written against a counted shape rather than whichever capture arrived first. It reports **features, not verdicts**: a big group says where to look, never that a rule is available, since removability needs its own proof. It also splits the CASE reports by what they are BUILT from — branch count, long string literals (hardcoded question wording), null logic (COALESCE/NULLIF/IS NULL) — because a composite index and a `CASE WHEN answer = 'yes'` share one refusal message and are two different problems; see ADR-014. `IN (…)`/`EXISTS`/scalar nesting is reported separately as "no FROM-subquery" — a different problem wearing the same refusal, and filing it with the wrappers would inflate the group that looks fixable. It also counts the **vocabulary of the outer SELECT** — the part no wrapper rule can remove, because it must be translated rather than dropped — and how many reports use nothing but arithmetic over aggregates, which is the question "would one expression capability clear this group". Frappe-free, runs anywhere.

**`scripts/metabase_export_sql.py` fills the folder the dry run reads.** One `.sql` per card, named `<card name>--<id>.sql` so a refusal leads back to the card; native cards verbatim, GUI-built cards compiled by Metabase (ADR-010). Archived cards skipped, template-tag cards counted so their refusals are expected, a 403 listed as a permission fact rather than failing the run. Live-site only, and `card_limit` is there so the first run can be five cards rather than 200.

`scripts/insights_schema_check.py`, `scripts/metabase_table_inventory.py`, `scripts/numeric_fields_typed_as_text.py` and `scripts/insights_operations_probe.py` are **read-only diagnostics that only run on the live site** — hand them to the user, don't try to run them here. The first compares Insights' own idea of a table's columns against the database's; the second reports which physical tables the Metabase cards read, for narrowing a database GRANT, and withholds its suggested GRANT block whenever anything is unresolved; the fourth reads what Insights has actually STORED to settle two questions the source cannot answer from here — the dimension data_types it accepts, and every `mutate` expression it holds, printed whole with its functions tallied — and reports finding none as **"no evidence either way", never as a no**, because removing a refusal on absence of evidence is the guess this project keeps paying for; the third sizes the `actual_value` problem across every DocType before anyone retypes a field, and **judges a field by the values it holds, never by its name** — `reference_no` is full of digits and holds no numbers, and `actual_value` is on no name list anyone would write. It separates wholly-numeric fields (retype cleanly) from mostly-numeric ones, which are the ones that matter: retyping those does not create the bad rows, it makes rows that silently coerce to 0 today visible.

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

**N aggregates are N measures in ONE summarize, and `Rating`/`Duration` are numbers.** Two blockers from the on-site scan, both this converter's own doing rather than anything Insights required. `summarize.measures` is a list — ADR-011's expression path already fills it with two — so "only one aggregate is translated" was a cap left over from the single-metric era, **and it had no test at all**, which is how it survived. Separately, Frappe stores a `Rating` as a fraction and a `Duration` as a count of seconds; both were missing from `FIELDTYPE_TO_DATA_TYPE`, fell through to String, and made `AVG(rating)` refuse as "only a number can be AVG'd" over a column that is one. Anything still unlisted stays String on purpose — that degrades to a refusal, never to a wrong chart.

**`DIMENSION_DATA_TYPES` is a CHART-RENDERER rule being applied to a QUERY, and that is unresolved.** Its own recorded provenance, in `archive/api_insights_sql_path.py`, says *"these are not our rules, they are the ones the chart renderer applies"* — it picked a chart's x-axis there. Here it gates `summarize.dimensions`, which is a different thing, and it is why grouping by an Integer refuses. Do **not** widen it on that suspicion: `query.types.ts` is not in this repo, and shipping on a guess is what ADR-009's first delivery did. `scripts/insights_operations_probe.py` settles it from records Insights itself wrote.

**Flag-don't-guess, harder than anywhere else.** Everything off the rule table refuses **by name and hands back no operations** — a partial operation list is a query that answers a different question. Refused: subqueries that are not provable passthroughs, more than one join, CROSS and self joins, an ON clause that is anything but a single equality of two qualified columns, an unqualified column that exists in both joined tables, a computed column in the SELECT list, a row limit, OR, UNION, HAVING, CASE, DISTINCT, window functions, more than one aggregate, LIKE and IN.

Two of those exist because the SELECT list and the LIMIT used to be read and then **silently dropped**: a computed column vanished, so the converted query answered a smaller question, and a `LIMIT 10` became "all of them". The one exception is `LIMIT 1048575`, the row cap Metabase appends to everything it compiles — an exact match on the constant observed in `reference/`, not a threshold, and any other value refuses.

Expected operations are asserted **in full** in the tests, not spot-checked: the failure mode here is a query that runs fine and answers something else, so "the right keys are present" proves nothing.

**A WHERE or GROUP BY stops at the `)` that closes the subquery it lives in.** Both are found by scanning forward to the next keyword, which runs straight past the end of a Metabase wrapper: a perfectly ordinary `` `tabX`.`name` = 'literal' `` came back as `` … = 'literal' ) AS `__mb_source` `` and refused as unparsed. Conditions are whitespace-normalised for the same class of reason — `_CONDITION`'s value is `.+?` with no DOTALL, so one wrapped across two lines matched nothing.

**A refusal is only useful if its reasons are the real ones.** Qualifiers that resolve to nothing are collected apart and dropped when a subquery survived — inside a wrapper that could not be flattened, every alias is unknown by construction, and `'__mb_source' is not a table or alias` three times buries the line that says what is actually wrong under an identifier nobody typed. Reasons are de-duplicated for the same reason: one fault found in the WHERE, the GROUP BY and the aggregate is one fault.

### Insights plumbing (`api/insights.py`)

What the converter needs and no more: the v3 DocType names, `clamp_title`, `_require_insights`, workbook resolution and `list_insights_workbooks`. The SQL-paste path that used to live here is in `archive/api_insights_sql_path.py`.

**Insights v3 only, and the version guard is subtle.** The v2 DocTypes still ship alongside v3, so `exists("DocType", "Insights Query")` is True on a v3 site — the original guard passed and wrote an orphan nothing could open. Guard on `Insights Query v3`. Same fault twice: the Site DB check must read `Insights Data Source v3`, not the v2 table that happens to hold a row of the same name.

`title` is a Frappe `Data` field — varchar(140) — and Frappe **aborts the insert** rather than trimming. `clamp_title` runs on the resolved name, so a caller-supplied title is clamped too.

### The app calls Metabase nowhere; two hand-run scripts do

The read-only HTTP client went to `archive/metabase_client_card_path.py` with the card path, and nothing in `dashboard_studio/` makes an HTTP call at all. `scripts/metabase_table_inventory.py` (GET only) and `scripts/metabase_export_sql.py` are the only things that reach Metabase, both hand-run on the live site.

**`POST /api/card/:id/query` and `POST /api/dataset` execute SQL against the connected production database and must never be added.** `POST /api/dataset/native` compiles MBQL to SQL *without* executing, and it is now used — by `metabase_export_sql.py` and nowhere else, which is what ADR-006 named as the route for a GUI-built card (*"or `POST /api/dataset/native` if that permission is ever granted"*) and what ADR-010 records. The two dangerous endpoints are one word from the safe one, so the protection is structural rather than careful: one `requests.post` in the file, its path checked at the call site, and a test that greps the source for the executing spellings and asserts the recorded calls. Reuse that shape or don't add the call.

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

- Nothing in the app talks to Metabase at all. Two hand-run scripts do: `scripts/metabase_table_inventory.py` (GET only) and `scripts/metabase_export_sql.py` (GET, plus `POST /api/dataset/native`, which compiles and does not execute — ADR-010). Neither writes anything to Metabase.
- **The Metabase key lives in `site_config.json`** (`metabase_url`, `metabase_api_key`) — per-site, outside this repo. Only those two scripts read it, server-side. Never return it to the browser, never log it, never echo it in a refusal — including the 401 path, where "helpful" context puts it into `_server_messages` and into a user's browser. If a Metabase call is ever added back to the app, that rule comes with it.
- **A key's group is a requirement someone has to meet, not a fact you can assert.** Metabase has no read-only key flag; only the group restricts it. A key in Administrators — or any group with `create-queries: query-builder-and-native` — is unrestricted on the Metabase side, making our GET-only client the *only* protection. Metabase's permission UI has been observed **not** to gate `/api/dataset/native` on this instance, so the durable control is a SELECT-only database login.
- `fixtures/role.json` creates `Dashboard Studio Editor` — every `frappe.only_for` depends on it. Don't remove it.
- No personal student data in fixtures or tests.
