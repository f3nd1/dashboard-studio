# Where the test fakes are looser than Frappe

Report only. **Nothing fixed, no fake changed.** Every entry names what the fake
does, what a real site does, and a concrete case where the suite is green and
`ucc.local` is not.

Prompted by the third harness-hides-a-fault incident (`reqd`, the `["in", …]`
operator, the mock-versus-live metric cache). It is a pattern, and this is the
list.

---

## The pattern first

There are **seven separate fake `frappe` modules** — `test_section_api`
(reused by `test_chart_api`), `test_governance_api`, `test_validation_api`,
`test_migration_api`, `test_migration_sql_api`, `test_catalogue_api`,
`test_api_permissions`, `test_deploy_check`. Each was written for the endpoints
in its own file and models exactly what those endpoints happened to need.

That produces two failure modes, and both have now bitten:

1. **A fake accepts what Frappe rejects** (`reqd`) — the endpoint is wrong and
   the test says it is fine.
2. **A fake returns nothing where Frappe returns rows** (`["in", …]`) — the
   endpoint is right and the test proves nothing, silently.

The second is worse. It fails *open*: the code path runs, produces an empty
result, and the assertions were written against that empty result.

**The most useful single fact in this document:** the `reqd` enforcement added
after the `create_chart` incident exists in **one fake out of seven**. It was
fixed where it bit, not where it applies. Finding #1 below is the live failure
that leaves behind.

---

## Ranked

Likelihood of being hit live × how bad it is when it is.

### 1. `insert()` does not enforce `reqd` in six of the seven fakes — and one live insert can legitimately supply an empty required field

Only `test_section_api._FakeDoc.insert` checks `reqd`. `test_validation_api` and
`test_migration_api` define `insert = _persist` with no check at all.

`DS Validation Row.group_label` is `reqd: 1`. `run_validation` builds child rows
via `_row_for_storage`, which sets `group_label: _as_text(row.get("label"))`, and
`_as_text(None)` returns `""`. Labels come from `comparison._index_rows`, which
does `indexed[str(label)] = …` — so a group whose dimension value is empty
produces the label `""`.

**Test passes, site fails:** run a validation on a metric whose grouping field is
blank on some rows — precisely the "unknown" case this project preserves rather
than coerces — and the live insert raises `MandatoryError` on `group_label`.
Every validation test passes today.

Also unenforced: `DS Data Mapping.data_source` / `external_table`,
`DS Migration Source Query.source_sql`.

### 2. `delete_doc` does not check for inbound links

Every fake's `delete_doc` is `store[doctype].pop(name)`. Frappe's runs
`check_if_doc_is_linked` and raises `LinkExistsError` unless `ignore_links` /
`force` is passed.

`delete_chart` (`studio.py:479`) deletes a `DS Chart`. `DS Validation Comparison`
carries a Link to `chart`.

**Test passes, site fails:** validate a chart, then delete it. `test_chart_api`'s
delete tests pass; live, Frappe refuses because a comparison points at it. This
is now *more* likely, not less — the publish gate we just built actively pushes
people to validate every chart before deleting anything.

`delete_section` (`:249`) is safe by construction: it clears `DS Chart.section`
first. That is the pattern the chart path does not have.

### 3. Select values are not validated on save, and only the client checks them

`_FakeDoc.save()` is a dict write. Frappe's `BaseDocument` validates Select
values against the field's options and raises on a value outside them.

`save_chart` (`:489`) writes `chart_type` and `sort_order` straight through —
`_EDITABLE_CHART_FIELDS` allows the *field*, nothing checks the *value*.
`create_chart` does check, via `_chart_type_options()`; `save_chart` does not.

`core.applyChartEdit` validates both client-side, and there is a test asserting
it rejects `"Random"`. **That is a client-side check standing in for a server-side
one.** A stale browser tab, or any direct call to the whitelisted endpoint, gets
past it.

**Test passes, site fails:** `save_chart(chart, {"chart_type": "Nonsense"})`.

