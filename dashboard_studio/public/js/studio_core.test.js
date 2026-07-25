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

// applyChartEdit carries section, including clearing it back to Ungrouped
var sectioned = core.applyChartEdit(original, { section: "sec-a" });
assert.strictEqual(sectioned.chart.section, "sec-a", "section assigned");
assert.strictEqual(core.applyChartEdit(sectioned.chart, { section: "" }).chart.section, null,
  "section can be cleared back to Ungrouped");
assert.ok(!("section" in core.applyChartEdit(original, { chart_title: "X" }).chart),
  "section untouched when not in the patch");

// applyChartEdit passes metric selection through
var withMetric = core.applyChartEdit(original, { metric: "Applicants by Year (MOCK)" });
assert.ok(withMetric.ok && withMetric.chart.metric === "Applicants by Year (MOCK)", "metric edit applied");

// isFilterEditable: Static+supported editable; Dynamic and like/between preserved read-only
assert.ok(core.isFilterEditable({ fieldname: "x", operator: "=", filter_type: "Static" }), "static = editable");
assert.ok(core.isFilterEditable({ fieldname: "x", operator: "" }), "new empty row editable");
assert.ok(!core.isFilterEditable({ fieldname: "x", operator: "=", filter_type: "Dynamic" }), "dynamic read-only");
assert.ok(!core.isFilterEditable({ fieldname: "x", operator: "like", filter_type: "Static" }), "like read-only");
assert.ok(!core.isFilterEditable({ fieldname: "x", operator: "between", filter_type: "Static" }), "between read-only");

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

// groupRelationships: grouped by source, children before links
var grouped = core.groupRelationships([
  { source: "DS Chart", target: "DS Metric", fieldname: "metric", kind: "link" },
  { source: "DS Chart", target: "DS Chart Filter", fieldname: "chart_filters", kind: "child" },
  { source: "DS Dashboard Section", target: "DS Dashboard", fieldname: "dashboard", kind: "link" },
]);
assert.deepStrictEqual(grouped.map(function (g) { return g.source; }),
  ["DS Chart", "DS Dashboard Section"], "grouped and sorted by source");
assert.strictEqual(grouped[0].edges[0].kind, "child", "child edges lead — ownership before reference");
assert.strictEqual(grouped[0].edges[1].fieldname, "metric");
assert.deepStrictEqual(core.groupRelationships([]), [], "no edges -> nothing");

// validationSummary: tallies by status, unknown statuses counted not dropped
var vs = core.validationSummary([
  { status: "Match" }, { status: "Match" }, { status: "Discrepancy" },
  { status: "Flagged" }, { status: "Accepted" }, { status: "Weird" },
]);
assert.strictEqual(vs.Match, 2);
assert.strictEqual(vs.Discrepancy, 1);
assert.strictEqual(vs.Flagged, 1);
assert.strictEqual(vs.Accepted, 1);
assert.strictEqual(vs.other, 1, "unknown status is counted, not silently dropped");
assert.strictEqual(vs.total, 6);

// canAccept mirrors the server: only a real difference can be accepted
assert.ok(core.canAccept({ status: "Discrepancy" }), "discrepancy acceptable");
assert.ok(core.canAccept({ status: "Flagged" }), "flagged acceptable");
assert.ok(!core.canAccept({ status: "Match" }), "nothing to accept on a match");
assert.ok(!core.canAccept({ status: "Accepted" }), "already accepted");
assert.ok(!core.canAccept(null), "no row");

// moveSection
var ordered = [{ name: "a" }, { name: "b" }, { name: "c" }];
assert.deepStrictEqual(core.moveSection(ordered, "b", -1), ["b", "a", "c"], "move up");
assert.deepStrictEqual(core.moveSection(ordered, "b", 1), ["a", "c", "b"], "move down");
assert.strictEqual(core.moveSection(ordered, "a", -1), null, "first cannot move up");
assert.strictEqual(core.moveSection(ordered, "c", 1), null, "last cannot move down");
assert.strictEqual(core.moveSection(ordered, "missing", 1), null, "unknown section");
assert.deepStrictEqual(ordered.map(function (s) { return s.name; }), ["a", "b", "c"],
  "input not mutated");

