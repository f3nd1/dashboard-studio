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

// ---- dashboardFormUrl: link out to the DS Dashboard record form ----
//
// DS Dashboard is autonamed field:dashboard_title, so every name is a human
// title and spaces are the norm, not the edge case.
assert.strictEqual(core.dashboardFormUrl("Admission Overview"),
  "/app/ds-dashboard/Admission%20Overview", "spaces are encoded");
assert.strictEqual(core.dashboardFormUrl("Fees / Refunds"),
  "/app/ds-dashboard/Fees%20%2F%20Refunds",
  "a slash is encoded, not left to split the path");

// ---- sortResultRows: DS Chart.sort_order applied to metric result rows ----

var YEARS = [
  { academic_year: "2022", count: 5 },
  { academic_year: "2024", count: 11 },
  { academic_year: "2023", count: 2 },
];

// Default must reproduce what the engine already returns: dimension ascending.
["Ascending", "", null, undefined, "nonsense"].forEach(function (mode) {
  assert.deepStrictEqual(
    core.sortResultRows(YEARS, mode).map(function (r) { return r.academic_year; }),
    ["2022", "2023", "2024"],
    "unset/unknown order (" + mode + ") falls back to ascending — no chart changes today");
});

assert.deepStrictEqual(
  core.sortResultRows(YEARS, "Descending").map(function (r) { return r.academic_year; }),
  ["2024", "2023", "2022"], "Descending reverses the dimension");

assert.deepStrictEqual(
  core.sortResultRows(YEARS, "Highest first").map(function (r) { return r.count; }),
  [11, 5, 2], "Highest first orders by count, not by dimension");

// Must not mutate the caller's array — rows are cached and shared between charts,
// so two charts on one metric with different orders would corrupt each other.
var original = YEARS.map(function (r) { return r.academic_year; });
core.sortResultRows(YEARS, "Descending");
assert.deepStrictEqual(YEARS.map(function (r) { return r.academic_year; }), original,
  "input array is left untouched");

// Mixed-type dimension values must not throw — the Python engine has the same
// fallback, and a chart that cannot sort must still draw.
var mixed = [{ y: 2024, count: 1 }, { y: "2023", count: 2 }, { y: null, count: 3 }];
assert.strictEqual(core.sortResultRows(mixed, "Ascending").length, 3,
  "mixed types still return every row");
assert.strictEqual(core.sortResultRows(mixed, "Ascending")[2].y, null,
  "a null dimension sorts last, matching the engine");

// applyChartEdit must carry the field, and refuse a value the DocType rejects —
// otherwise the panel could save a Select value Frappe will not accept.
var edited = core.applyChartEdit(
  { chart_title: "X", chart_type: "Bar Chart", pos_x: 0, pos_y: 0, width: 4, height: 3 },
  { sort_order: "Highest first" });
assert.strictEqual(edited.ok, true);
assert.strictEqual(edited.chart.sort_order, "Highest first");
assert.strictEqual(
  core.applyChartEdit({ chart_title: "X", chart_type: "Bar Chart" },
    { sort_order: "Random" }).ok,
  false, "an order outside the DocType's options is rejected");

assert.deepStrictEqual(core.sortResultRows([], "Descending"), [], "empty stays empty");
assert.deepStrictEqual(core.sortResultRows(null, "Descending"), [], "null is not a crash");

// The readiness chip assembles the server's blockers; it never decides them.
assert.strictEqual(core.readinessChip(null, "Draft"), null,
  "no readiness payload means no chip, not a guess");

var ready = core.readinessChip({ publishable: true, blockers: [] }, "Draft");
assert.strictEqual(ready.text, "Draft · ready to publish");
assert.strictEqual(ready.tone, "ready");
assert.strictEqual(
  core.readinessChip({ publishable: true, blockers: [] }, "Published").text, "Published",
  "a published dashboard does not advertise that it is ready to publish");

var one = core.readinessChip(
  { blockers: [{ rule: "scope", summary: "no subcriterion set" }] }, "Draft");
assert.strictEqual(one.text, "Draft · no subcriterion set", "a single blocker is named");
assert.strictEqual(one.tone, "blocked");

var many = core.readinessChip({
  blockers: [
    { rule: "scope", summary: "no subcriterion set" },
    { rule: "chart_without_metric", summary: "2 charts with no metric" },
    { rule: "chart_not_validated", summary: "3 charts not validated since the last edit" },
  ],
}, "Draft");
assert.strictEqual(many.text, "Draft · no subcriterion set, +2 more");
assert.ok(many.detail.indexOf("3 charts not validated") !== -1,
  "the hover detail carries every blocker, not just the named one");

