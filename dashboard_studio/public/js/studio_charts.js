/*
 * Dashboard Studio — pure chart rendering for the Design view.
 * Turns metric result rows [{<dimension>: label, count: n}] into SVG/HTML
 * strings. No DOM, no Frappe, no dependencies — Node-testable like
 * studio_core.js (see studio_charts.test.js). UMD-style export.
 *
 * ponytail: hand-built SVG covers count-by-group marks (bar/line/donut/KPI/
 * table). If richer charts (axes, tooltips, legends) are ever required, that is
 * the point to discuss a charting library — not before.
 */
(function (root) {
  "use strict";

  // Chart types that map naturally to count-by-group data. The other schema
  // types render a visible "not yet supported" stub instead of guessing.
  var SUPPORTED = ["KPI Card", "Bar Chart", "Line Chart", "Donut Chart", "Table"];

  // Accent-first palette, matches studio.css.
  var COLORS = ["#0d7481", "#4fa3ad", "#8bc3ca", "#c2dfe3", "#1b4b52", "#6b5cc4"];

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // Rows carry the dimension under its real field name; find it.
  function inferDimension(rows) {
    if (!rows || !rows.length) return null;
    var keys = Object.keys(rows[0]);
    for (var i = 0; i < keys.length; i++) {
      if (keys[i] !== "count") return keys[i];
    }
    return null;
  }

  function series(rows) {
    var dim = inferDimension(rows);
    return {
      labels: rows.map(function (r) { return r[dim]; }),
      values: rows.map(function (r) { return Number(r.count) || 0; }),
    };
  }

  function empty() {
    return '<div class="dss-nochart">No data</div>';
  }

  function kpi(rows) {
    var total = series(rows).values.reduce(function (a, b) { return a + b; }, 0);
    return '<div class="dss-kpi">' + esc(total) + '</div>';
  }

  function bar(rows) {
    var s = series(rows);
    var max = Math.max.apply(null, s.values.concat([1]));
    var slot = 100 / s.values.length;
    var rects = s.values.map(function (v, i) {
      var h = (v / max) * 52;
      return '<rect x="' + (i * slot + slot * 0.15).toFixed(2) + '" y="' + (56 - h).toFixed(2) +
        '" width="' + (slot * 0.7).toFixed(2) + '" height="' + h.toFixed(2) +
        '" fill="' + COLORS[0] + '"><title>' + esc(s.labels[i]) + ": " + esc(v) + "</title></rect>";
    }).join("");
    return '<svg viewBox="0 0 100 60" preserveAspectRatio="none" class="dss-chart-svg">' + rects + "</svg>";
  }

  function line(rows) {
    var s = series(rows);
    var max = Math.max.apply(null, s.values.concat([1]));
    var step = s.values.length > 1 ? 92 / (s.values.length - 1) : 0;
    var points = s.values.map(function (v, i) {
      return (4 + i * step).toFixed(2) + "," + (54 - (v / max) * 48).toFixed(2);
    }).join(" ");
    return '<svg viewBox="0 0 100 60" preserveAspectRatio="none" class="dss-chart-svg">' +
      '<polyline points="' + points + '" fill="none" stroke="' + COLORS[0] + '" stroke-width="2"/>' +
      "</svg>";
  }

  function donut(rows) {
    // stroke-dasharray segment technique on a unit circle (r=15.9155 makes the
    // circumference ~100, so values map straight to percentages).
    var s = series(rows);
    var total = s.values.reduce(function (a, b) { return a + b; }, 0);
    if (!total) return empty();
    var offset = 25; // start at 12 o'clock
    var segments = s.values.map(function (v, i) {
      var pct = (v / total) * 100;
      var seg = '<circle r="15.9155" cx="21" cy="21" fill="none" stroke-width="7" ' +
        'stroke="' + COLORS[i % COLORS.length] + '" stroke-dasharray="' + pct.toFixed(2) +
        ' ' + (100 - pct).toFixed(2) + '" stroke-dashoffset="' + offset.toFixed(2) + '">' +
        "<title>" + esc(s.labels[i]) + ": " + esc(v) + "</title></circle>";
      offset -= pct;
      return seg;
    }).join("");
    return '<svg viewBox="0 0 42 42" class="dss-chart-svg dss-chart-donut">' + segments + "</svg>";
  }

  function table(rows) {
    var dim = inferDimension(rows);
    var body = rows.map(function (r) {
      return "<tr><td>" + esc(r[dim]) + "</td><td>" + esc(r.count) + "</td></tr>";
    }).join("");
    return '<table class="dss-table"><thead><tr><th>' + esc(dim) +
      "</th><th>count</th></tr></thead><tbody>" + body + "</tbody></table>";
  }

  function render(chartType, rows) {
    if (SUPPORTED.indexOf(chartType) === -1) {
      return {
        supported: false,
        html: '<div class="dss-nochart">' + esc(chartType || "This chart type") +
          " is not yet supported</div>",
      };
    }
    if (!rows || !rows.length) return { supported: true, html: empty() };
    var html;
    if (chartType === "KPI Card") html = kpi(rows);
    else if (chartType === "Bar Chart") html = bar(rows);
    else if (chartType === "Line Chart") html = line(rows);
    else if (chartType === "Donut Chart") html = donut(rows);
    else html = table(rows);
    return { supported: true, html: html };
  }

  var api = {
    SUPPORTED_CHART_TYPES: SUPPORTED,
    esc: esc,
    inferDimension: inferDimension,
    render: render,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.DSStudioCharts = api;
})(typeof window !== "undefined" ? window : globalThis);
