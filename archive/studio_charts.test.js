/*
 * Node self-check for studio_charts.js — run: node studio_charts.test.js
 * Verifies rendering LOGIC only, not live-Desk behaviour (no Bench available).
 */
"use strict";
var assert = require("assert");
var charts = require("./studio_charts.js");

// FIXTURE ONLY — invented rows, not real UCC data.
var rows = [
  { academic_year: "2022", count: 2 },
  { academic_year: "2023", count: 3 },
  { academic_year: "2024", count: 1 },
];

assert.strictEqual(charts.inferDimension(rows), "academic_year", "inferDimension");
assert.strictEqual(charts.inferDimension([]), null, "inferDimension empty");

var kpi = charts.render("KPI Card", rows);
assert.ok(kpi.supported && kpi.html.indexOf(">6<") !== -1, "KPI sums counts (2+3+1)");

var bar = charts.render("Bar Chart", rows);
assert.strictEqual((bar.html.match(/<rect /g) || []).length, 3, "bar renders one rect per group");

var line = charts.render("Line Chart", rows);
assert.ok(line.html.indexOf("<polyline") !== -1, "line renders a polyline");

// A single group must still be visible — a one-point polyline draws nothing.
var oneLine = charts.render("Line Chart", [{ academic_year: "2024", count: 5 }]);
assert.ok(oneLine.html.indexOf("<circle") !== -1, "single-point line renders a visible dot");

var donut = charts.render("Donut Chart", rows);
assert.strictEqual((donut.html.match(/<circle /g) || []).length, 3, "donut renders one segment per group");

var table = charts.render("Table", rows);
assert.strictEqual((table.html.match(/<tr><td>/g) || []).length, 3, "table renders one row per group");
assert.ok(table.html.indexOf("academic_year") !== -1, "table header shows dimension");

// Trend: area + line + emphasized endpoint
var trend = charts.render("Trend Chart", rows);
assert.ok(trend.supported && trend.html.indexOf("<polygon") !== -1, "trend has an area fill");
assert.ok(trend.html.indexOf("<circle") !== -1, "trend marks the latest value");

// Funnel: one band per group, ordered by magnitude (widest first)
var funnel = charts.render("Funnel", rows);
assert.strictEqual((funnel.html.match(/<rect /g) || []).length, 3, "funnel band per group");
var widths = (funnel.html.match(/width="([\d.]+)"/g) || []).map(function (w) {
  return parseFloat(w.replace(/[^\d.]/g, ""));
});
assert.ok(widths[0] >= widths[1] && widths[1] >= widths[2], "funnel tapers by count");

// Radar: polygon over >=3 groups; degenerate below that
var radar = charts.render("Radar", rows);
assert.ok(radar.supported && radar.html.indexOf("<polygon") !== -1, "radar renders a polygon");
var radar2 = charts.render("Radar", rows.slice(0, 2));
assert.ok(radar2.html.indexOf("at least 3 groups") !== -1, "radar declines under 3 groups");

// Unsupported types stub with the SPECIFIC reason, not a bare message.
var matrix = charts.render("Matrix", rows);
assert.ok(!matrix.supported, "Matrix unsupported");
assert.ok(matrix.html.indexOf("two dimensions") !== -1, "Matrix explains why");
var gauge = charts.render("Gauge", rows);
assert.ok(gauge.html.indexOf("target") !== -1, "Gauge explains the missing target");
var unknown = charts.render("Totally Made Up", rows);
assert.ok(!unknown.supported, "unknown type still stubs safely");

// Empty result -> No data placeholder, still supported.
var none = charts.render("Bar Chart", []);
assert.ok(none.supported && none.html.indexOf("No data") !== -1, "empty rows placeholder");

// Labels are escaped — a hostile dimension value must not become markup.
var hostile = charts.render("Table", [{ academic_year: '<img src=x onerror=1>', count: 1 }]);
assert.ok(hostile.html.indexOf("<img") === -1 && hostile.html.indexOf("&lt;img") !== -1, "labels escaped");

console.log("studio_charts.test.js — all assertions passed");
