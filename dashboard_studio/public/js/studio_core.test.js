/*
 * Node self-check for studio_core.js — run: node studio_core.test.js
 */
"use strict";
var assert = require("assert");
var core = require("./studio_core.js");

// describeOperation: the converted operations, readable enough that somebody
// can spot a wrong translation BEFORE running it.
assert.strictEqual(core.describeOperation(
  { type: "source", table: { table_name: "tabStudent Applicant" } }),
  "tabStudent Applicant");
assert.strictEqual(core.describeOperation(
  { type: "filter", column: { column_name: "status" }, operator: "=", value: "Enrolled" }),
  'status = "Enrolled"');
assert.strictEqual(core.describeOperation({ type: "join", join_type: "left",
  table: { table_name: "tabPurchase Order" },
  join_condition: { left_column: { column_name: "po_ref" },
                    right_column: { column_name: "po_name" } } }),
  "left join tabPurchase Order on po_ref = po_name");
assert.strictEqual(core.describeOperation({ type: "summarize",
  measures: [{ aggregation: "count", column_name: "count" }],
  dimensions: [{ column_name: "intake_year" }] }),
  "count(count) by intake_year");
assert.strictEqual(core.describeOperation({ type: "summarize",
  measures: [{ aggregation: "sum", column_name: "fee" }], dimensions: [] }),
  "sum(fee)");
// A cast is its own operation now, and has to read as one.
assert.strictEqual(core.describeOperation(
  { type: "cast", column: { column_name: "actual_value" }, data_type: "Decimal" }),
  "cast actual_value to Decimal");
// And the measure says WHY the cast is there: nothing else in the converted
// query shows the source field is text, and non-numeric rows become 0.
assert.strictEqual(core.describeOperation({ type: "summarize",
  measures: [{ aggregation: "avg", column_name: "actual_value",
               coerced_from: "String" }],
  dimensions: [{ column_name: "metric" }] }),
  "avg(actual_value) — String cast to a number by metric");

// A computed column reads back as the maths it is.
assert.strictEqual(core.describeOperation({ type: "mutate", new_name: "Actual No",
  data_type: "Auto",
  expression: { type: "expression", expression: "(avg_of_q1 + avg_of_q5) / 2" } }),
  "Actual No = (avg_of_q1 + avg_of_q5) / 2");

// Junk must not throw — this renders inside a panel that is already reporting
// something the person needs to read.
assert.strictEqual(core.describeOperation(null), "");
assert.strictEqual(core.describeOperation({ type: "filter" }), '? ? undefined');

// refusalMessage: the server's own sentence has to reach the user.
//
// Frappe puts a thrown message in different places depending on the site's
// settings and API version (response.py sets _server_messages only if
// message_log, and exc only if is_traceback_allowed). Reading two of them is
// how "aggregation '*' is a compound or custom expression" reached a user as
// "Could not convert that card." — every shape below is one that has to work.
var REAL = "This card cannot be converted: aggregation '*' is a compound or " +
  "custom expression, not a simple aggregate. Its SQL can still be copied " +
  "across by hand.";

// 1. The shape seen in the live console: the `exception` field.
assert.strictEqual(
  core.refusalMessage({ exception: "frappe.exceptions.ValidationError: " + REAL }, "GENERIC"),
  REAL, "the exception field was ignored — this is the reported bug");
// ...and nested in responseJSON, which is where a REJECTED call puts it.
assert.strictEqual(
  core.refusalMessage({ responseJSON: { exception: "frappe.exceptions.ValidationError: " + REAL } },
    "GENERIC"), REAL);

// 2. _server_messages: a JSON array of JSON-encoded dicts.
assert.strictEqual(core.refusalMessage(
  { _server_messages: JSON.stringify([JSON.stringify({ message: REAL })]) }, "GENERIC"), REAL);
assert.strictEqual(core.refusalMessage(
  { responseJSON: { _server_messages: JSON.stringify([JSON.stringify({ message: REAL })]) } },
  "GENERIC"), REAL);

// 3. exc: a JSON array of tracebacks. The last line carries the message.
assert.strictEqual(core.refusalMessage({ exc: JSON.stringify([
  'Traceback (most recent call last):\n  File "x.py", line 1\n' +
  "frappe.exceptions.ValidationError: " + REAL]) }, "GENERIC"), REAL);