// Width presets map to grid columns; an off-preset width from drag-resize must
// survive opening the panel.
assert.deepStrictEqual(core.widthOptions(6).map(o => o.label), ["25%", "33%", "50%", "100%"]);
assert.strictEqual(core.widthOptions(6).find(o => o.value === 6).label, "50%");
var odd = core.widthOptions(7);
assert.strictEqual(odd.length, 5, "an off-preset width is offered too");
assert.strictEqual(odd.find(o => o.value === 7).label, "7 of 12 (custom)");
assert.deepStrictEqual(odd.map(o => o.value), [3, 4, 6, 7, 12], "and sorts into place");
assert.strictEqual(core.widthOptions(null).length, 4, "no width means no custom entry");

// dashboardSources: distinct source DocTypes of the metrics this dashboard's
// charts use, counted by chart, filtered by the search box.
var metricsByName = {
  M1: { source_doctype: "Student Applicant" },
  M2: { source_doctype: "Student Applicant" },
  M3: { source_doctype: "Agent" },
};
var resolve = function (n) { return metricsByName[n]; };
var srcCharts = [
  { metric: "M1" }, { metric: "M2" }, { metric: "M3" },
  { metric: "" },              // no metric linked yet
  { metric: "M-unknown" },     // metric not in the list
];
var sources = core.dashboardSources(srcCharts, resolve);
assert.deepStrictEqual(sources.map(s => s.source), ["Agent", "Student Applicant"], "sorted, distinct");
assert.strictEqual(sources[1].charts, 2, "two charts share Student Applicant");
assert.strictEqual(sources[1].subtitle, "2 charts");
assert.strictEqual(sources[0].subtitle, "1 chart", "singular is not '1 charts'");
assert.strictEqual(sources[0].glyph, "AG", "one-word name takes its first two characters");
assert.strictEqual(sources[1].glyph, "SA", "two-word name takes initials");
assert.deepStrictEqual(core.dashboardSources(srcCharts, resolve, "app").map(s => s.source),
  ["Student Applicant"], "search filters");
assert.deepStrictEqual(core.dashboardSources(srcCharts, resolve, "  AGE ").map(s => s.source),
  ["Agent"], "search is trimmed and case-insensitive");
assert.deepStrictEqual(core.dashboardSources(srcCharts, resolve, "zzz"), [], "no match");
assert.deepStrictEqual(core.dashboardSources([], resolve), [], "no charts");
assert.deepStrictEqual(core.dashboardSources(srcCharts, function () { return null; }), [],
  "a metric list that has not loaded yields nothing, never a guessed source");

// targetSuggestions: canvas targets plus every metric's source, distinct+sorted.
assert.deepStrictEqual(
  core.targetSuggestions(
    [{ node_type: "Target DocType", label: "Student Applicant" },
     { node_type: "Source Table", label: "tabStudent Applicant" },
     { node_type: "Target DocType", label: "Employee" }],
    [{ source_doctype: "Student Applicant" }, { source_doctype: "Agent" }, {}]),
  ["Agent", "Employee", "Student Applicant"]);
assert.deepStrictEqual(core.targetSuggestions([], []), [], "nothing known, nothing suggested");
assert.deepStrictEqual(core.targetSuggestions(null, null), [], "null is not a crash");

// mappingRows: every source table on the canvas appears, mapped or not. This is
// the three-query bug — an untranslatable query adds a node and no mapping, so a
// panel driven by mappings alone never showed queries 2 and 3.
var mapNodes = [
  { node_type: "Source Table", label: "tabStudent Applicant" },
  { node_type: "Target DocType", label: "Student Applicant" },
  { node_type: "Source Table", label: "tabEmployee" },
  { node_type: "Source Table", label: "tabAgent" },
];
var mapped = [{ external_table: "tabStudent Applicant", target_doctype: "Student Applicant",
                mapping_status: "Suggested" }];
var rows = core.mappingRows(mapNodes, mapped);
assert.deepStrictEqual(rows.map(r => r.external_table),
  ["tabStudent Applicant", "tabEmployee", "tabAgent"], "every source table is listed");
assert.strictEqual(rows[0].target_doctype, "Student Applicant");
assert.strictEqual(rows[1].target_doctype, "", "an unmapped table has an empty target");
assert.strictEqual(rows[1].mapping_status, "Unmapped");
assert.strictEqual(rows[0], mapped[0], "an existing mapping is the SAME object, so edits stick");
// A mapping whose node was never added is data, not noise.
assert.deepStrictEqual(
  core.mappingRows([], [{ external_table: "tabOrphan", target_doctype: "X" }])
    .map(r => r.external_table), ["tabOrphan"]);
