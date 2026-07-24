/*
 * Node self-check for studio_core.js — run: node studio_core.test.js
 * Pure logic only; no browser, no Frappe. This is the frontend's equivalent of
 * the Python fixture tests: it verifies logic, NOT live-Desk behaviour.
 */
"use strict";
var assert = require("assert");
var core = require("./studio_core.js");

// clampLayout keeps boxes on the 12-col grid
assert.deepStrictEqual(
  core.clampLayout({ pos_x: 20, pos_y: -3, width: 99, height: 0 }),
  { pos_x: 0, pos_y: 0, width: 12, height: 1 },
  "clampLayout bounds"
);

// serializeLayout returns only persistable fields
assert.deepStrictEqual(
  core.serializeLayout([{ name: "c1", chart_title: "x", pos_x: 2, pos_y: 1, width: 4, height: 3 }]),
  [{ name: "c1", pos_x: 2, pos_y: 1, width: 4, height: 3 }],
  "serializeLayout"
);

// applyChartEdit validates and does not mutate input
var original = { chart_title: "Old", chart_type: "Bar Chart", pos_x: 0, pos_y: 0, width: 4, height: 3 };
var edited = core.applyChartEdit(original, { chart_title: "New", chart_type: "Line Chart" });
assert.ok(edited.ok, "edit ok");
assert.strictEqual(edited.chart.chart_title, "New");
assert.strictEqual(edited.chart.chart_type, "Line Chart");
assert.strictEqual(original.chart_title, "Old", "input not mutated");

assert.ok(!core.applyChartEdit(original, { chart_title: "  " }).ok, "empty title rejected");
assert.ok(!core.applyChartEdit(original, { chart_type: "Pie" }).ok, "unknown chart type rejected");

// validateFilter mirrors the engine's operator allowlist
assert.ok(core.validateFilter({ fieldname: "academic_year", operator: "=" }).ok, "valid filter");
assert.ok(!core.validateFilter({ fieldname: "x", operator: "like" }).ok, "like rejected");
assert.ok(!core.validateFilter({ fieldname: "", operator: "=" }).ok, "missing field rejected");

// ---- mapping core ----
assert.strictEqual(core.nextMappingStatus("Suggested"), "Confirmed", "status cycle 1");
assert.strictEqual(core.nextMappingStatus("Confirmed"), "Rejected", "status cycle 2");
assert.strictEqual(core.nextMappingStatus("Rejected"), "Suggested", "status cycle wraps");
assert.strictEqual(core.nextMappingStatus("Missing"), "Suggested", "unknown status resets");

assert.deepStrictEqual(
  core.buildMapping("tabStudent Applicant", "Student Applicant"),
  { external_table: "tabStudent Applicant", target_doctype: "Student Applicant", mapping_status: "Suggested" },
  "buildMapping shape matches DS Data Mapping"
);

assert.deepStrictEqual(
  core.serializeCanvasNodes([{ node_id: "src:tabX", node_type: "Source Table", pos_x: 20.6, pos_y: null, label: "x" }]),
  [{ node_id: "src:tabX", node_type: "Source Table", pos_x: 21, pos_y: 0 }],
  "serializeCanvasNodes matches DS Canvas Node shape (label dropped, ints)"
);

var nodes = core.analysisToNodes(
  { doctypes: ["Student Applicant", "Student Admission UCC"] },
  ["Student Applicant"]
);
assert.strictEqual(nodes.length, 3, "two source + one target node");
assert.strictEqual(nodes[0].node_type, "Source Table");
assert.strictEqual(nodes[0].label, "tabStudent Applicant", "source label restores tab prefix");
assert.strictEqual(nodes[2].node_type, "Target DocType");
assert.ok(nodes[2].pos_x > nodes[0].pos_x, "targets laid out right of sources");

console.log("studio_core.test.js — all assertions passed");