// 4. API v2: {errors: [{type, exception}]}
assert.strictEqual(core.refusalMessage(
  { responseJSON: { errors: [{ type: "ValidationError", exception: REAL }] } },
  "GENERIC"), REAL);

// 5. _error_message.
assert.strictEqual(core.refusalMessage({ _error_message: REAL }, "GENERIC"), REAL);

// 6. A plain Error message still wins — it is the most direct.
assert.strictEqual(core.refusalMessage(new Error(REAL), "GENERIC"), REAL);

// HTML is stripped; Frappe wraps some messages in tags.
assert.strictEqual(core.refusalMessage(
  { _server_messages: JSON.stringify([JSON.stringify({ message: "<b>" + REAL + "</b>" })]) },
  "GENERIC"), REAL);

// The class prefix is noise to a reader and must not survive.
assert.ok(!/ValidationError/.test(core.refusalMessage(
  { exception: "frappe.exceptions.ValidationError: " + REAL }, "GENERIC")));

// The fallback is ONLY for a payload that genuinely carries no sentence.
assert.strictEqual(core.refusalMessage({}, "GENERIC"), "GENERIC");
assert.strictEqual(core.refusalMessage(null, "GENERIC"), "GENERIC");
assert.strictEqual(core.refusalMessage({ _server_messages: "[]" }, "GENERIC"), "GENERIC");
assert.strictEqual(core.refusalMessage({ exc_type: "" }, "GENERIC"), "GENERIC");
// A bare class name is not a sentence, but it beats nothing.
assert.strictEqual(core.refusalMessage({ message: "ValidationError" }, "GENERIC"),
  "ValidationError");

console.log("studio_core.test.js — all assertions passed");

// ---------------------------------------------------------------------------
// The proposal read-back.
//
// This is the question box's whole safety argument: the sentence a person reads
// to decide whether the proposal understood them is composed HERE, from the
// operations that will run, and never by the model. So these assertions are
// about faithfulness, not phrasing.
// ---------------------------------------------------------------------------
var PROPOSAL = [
  { type: "source", table: { table_name: "tabSales Invoice" } },
  { type: "mutate", new_name: "Year",
    expression: { expression: "year(posting_date)" } },
  { type: "filter", column: { column_name: "docstatus" }, operator: "=", value: 1 },
  { type: "summarize",
    measures: [{ measure_name: "sum_of_sales_income", column_name: "sales_income",
      aggregation: "sum", data_type: "Decimal" }],
    dimensions: [{ dimension_name: "agent_name", column_name: "agent_name",
      data_type: "String" },
    { dimension_name: "Year", column_name: "Year", data_type: "Integer" }] },
  { type: "order_by", column: { column_name: "sum_of_sales_income" },
    direction: "desc" },
];

var line = core.describeProposal(PROPOSAL);
// Every part of the sentence comes from an operation, so a proposal that
// aggregates the wrong column says so in the line somebody reads.
assert.ok(line.indexOf("sum of sales_income") !== -1, line);
assert.ok(line.indexOf("for each agent_name and Year") !== -1, line);
assert.ok(line.indexOf("from tabSales Invoice") !== -1, line);
assert.ok(line.indexOf("where docstatus = 1") !== -1, line);
assert.ok(line.indexOf("highest sum_of_sales_income first") !== -1, line);

// Change which column is aggregated and the sentence changes with it. This is
// the property that makes reading it a real check.
var swapped = JSON.parse(JSON.stringify(PROPOSAL));
swapped[3].measures[0].column_name = "commission_amount";
assert.ok(core.describeProposal(swapped).indexOf("commission_amount") !== -1,
  "the read-back must follow the operations");
assert.notStrictEqual(core.describeProposal(swapped), line);

// Nothing to summarise means no sentence, rather than an invented one.
assert.strictEqual(core.describeProposal([{ type: "source", table: {} }]), "");
assert.strictEqual(core.describeProposal(null), "");

// The operations added since describeOperation was written must read back too —
// an operation rendering as its own type name is a step nobody can check.
assert.strictEqual(core.describeOperation(
  { type: "order_by", column: { column_name: "n" }, direction: "desc" }),
"n, highest first");
assert.strictEqual(core.describeOperation({ type: "limit", limit: 10 }),
  "first 10 rows");