### 4. Link targets are not validated

Same cause. Frappe checks that a Link's target row exists and raises
`LinkValidationError`.

`save_chart` writes `metric` and `section` unchecked.

**Test passes, site fails:** save a chart whose `metric` names a `DS Metric` that
was renamed or deleted — plausible, because `DS Metric` is `autoname:
field:metric_name`, so renaming a metric changes its primary key.

### 5. `autoname` and `unique` are not modelled

`_FakeDoc._persist` invents `f"{doctype}-{len(table)+1}"` when `name` is absent.
Four DS DocTypes use `autoname: field:<title>` with that field `unique: 1` —
`DS Dashboard`, `DS Data Source`, `DS Metric`, `DS Migration Project`.

Two consequences:

- **`doc.name` is wrong in every test.** `create_dashboard` returns `doc.name`;
  live that is the scrubbed title, in tests it is `DS Dashboard-1`. Anything
  asserting the shape of a name is asserting the fake.
- **Duplicate titles never raise.** Live, a second dashboard with an existing
  title raises `DuplicateEntryError`.

**Test passes, site fails:** create two dashboards called "Admission Intake".
`create_dashboard` has no duplicate handling and no test could have asked for one.

### 6. Nothing models DocType-level write permissions — and our two permission lists disagree

`frappe.get_all` is `get_list(ignore_permissions=True)`, so read paths genuinely
are unchecked live too; the fakes are right about reads. **Writes are different:**
`doc.save()`, `.insert()` and `frappe.delete_doc` all call `check_permission`
against the DocType's own permission rows. No fake does.

And the rows do not match the API gate. `DS_READ_ROLES` / `DS_WRITE_ROLES` treat
**System Manager** as superuser; **no DS DocType lists System Manager in its
`permissions` block** — all thirteen list only Editor / Viewer / QA Approver.
Only *Administrator* bypasses DocType permissions in Frappe, not System Manager.

**Test passes, site probably fails:** log in as a user with System Manager but
none of the three DS roles, and save a chart. `frappe.only_for` passes; the write
should then be refused.

**Flagged as unverified.** This is the one item here I cannot settle from source
alone, and it is cheap to check on the live site — it needs a non-Administrator
System Manager account, which is also why it would not show in testing so far.

### 7. `fields=[…]` is ignored by every fake

All seven return whole rows. Frappe returns only the requested keys.

Nothing is broken today — every endpoint reads only what it asked for, and I
checked all twenty `get_all` calls. But there is **no guard**: add a use of
`chart.sort_order` inside `publish_readiness` without adding it to that call's
`fields`, and every test passes while the live value is `None`.

Silent, and of the fail-open kind.

### 8. `order_by` is ignored by every fake

Five orderings are asserted by no test:

| Call | Order | What depends on it |
|---|---|---|
| `studio.py:115` | `pos_y asc, pos_x asc` | the order charts are drawn in |
| `studio.py:123` | `idx asc` | filter row order within a chart |
| `validation.py:128` | `comparison_date desc` | "newest first" in the Validation table |
| `governance.py:290` | `creation desc` | version history order |
| `catalogue.py:66` | `modified desc` + `limit 3` | which three records show as "recent" |

Tests see dict-insertion order and pass. `_next_free_row` is order-independent,
so chart *placement* is safe.

### 9. `limit` is ignored by two fakes that receive it

`test_validation_api`'s `get_all` accepts `limit` and never applies it;
`test_section_api`'s absorbs it into `**kwargs`. `test_governance_api`'s honours it.

`list_comparisons` passes `limit=100`. **Test passes, site truncates:** a chart
with more than 100 comparisons shows a silently short list, and there is no test
that could notice.

### 10. `["in", […]]` is still unsupported in five of the seven fakes

Fixed in `test_governance_api` this week. Still equality-only in
`test_section_api` (and therefore `test_chart_api`), `test_validation_api`,
`test_catalogue_api`, `test_migration_sql_api`. `test_migration_api` has a
`_matches` helper that handles it — **wired into `db.get_value` only, not into
its own `get_all`.**

