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