assert.strictEqual(core.describeOperation({ type: "filter_group",
  logical_operator: "Or",
  filters: [{ column: { column_name: "s" }, operator: "=", value: "A" },
    { column: { column_name: "s" }, operator: "=", value: "B" }] }),
's = "A" or s = "B"');
assert.strictEqual(core.labelForOperation({ type: "summarize" }), "Summarise");
assert.strictEqual(core.labelForOperation({ type: "order_by" }), "Sort");

console.log("studio_core.test.js — proposal read-back assertions passed");

// ---------------------------------------------------------------------------
// The unchartable-dimension disclosure (ADR-024).
//
// MONTH/QUARTER/DAY keep the numeric mutate on purpose: month-of-year pools
// every January and genuinely is not a date, so regrouping it to satisfy a
// chart would answer a different question. It IS unchartable though, and that
// is Insights' limit rather than a converter fault — so the read-back says so.
// ---------------------------------------------------------------------------
var monthly = core.describeOperation(
  { type: "mutate", new_name: "month_of_d", expression: { expression: "month(d)" } });
assert.ok(monthly.indexOf("cannot be a chart's X axis") !== -1, monthly);
assert.ok(monthly.indexOf("month_of_d = month(d)") !== -1, monthly);
["quarter(d)", "day(d)"].forEach(function (expression) {
  assert.ok(core.describeOperation({ type: "mutate", new_name: "x",
    expression: { expression: expression } }).indexOf("X axis") !== -1, expression);
});
// A YEAR grouping never appears as a mutate — it is a granularity — and any
// other mutate reads back plainly, with no warning attached.
["year(d)", "rating_1 * 5", "date_diff(a, b, 'day')", "(avg_of_a + avg_of_b) / 2"]
  .forEach(function (expression) {
    assert.strictEqual(core.describeOperation({ type: "mutate", new_name: "x",
      expression: { expression: expression } }), "x = " + expression);
  });

console.log("studio_core.test.js — unchartable-dimension disclosure asserted");

// ---------------------------------------------------------------------------
// The multiple-measure chart-display note (Part 3).
//
// The wording matters more than the trigger here. Metabase stores a per-series
// display type only when somebody overrode it, and a `display: "combo"` card
// computes the split from array position rather than saving it — so there is
// no reliable signal that a combo was intended. The note must therefore PROMPT
// a check and never announce a detection.
// ---------------------------------------------------------------------------
var summarize = function (measures) {
  return [{ type: "source", table: { table_name: "tabQuality Action" } },
          { type: "summarize", measures: measures, dimensions: [] }];
};
var COUNT = { measure_name: "count", column_name: "count",
              data_type: "Integer", aggregation: "count" };
var AVG = { measure_name: "avg_of_qipi", column_name: "qipi",
            data_type: "Decimal", aggregation: "avg" };

var note = core.chartDisplayNote(summarize([COUNT, AVG]));
assert.ok(note.indexOf("multiple measures") !== -1, note);
assert.ok(note.indexOf("bar+line combo chart") !== -1, note);
// It must NOT claim to have found one. "detected", "combo chart detected" and
// any assertion that Metabase said so are exactly what the data cannot support.
["detected", "Metabase", "combo chart is", "will be"].forEach(function (banned) {
  assert.strictEqual(note.indexOf(banned), -1,
    "the note claims more than it knows: " + banned);
});

// One measure is the ordinary case and says nothing — a note on every single
// conversion is a note nobody reads.
assert.strictEqual(core.chartDisplayNote(summarize([COUNT])), "");
assert.strictEqual(core.chartDisplayNote(summarize([])), "");
assert.strictEqual(core.chartDisplayNote([]), "");
assert.strictEqual(core.chartDisplayNote(undefined), "");
// No summarize at all — nothing to say.
assert.strictEqual(
  core.chartDisplayNote([{ type: "source", table: { table_name: "tabX" } }]), "");
// A non-numeric measure is not a chartable series, so it does not make a pair.
assert.strictEqual(core.chartDisplayNote(
  summarize([COUNT, { measure_name: "m", column_name: "c",
                      data_type: "String", aggregation: "max" }])), "");