A list filter compared with `==` never matches, so the call returns `[]`.

**Currently latent** because of #11, which hides it.

### 11. Child tables are nested inside the parent dict, never separate tables

Every fixture stores `chart_filters` / `canvas_nodes` / `comparison_rows` as a
list on the parent. Live they are rows in their own DocType with a `parent`
column.

So `get_studio_dashboard`'s child-attach block (`studio.py:118-129`) — the
`["in", …]` filter, the `row.pop("parent")`, the `by_parent` grouping — **runs
against an empty result in every test**. `test_api_permissions` returns `[]` for
`DS Chart Filter` explicitly; the others have no such table at all.

That block has never been executed with data. Combined with #10 it is the exact
shape of the bug we just fixed, one layer down.

### 12. No field-length limit

Frappe `Data` is `varchar(140)` and raises `CharacterLengthExceededError`.

`create_chart` names a duplicate `f"{source.chart_title} (copy)"`. Duplicate a
duplicate about twenty times and the title crosses 140.

Low likelihood, trivial damage, listed for completeness.

### 13. Types are not coerced

Frappe casts `Check` to `0`/`1` and `Int` through `cint`. The fakes store
whatever Python object they are handed.

A test asserting `drill_down_enabled is True` is asserting the fake; live it is
`1`. A float `pos_x` from drag arithmetic stores as `4.5` in tests and truncates
live.

### 14. A missing record raises the wrong exception

Fakes raise `KeyError`; Frappe raises `DoesNotExistError` (→ HTTP 404). Any test
asserting the failure mode for a missing record is asserting the fake's shape.

This is the one that produced the live 404 loop earlier this month, from the
other direction.

---

## What the fakes model honestly

Worth stating, so the list above is not read as "the harness is worthless":

- **`frappe.only_for`** matches the real role-intersection semantics.
- **`get_meta` reads the real shipped DocType JSON** in `test_section_api` and
  `test_deploy_check`, so Select options and field types cannot drift from
  schema. That is why `create_chart`'s type check is genuinely tested.
- **`_doctype_fields` reads from disk**, so a `reqd` flag added to a JSON starts
  being enforced with no test change — where the check exists at all (#1).
- **`test_migration_api._matches` models SQL `NULL != ''` deliberately**, with a
  comment saying why. That is the standard the others are being measured against.
- **`test_deploy_check` models the site separately from the shipped JSON**, which
  is the only way its drift cases mean anything.
- **`frappe.get_all` bypassing permissions** is correct behaviour, not a gap.

---

## What I would close, if it were my call

**Close (cheap, and each has a live failure behind it):** #1, #2, #3, #4.
Numbers 1 and 2 are live failures waiting on ordinary use; 3 and 4 are a
server-side validation gap that a client-side check is currently covering for,
which is not a boundary.

**Close by consolidation rather than one at a time:** #7, #8, #9, #10, #11.
These are all "the fake does less than the query says", and fixing them
individually across seven files is how #10 ended up fixed in one place. One
shared fake with `fields` / `order_by` / `limit` / operator support, imported the
way `test_chart_api` already imports `test_section_api`'s, closes all five —
and would have closed #10 in every file the first time.

**Leave:** #12, #13, #14 — real, but low value against the cost of modelling
Frappe's type system in a mock.

**Check live, do not build for:** #6. Needs a non-Administrator System Manager
login to settle, and the answer decides whether it is a schema fix or nothing.

---

## The structural note

This is the same shape as `docs/SOPHIA_FAULT_PATTERN.md`, one level up: **seven
implementations of "what Frappe does", each written to satisfy its own caller,
agreeing with each other and with Frappe only by coincidence.** The three
incidents were not three bad-luck events; they were three samples from that
distribution.

The difference is that here the divergence is cheap to remove — one fake, seven
importers — where on the Sophia side it needs a change to how charts are
declared.