assert.deepStrictEqual(core.mappingRows(null, null), [], "null is not a crash");

// describeMeasure: what the node card shows under the table name.
assert.strictEqual(core.describeMeasure(
  { supported: true, aggregations: [{ function: "COUNT" }], group_by: ["agent"] }), "Count by agent");
assert.strictEqual(core.describeMeasure(
  { supported: true, aggregations: [{ function: "SUM" }], group_by: ["program"] }), "Sum by program");
assert.strictEqual(core.describeMeasure(
  { supported: true, aggregations: [{ function: "COUNT" }], group_by: [] }), "Count");
assert.strictEqual(core.describeMeasure({ supported: false, reasons: ["subquery"] }), "not translated",
  "an untranslated query must not look like a translated one on the card");
assert.strictEqual(core.describeMeasure(null), "not translated");

// The newest query about a table wins the subtitle.
var n1 = core.analysisToNodes(
  { supported: true, doctypes: ["Student Applicant"], aggregations: [{ function: "COUNT" }],
    group_by: ["agent"] }, []);
assert.strictEqual(n1[0].measure, "Count by agent");
var n2 = core.mergeNodes(n1, core.analysisToNodes(
  { supported: true, doctypes: ["Student Applicant"], aggregations: [{ function: "COUNT" }],
    group_by: ["nationality"] }, []));
assert.strictEqual(n2.length, 1, "same table, still one node");
assert.strictEqual(n2[0].measure, "Count by nationality", "the card still described the older query");

// clearedCanvas: confirmed work survives, everything else goes.
var cnodes = [
  { node_id: "src:tabA", node_type: "Source Table", label: "tabA" },
  { node_id: "tgt:A", node_type: "Target DocType", label: "A" },
  { node_id: "src:tabB", node_type: "Source Table", label: "tabB" },
  { node_id: "tgt:B", node_type: "Target DocType", label: "B" },
];
var cmaps = [
  { external_table: "tabA", target_doctype: "A", mapping_status: "Confirmed" },
  { external_table: "tabB", target_doctype: "B", mapping_status: "Suggested" },
];
var cleared = core.clearedCanvas(cnodes, cmaps);
assert.deepStrictEqual(cleared.nodes.map(n => n.node_id), ["src:tabA", "tgt:A"]);
assert.deepStrictEqual(cleared.mappings.map(m => m.external_table), ["tabA"]);
assert.strictEqual(cleared.keptConfirmed, 1);
assert.deepStrictEqual(core.clearedCanvas(cnodes, []).nodes, [], "nothing confirmed, nothing kept");
assert.deepStrictEqual(core.clearedCanvas(null, null),
  { nodes: [], mappings: [], keptConfirmed: 0 });

// chartTypeOptions: the publish constraint, in the one place both pickers read.
var opts = core.chartTypeOptions("Bar Chart", ["Bar Chart", "KPI Card", "Table"]);
assert.strictEqual(opts.length, core.CHART_TYPES.length, "every type is still offered");
var byValue = {};
opts.forEach(function (o) { byValue[o.value] = o; });
assert.strictEqual(byValue["KPI Card"].disabled, true, "KPI Card is selectable");
assert.strictEqual(byValue["Line Chart"].disabled, true, "Line Chart is selectable");
assert.strictEqual(byValue["Table"].disabled, true, "Table is selectable");
assert.strictEqual(byValue["Bar Chart"].disabled, false, "a publishable type was blocked");
assert.strictEqual(byValue["Donut Chart"].disabled, false, "a publishable type was blocked");
assert.ok(/not publishable/.test(byValue["Table"].label), "the label does not say why");
assert.ok(/CHART_TYPE_MAPPING/.test(byValue["Table"].reason), "the reason cites no source");
assert.strictEqual(byValue["Bar Chart"].reason, null, "a publishable type carries a refusal");
// A type Sophia cannot draw and this app cannot draw either says the publish
// thing, not the drawing thing — publishing is the harder constraint.
assert.ok(/not publishable/.test(byValue["Line Chart"].label));
assert.ok(/no chart yet/.test(byValue["Gauge"].label), "undrawable type lost its note");

// The CURRENT type is never disabled: an existing KPI Card must stay editable
// and must not be silently retyped by a picker that refuses to show it.
var onKpi = {};
core.chartTypeOptions("KPI Card", []).forEach(function (o) { onKpi[o.value] = o; });
assert.strictEqual(onKpi["KPI Card"].disabled, false, "an existing KPI Card became uneditable");
assert.strictEqual(onKpi["KPI Card"].selected, true);
assert.ok(/cannot be published/.test(onKpi["KPI Card"].label),
  "an existing unpublishable chart does not say so");
