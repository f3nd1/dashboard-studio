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

## What was deliberately NOT archived

- `dashboard_studio/fixtures/role.json` — creates `Dashboard Studio Editor`,
  which every `frappe.only_for` in the converter checks against. Archiving it
  would have made the converter refuse everybody on a fresh site.
- `integrations/metabase/parser.py` + `mapper.py` — `card.py` imports
  `TABLE_PATTERN` from the parser, so the SQL parser is still load-bearing for
  reading a card's tables even though the SQL *path* is gone.