// Three measures still fires.
assert.ok(core.chartDisplayNote(summarize([COUNT, AVG, AVG])) !== "");

console.log("studio_core.test.js — multiple-measure display note asserted");
// It reads the SUMMARIZE's measures, not any operation that happens to carry a
// `measures` key. No operation Insights emits today does, so this pins the
// intent rather than an observed shape — without it the check is a coincidence
// somebody could delete and see nothing fail.
assert.strictEqual(core.chartDisplayNote(
  [{ type: "source", table: { table_name: "tabX" }, measures: [COUNT, AVG] },
   { type: "summarize", measures: [COUNT], dimensions: [] }]), "");

console.log("studio_core.test.js — the note reads the summarize specifically");

// ---------------------------------------------------------------------------
// The month-of-year one-click regroup.
//
// The substitution is text, so the tests are mostly about what it must NOT
// touch. Rewriting a quoted literal would edit a filter value into one nobody
// typed — a query that converts, runs, and returns different rows.
// ---------------------------------------------------------------------------
var monthOps = [
  { type: "source", table: { table_name: "tabQuality Action" } },
  { type: "mutate", new_name: "month_of_d",
    expression: { expression: "month(d)" } },
  { type: "summarize", measures: [COUNT],
    dimensions: [{ dimension_name: "month_of_d", column_name: "month_of_d",
                   data_type: "Integer" }] },
];
assert.deepStrictEqual(core.datePartGrouping(monthOps),
  { part: "month", dimension: "month_of_d", column: "d", entangled: false });

// A YEAR grouping is a granularity on the date column and never a mutate, so
// it must never offer the fix — it is already what the fix produces.
assert.strictEqual(core.datePartGrouping([
  { type: "summarize", measures: [COUNT],
    dimensions: [{ dimension_name: "d", column_name: "d", data_type: "Date",
                   granularity: "year" }] }]), null);
// A mutate that is not grouped BY is not the chart's X axis.
assert.strictEqual(core.datePartGrouping([
  { type: "mutate", new_name: "month_of_d", expression: { expression: "month(d)" } },
  { type: "summarize", measures: [COUNT], dimensions: [] }]), null);
// Arithmetic mutates are untouched.
assert.strictEqual(core.datePartGrouping([
  { type: "mutate", new_name: "x", expression: { expression: "(a + b) / 2" } },
  { type: "summarize", measures: [COUNT],
    dimensions: [{ column_name: "x" }] }]), null);

// The substitution: all three places at once, which is where it always appears.
assert.strictEqual(
  core.regroupByYear("SELECT MONTH(`d`) AS `m` FROM `t` " +
                     "GROUP BY MONTH(`d`) ORDER BY MONTH(`d`) ASC", "month"),
  "SELECT YEAR(`d`) AS `m` FROM `t` GROUP BY YEAR(`d`) ORDER BY YEAR(`d`) ASC");
// A quoted literal is NOT rewritten — the one case that would be a silently
// different result rather than a visible failure.
assert.strictEqual(
  core.regroupByYear("SELECT MONTH(`d`) FROM `t` WHERE `label` = 'MONTH(x)'", "month"),
  "SELECT YEAR(`d`) FROM `t` WHERE `label` = 'MONTH(x)'");
assert.strictEqual(
  core.regroupByYear('SELECT MONTH(`d`) FROM `t` WHERE `l` = "MONTH(x)"', "month"),
  'SELECT YEAR(`d`) FROM `t` WHERE `l` = "MONTH(x)"');
// A backticked identifier that happens to be spelled MONTH is a column.
assert.strictEqual(core.regroupByYear("SELECT `MONTH(x)` FROM `t`", "month"),
                   "SELECT `MONTH(x)` FROM `t`");
// A word boundary before it: DAYCOUNT( and t.DAY( are other things entirely.
assert.strictEqual(core.regroupByYear("SELECT DAYCOUNT(a), DAY(`d`) FROM t", "day"),
                   "SELECT DAYCOUNT(a), YEAR(`d`) FROM t");
// Case and spacing as Metabase writes them.
assert.strictEqual(core.regroupByYear("select month (`d`) from t", "month"),
                   "select YEAR (`d`) from t");