assert.strictEqual(onKpi["Table"].disabled, true, "the other blocked types unblocked too");

// chartBlockReason: why a card cannot show live data, decided before asking.
assert.strictEqual(core.chartBlockReason({ metric: "M", metric_status: "Approved",
  metric_calculation: "Count" }), null, "an approved count metric was blocked");
assert.strictEqual(core.chartBlockReason({ metric: "M" }), null,
  "an older payload with no status must not invent a refusal");
assert.strictEqual(core.chartBlockReason({}).title, "No metric linked");
var draft = core.chartBlockReason({ metric: "DEMO Survey responses", metric_status: "Draft",
  metric_calculation: "Count" });
assert.strictEqual(draft.title, "Metric not yet approved");
assert.ok(/DEMO Survey responses/.test(draft.hint), "the refusal does not name the metric");
assert.ok(/DS Metric list/.test(draft.hint), "the refusal does not say what to do");
assert.strictEqual(core.chartBlockReason({ metric: "M", metric_status: "Deprecated" }).title,
  "Metric not yet approved");
assert.ok(/Deprecated/.test(core.chartBlockReason({ metric: "M",
  metric_status: "Deprecated" }).hint), "Deprecated reads as merely unapproved");
assert.strictEqual(core.chartBlockReason({ metric: "M", metric_missing: true }).title,
  "Metric not found");
assert.strictEqual(core.chartBlockReason({ metric: "M", metric_status: "Approved",
  metric_calculation: "Sum" }).title, "Metric cannot run yet");
// Status is checked before calculation: a Draft Sum metric is unapproved first.
assert.strictEqual(core.chartBlockReason({ metric: "M", metric_status: "Draft",
  metric_calculation: "Sum" }).title, "Metric not yet approved");

// insightsPrefill: what Studio can say that raw SQL cannot.
var pf = core.insightsPrefill({
  doctypes: ["Student Applicant"], group_by: ["agent"],
  aggregations: [{ function: "COUNT", argument: "*" }],
});
assert.deepStrictEqual(pf, { title: "Count of Student Applicant by agent",
  x_axis: "agent", y_axis: "count", series: "", chart_type: "bar" });

// A named aggregate column, not COUNT(*), becomes the Y axis.
assert.strictEqual(core.insightsPrefill({ doctypes: ["Fee"], group_by: ["term"],
  aggregations: [{ function: "SUM", argument: "`amount`" }] }).y_axis, "amount",
  "backticks survived into the axis name");
assert.strictEqual(core.insightsPrefill({ doctypes: ["Fee"], group_by: ["term"],
  aggregations: [{ function: "SUM", argument: "amount" }] }).title,
  "Sum of Fee by term");

// The title degrades the same way the endpoint's does — the queries most worth
// sending to Insights are the ones the parser could NOT translate.
assert.strictEqual(core.insightsPrefill({ doctypes: ["Employee"] }).title, "Employee query");
assert.strictEqual(core.insightsPrefill({ doctypes: ["B", "A"] }).title, "A + 1 more",
  "two tables are not named in a stable order");
assert.strictEqual(core.insightsPrefill(null).title, "Imported SQL query");
assert.strictEqual(core.insightsPrefill({}).x_axis, "", "an axis was invented from nothing");

// suggestedChartType: a suggestion has to be drawable from what the query returns.
assert.strictEqual(core.suggestedChartType({ group_by: [], aggregations: [{ function: "COUNT" }] }),
  "number", "one number with no dimension is a KPI, not a bar of one");
assert.strictEqual(core.suggestedChartType({ group_by: ["a"], aggregations: [{ function: "COUNT" }] }),
  "bar");
assert.strictEqual(core.suggestedChartType({ group_by: ["a", "b"], aggregations: [{ function: "COUNT" }] }),
  "bar", "two dimensions is a bar split by colour — the second is the series");
assert.strictEqual(core.suggestedChartType({ group_by: ["a", "b", "c"], aggregations: [{ function: "COUNT" }] }),
  "table", "three dimensions has nowhere to put the third");
assert.strictEqual(core.suggestedChartType({ group_by: ["a"], aggregations: [] }), "table");
assert.strictEqual(core.suggestedChartType(null), "table");
assert.deepStrictEqual(core.INSIGHTS_CHART_TYPES.map(function (t) { return t.value; }),
  ["bar", "line", "donut", "number", "table"]);

