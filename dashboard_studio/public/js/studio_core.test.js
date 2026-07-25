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

// ---- parseReferenceRows: pasted reference results for the Validation Centre ----

var parsed = core.parseReferenceRows("2022, 2\n2023,3\n\n2024 , 1");
assert.deepStrictEqual(parsed.rows,
  [{ label: "2022", count: "2" }, { label: "2023", count: "3" }, { label: "2024", count: "1" }],
  "one row per non-blank line, both sides trimmed");
assert.deepStrictEqual(parsed.errors, [], "clean input has no errors");

// A blank value is unknown, not zero — it must survive as a blank so the
// comparison flags it instead of reporting a match against 0.
var blank = core.parseReferenceRows("Offered,");
assert.strictEqual(blank.rows[0].count, "", "blank value stays blank, never 0");
assert.deepStrictEqual(blank.errors, [], "a blank value is allowed, not an error");

// A label containing a comma still works — the value is after the LAST comma.
assert.deepStrictEqual(core.parseReferenceRows("Singapore, Central,4").rows,
  [{ label: "Singapore, Central", count: "4" }], "splits on the last comma");

// A line with no separator cannot be read; report it rather than guessing.
var bad = core.parseReferenceRows("2022 2\n2023,3");
assert.strictEqual(bad.rows.length, 1, "readable lines still parse");
assert.strictEqual(bad.errors.length, 1, "unreadable line reported");
assert.ok(/line 1/.test(bad.errors[0]), "error names the line: " + bad.errors[0]);

// An empty label is not a usable group.
assert.strictEqual(core.parseReferenceRows(" ,4").errors.length, 1, "blank label rejected");

assert.deepStrictEqual(core.parseReferenceRows("   "), { rows: [], errors: [] },
  "empty input is empty, not an error");

// ---- pickerModel: the dashboard picker's scale behaviour ----
//
// Fixture dashboards arrive the way list_dashboards returns them: modified desc.
function dash(n, title, status) {
  return { name: title, dashboard_title: title, status: status || "Draft" };
}
var small = ["Delta", "Alpha", "Charlie"].map(function (t, i) { return dash(i, t); });
var big = ["I", "H", "G", "F", "E", "D", "C", "B", "A"].map(function (t, i) { return dash(i, t); });

// 8 or fewer: no search box, no grouping — a short list stays light.
var eight = big.slice(0, 8);
var m8 = core.pickerModel(eight, {});
assert.strictEqual(m8.searchable, false, "8 dashboards is not above the threshold");
assert.strictEqual(m8.groups.length, 1, "no grouping at 8");
assert.strictEqual(m8.groups[0].title, null, "the single group is unlabelled");
assert.strictEqual(m8.groups[0].items.length, 8, "all 8 listed");
assert.strictEqual(m8.groups[0].items[0].dashboard_title, "I",
  "ungrouped keeps the server's modified-desc order");

// Above 8: search box and grouping switch on.
var m9 = core.pickerModel(big, {});
assert.strictEqual(m9.searchable, true, "9 is above the threshold");
assert.strictEqual(m9.groups.length, 2, "Recent + All dashboards");
assert.strictEqual(m9.groups[0].title, "Recent");
assert.strictEqual(m9.groups[1].title, "All dashboards");
assert.strictEqual(m9.groups[0].items.length, 5, "Recent is capped");
assert.deepStrictEqual(m9.groups[0].items.map(function (d) { return d.dashboard_title; }),
  ["I", "H", "G", "F", "E"], "Recent is last-modified order, untouched");
assert.deepStrictEqual(m9.groups[1].items.map(function (d) { return d.dashboard_title; }),
  ["A", "B", "C", "D", "E", "F", "G", "H", "I"], "All dashboards is alphabetical");
assert.strictEqual(big[0].dashboard_title, "I", "sorting did not mutate the caller's array");

// Searching narrows, and collapses the groups away: they help browsing, not narrowing.
var searched = core.pickerModel(big, { query: "a" });
assert.strictEqual(searched.groups.length, 1, "groups collapse while searching");
assert.strictEqual(searched.groups[0].title, null);
assert.deepStrictEqual(searched.groups[0].items.map(function (d) { return d.dashboard_title; }),
  ["A"], "filtered by title");
assert.strictEqual(searched.searchable, true, "the search box stays available while searching");

// Counts drive the footer: a filtered list must not read as a short one.
assert.strictEqual(m9.total, 9);
assert.strictEqual(m9.shown, 9, "unfiltered shows everything");
assert.strictEqual(searched.shown, 1);
assert.strictEqual(searched.total, 9, "total is the whole list, not the filtered one");

// Matching ignores case and surrounding space, and matches anywhere in the title.
var mixed = core.pickerModel(
  [dash(0, "Admission Overview")].concat(big), { query: "  VIEW " });
assert.deepStrictEqual(mixed.groups[0].items.map(function (d) { return d.dashboard_title; }),
  ["Admission Overview"], "case-insensitive substring match");

// Nothing matched — the caller needs to know, and needs the query back to say so.
var none = core.pickerModel(big, { query: "zzz" });
assert.strictEqual(none.shown, 0);
assert.strictEqual(none.query, "zzz", "trimmed query returned for the empty message");
assert.strictEqual(none.groups[0].items.length, 0);

// A short list never gets a search box, so a query it cannot produce is ignored.
var smallQueried = core.pickerModel(small, { query: "alpha" });
assert.strictEqual(smallQueried.searchable, false);
assert.strictEqual(smallQueried.shown, 3, "short lists are never filtered");

// Flat rows, in display order, are what the keyboard walks — group headers are
// not stops.
assert.deepStrictEqual(core.pickerRows(m9).map(function (d) { return d.dashboard_title; }),
  ["I", "H", "G", "F", "E", "A", "B", "C", "D", "E", "F", "G", "H", "I"],
  "every rendered row, groups flattened, duplicates and all");
assert.strictEqual(core.pickerRows(none).length, 0, "no rows when nothing matched");

// Empty input is a real state, not a crash.
var empty = core.pickerModel([], {});
assert.strictEqual(empty.total, 0);
assert.strictEqual(empty.searchable, false);
assert.strictEqual(core.pickerRows(empty).length, 0);

console.log("studio_core.test.js — all assertions passed");