// groupChartsBySection
var secs = [
  { name: "sec-b", section_title: "Outcomes", sort_order: 2 },
  { name: "sec-a", section_title: "Intake", sort_order: 1, is_collapsed_default: 1 },
];
var chartsToGroup = [
  { name: "c1", section: "sec-a" },
  { name: "c2", section: "sec-b" },
  { name: "c3" },                       // no section
  { name: "c4", section: "sec-gone" },  // section deleted
];
var bands = core.groupChartsBySection(chartsToGroup, secs);
assert.strictEqual(bands.length, 3, "two sections plus an Ungrouped band");
assert.strictEqual(bands[0].title, "Outcomes", "server order is preserved, not re-sorted");
assert.strictEqual(bands[1].collapsed, true, "is_collapsed_default carried through");
assert.strictEqual(bands[2].title, "Ungrouped");
assert.deepStrictEqual(bands[2].charts.map(function (c) { return c.name; }), ["c3", "c4"],
  "sectionless AND orphaned charts fall through, never vanish");
assert.deepStrictEqual(core.groupChartsBySection(chartsToGroup, []), [],
  "no sections -> no bands, caller keeps the flat canvas");
var noOrphans = core.groupChartsBySection([{ name: "c1", section: "sec-a" }], secs);
assert.strictEqual(noOrphans.length, 2, "no Ungrouped band when nothing is ungrouped");

// mergeMappings: adds new suggestions, never resets an existing decision
var existingMappings = [
  { external_table: "tabStudent Applicant", target_doctype: "Student Applicant", mapping_status: "Rejected" },
];
var mergedMappings = core.mergeMappings(existingMappings, [
  { external_table: "tabStudent Applicant", target_doctype: "Student Applicant", mapping_status: "Suggested" },
  { external_table: "tabProgram", target_doctype: "Program", mapping_status: "Suggested" },
]);
assert.strictEqual(mergedMappings.length, 2, "only the genuinely new mapping is added");
assert.strictEqual(mergedMappings[0].mapping_status, "Rejected", "existing decision preserved");
assert.strictEqual(mergedMappings[1].target_doctype, "Program");
assert.strictEqual(existingMappings.length, 1, "input not mutated");
assert.strictEqual(core.mergeMappings([], [{ external_table: "", target_doctype: "X" }]).length, 0,
  "incomplete rows ignored");

// nodesFromProject: saved positions restored, labels derived from node_id
var restored = core.nodesFromProject(
  [{ node_id: "src:tabStudent Applicant", node_type: "Source Table", pos_x: 44, pos_y: 90 }],
  []
);
assert.strictEqual(restored.length, 1, "restores saved node");
assert.strictEqual(restored[0].label, "tabStudent Applicant", "label strips src: prefix");
assert.strictEqual(restored[0].pos_x, 44, "saved position kept");

// a mapping with no saved node still appears, laid out by side
var derived = core.nodesFromProject(
  [],
  [{ external_table: "tabStudent Applicant", target_doctype: "Student Applicant" }]
);
assert.strictEqual(derived.length, 2, "mapping implies a source and a target node");
assert.strictEqual(derived[0].node_type, "Source Table");
assert.strictEqual(derived[1].node_type, "Target DocType");
assert.ok(derived[1].pos_x > derived[0].pos_x, "targets laid out right of sources");

// a saved node is not duplicated by the mapping that references it
var mixed = core.nodesFromProject(
  [{ node_id: "src:tabStudent Applicant", node_type: "Source Table", pos_x: 44, pos_y: 90 }],
  [{ external_table: "tabStudent Applicant", target_doctype: "Student Applicant" }]
);
assert.strictEqual(mixed.length, 2, "saved source + derived target, no duplicate");
assert.strictEqual(mixed[0].pos_x, 44, "saved position wins over default layout");

console.log("studio_core.test.js — all assertions passed");
