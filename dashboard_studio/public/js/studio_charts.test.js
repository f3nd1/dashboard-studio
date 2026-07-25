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

// Unsupported types stub visibly instead of guessing.
var radar = charts.render("Radar", rows);
assert.ok(!radar.supported && radar.html.indexOf("not yet supported") !== -1, "unsupported stub");

// Empty result -> No data placeholder, still supported.
var none = charts.render("Bar Chart", []);
assert.ok(none.supported && none.html.indexOf("No data") !== -1, "empty rows placeholder");

// Labels are escaped — a hostile dimension value must not become markup.
var hostile = charts.render("Table", [{ academic_year: '<img src=x onerror=1>', count: 1 }]);
assert.ok(hostile.html.indexOf("<img") === -1 && hostile.html.indexOf("&lt;img") !== -1, "labels escaped");

console.log("studio_charts.test.js — all assertions passed");