// axisState: an empty axis is NOT a guess.
assert.strictEqual(core.axisState("agent", false), "guessed");
assert.strictEqual(core.axisState("agent", true), "confirmed");
assert.strictEqual(core.axisState("", false), "missing");
assert.strictEqual(core.axisState("   ", true), "missing",
  "whitespace counted as a detected axis");
assert.strictEqual(core.axisState(null, false), "missing");
assert.strictEqual(core.axisState(undefined, true), "missing");
// The join case that produced the blank boxes: both axes missing, title fine.
var joined = core.insightsPrefill({ supported: false,
  doctypes: ["Student Admission UCC", "Student Applicant"], group_by: [], aggregations: [] });
assert.strictEqual(joined.title, "Student Admission UCC + 1 more");
assert.strictEqual(core.axisState(joined.x_axis, false), "missing");
assert.strictEqual(core.axisState(joined.y_axis, false), "missing");
assert.strictEqual(joined.chart_type, "table", "the chart-type fallback changed");

// clampTitle: Insights' title is varchar(140) and Frappe aborts the whole
// insert with "Value too big" rather than trimming. A title is cosmetic; the
// query is not.
assert.strictEqual(core.clampTitle("short"), "short");
var edge = "x".repeat(140);
assert.strictEqual(core.clampTitle(edge), edge, "exactly 140 must not be trimmed");
var over = core.clampTitle("y".repeat(400));
assert.strictEqual(over.length, 140, "clamped title still exceeds the column");
assert.ok(over.endsWith("…"), "no marker that the title was cut");
assert.strictEqual(core.clampTitle("  lots   of   space  "), "lots of space");
assert.strictEqual(core.clampTitle(null), "");
// The real shape that crashed: Metabase-compiled SQL whose generated join
// aliases are long enough that a handful of them blow the limit.
var alias = "Quality Performance Actual Value Parameter Child_a3e4a16b";
var wide = core.insightsPrefill({ doctypes: [alias, alias + "2", alias + "3", alias + "4"] });
assert.ok(wide.title.length <= 140, "compiled-SQL title would still be refused");
assert.strictEqual(wide.title, alias + " + 3 more",
  "the many-table title should name the base and count the rest");

// series: the colour breakdown, from a SECOND group-by column only.
var twoDim = core.insightsPrefill({ doctypes: ["Objective"], group_by: ["quarter", "perspective"],
  aggregations: [{ function: "COUNT", argument: "*" }] });
assert.strictEqual(twoDim.x_axis, "quarter");
assert.strictEqual(twoDim.series, "perspective", "the second group-by is the colour field");
assert.strictEqual(twoDim.chart_type, "bar",
  "two dimensions plus an aggregate is a bar split by colour, not a table");
var oneDim = core.insightsPrefill({ doctypes: ["Objective"], group_by: ["quarter"],
  aggregations: [{ function: "COUNT", argument: "*" }] });
assert.strictEqual(oneDim.series, "", "a series was invented from one group-by");
// Three dimensions has nowhere left to put the third — still a table.
assert.strictEqual(core.insightsPrefill({ doctypes: ["O"], group_by: ["a", "b", "c"],
  aggregations: [{ function: "COUNT", argument: "*" }] }).chart_type, "table");
// An imported card's series wins and reads Confirmed, same as the axes.
var withSeries = core.mergeImportedFields({ series: "guessed" }, { series: "perspective" });
assert.strictEqual(withSeries.fields.series, "perspective");
assert.strictEqual(withSeries.confirmed.series, true);

// mergeImportedFields: the card's own settings beat anything guessed from SQL.
var guessed = { title: "Guessed title", x_axis: "gx", y_axis: "gy", chart_type: "table" };
var merged = core.mergeImportedFields(guessed,
  { title: "Applicants per Country", x_axis: "country", y_axis: "count", chart_type: "bar" });
assert.strictEqual(merged.fields.title, "Applicants per Country");
assert.strictEqual(merged.fields.chart_type, "bar", "the card's own display lost to a guess");
assert.strictEqual(merged.confirmed.x_axis, true, "an imported axis still reads as Guessed");
// A dropped axis (a stale setting naming a column the card no longer returns)
// falls back to the guess and stays Guessed — not blank, not Confirmed.
var partial = core.mergeImportedFields(guessed, { title: "Real title", y_axis: "count" });
assert.strictEqual(partial.fields.x_axis, "gx", "a blank import wiped the guess");
assert.strictEqual(partial.confirmed.x_axis, undefined, "a fallback was marked Confirmed");
assert.strictEqual(partial.confirmed.y_axis, true);
assert.strictEqual(core.mergeImportedFields(null, null).fields.title, "");

console.log("studio_core.test.js — all assertions passed");