// Only the detected part — a QUARTER query does not have its MONTHs rewritten.
assert.strictEqual(core.regroupByYear("SELECT QUARTER(`d`), MONTH(`e`) FROM t", "quarter"),
                   "SELECT YEAR(`d`), MONTH(`e`) FROM t");
// An escaped quote inside a literal does not end it.
assert.strictEqual(
  core.regroupByYear("SELECT MONTH(`d`) FROM t WHERE x = 'it''s MONTH(y)'", "month"),
  "SELECT YEAR(`d`) FROM t WHERE x = 'it''s MONTH(y)'");

console.log("studio_core.test.js — month-of-year regroup asserted");
// A QUALIFIED name is not a function call. `DAYCOUNT(` never matched anyway —
// the regex needs the bracket immediately after — so the word-boundary check
// is really about this shape, and that is what it has to be tested on.
assert.strictEqual(core.regroupByYear("SELECT t.DAY(`d`) FROM t", "day"),
                   "SELECT t.DAY(`d`) FROM t");
assert.strictEqual(core.regroupByYear("SELECT my_MONTH(`d`) FROM t", "month"),
                   "SELECT my_MONTH(`d`) FROM t");
// `year` must NEVER be offered as unchartable: regrouping year by year is a
// no-op, and the button would loop. Asserted on a synthetic mutate, because
// ADR-024 means a grouped YEAR does not produce one.
assert.strictEqual(core.datePartGrouping([
  { type: "mutate", new_name: "year_of_d", expression: { expression: "year(d)" } },
  { type: "summarize", measures: [COUNT],
    dimensions: [{ column_name: "year_of_d" }] }]), null);

console.log("studio_core.test.js — regroup boundary and year-exclusion asserted");

// ---------------------------------------------------------------------------
// Entanglement: a date part a LABEL expression also consumes.
//
// Found live: a month card's CASE (1 -> '01-Jan' ... 12 -> '12-Dec') had its
// MONTH( substituted along with the grouping, so the regrouped query compared
// 2024 against 1..12 and labelled every row NULL. No error, wrong everything.
// The one-click regroup must not be offered on such a card at all.
// ---------------------------------------------------------------------------
var monthLabelOps = [
  { type: "mutate", new_name: "Month Label",
    expression: { expression: "case(month(d) == 1, '01-Jan', month(d) == 2, '02-Feb')" } },
  { type: "mutate", new_name: "Month No", expression: { expression: "month(d)" } },
  { type: "summarize", measures: [COUNT],
    dimensions: [{ column_name: "Month No" }, { column_name: "Month Label" }] },
];
var found = core.datePartGrouping(monthLabelOps);
assert.strictEqual(found.part, "month");
assert.strictEqual(found.entangled, true, "the CASE consumes month( too");

// A plain month grouping is untangled — the button stays.
assert.strictEqual(core.datePartGrouping([
  { type: "mutate", new_name: "month_of_d", expression: { expression: "month(d)" } },
  { type: "summarize", measures: [COUNT],
    dimensions: [{ column_name: "month_of_d" }] }]).entangled, false);

// A SECOND pure mutate of the same part does not entangle: both substitute to
// year cleanly. (It collides in the promotion instead, which refuses there.)
assert.strictEqual(core.datePartGrouping([
  { type: "mutate", new_name: "m1", expression: { expression: "month(d)" } },
  { type: "mutate", new_name: "m2", expression: { expression: "month(d)" } },
  { type: "summarize", measures: [COUNT],
    dimensions: [{ column_name: "m1" }] }]).entangled, false);

// A DIFFERENT part in the label does not entangle this one: substituting
// QUARTER( leaves a month(...) CASE untouched.
assert.strictEqual(core.datePartGrouping([
  { type: "mutate", new_name: "Label",
    expression: { expression: "case(month(d) == 1, 'x')" } },
  { type: "mutate", new_name: "q", expression: { expression: "quarter(d)" } },
  { type: "summarize", measures: [COUNT],
    dimensions: [{ column_name: "q" }, { column_name: "Label" }] }]).entangled,
  false);

console.log("studio_core.test.js — date-part entanglement asserted");
