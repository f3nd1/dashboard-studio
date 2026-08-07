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
