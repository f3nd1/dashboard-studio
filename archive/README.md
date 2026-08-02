# Archive — not part of the app

Everything here was live code until the scope cut to the Metabase → Insights
converter. It is kept because it worked, not because anything calls it.

**Nothing in here is imported, tested, linted or shipped.** `ruff` and the test
runner are both pointed at `dashboard_studio/` and `scripts/` only. Do not fix
things in here; if something is needed again, move it back and give it tests.

| Path | Was |
|---|---|
| `analytics/` | the DS Metric query engine — plan builder, validators, comparison |
| `api_*.py` | the endpoints for the five archived workspaces |
| `api_insights_sql_path.py` | the SQL-paste path — create_insights_query, apply_insights_chart, the SELECT-only guard, the axis picker |
| `api_studio.py` | the main endpoint module; its two role tuples now live in `dashboard_studio/roles.py` |
| `doctype/` | all 17 DocTypes. Records made by them are still in the database; the definitions just no longer ship |
| `studio_app_full.js` | the six-workspace SPA. The converter's own code was lifted out of it unchanged |
| `studio_core_full.js` | grid maths, chart-type rules, filter validation, mapping nodes |
| `studio_charts.js`, `studio_mock.js` | hand-built SVG charts and the mock dataset, both for the builder |
| `tests/` | the tests for all of the above |
| `scripts/insights_v3_probe.py` | the v3 schema probe; its work is done |
| `docs/` | design records for the archived surfaces |
| `metabase_mbql_card_path.py` | the MBQL 5 → operations translator (`translate_card`), from when a Metabase **card id** was a way in. Its Insights-side shapes and constants — `_source`, `_filter`, `_join`, `_summarize`, the operator and aggregation tables — were moved into `integrations/metabase/sql_ops.py`, which is now the only translator |
| `metabase_client_card_path.py` | the read-only Metabase HTTP client. Nothing in the app calls Metabase any more; `scripts/metabase_table_inventory.py` does its own GETs |
| `test_mbql_translation.py` | the tests for `translate_card` |

## What was deliberately NOT archived

- `dashboard_studio/fixtures/role.json` — creates `Dashboard Studio Editor`,
  which every `frappe.only_for` in the converter checks against. Archiving it
  would have made the converter refuse everybody on a fresh site.
- `integrations/metabase/parser.py` + `mapper.py` — the SQL parser IS the
  converter's front half now: it reads the source table, the WHERE, the GROUP BY
  and the join out of pasted text.
- `integrations/metabase/card.py` — nothing in the app calls it, but
  `scripts/metabase_table_inventory.py` imports `referenced_tables` to work out
  which physical tables the Metabase cards read, for narrowing a database GRANT.
  It is Frappe-free and imports only `parser.TABLE_PATTERN`.
