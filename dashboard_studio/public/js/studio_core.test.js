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

console.log("studio_core.test.js — all assertions passed");
