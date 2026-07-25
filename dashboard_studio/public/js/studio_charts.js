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

  // Chart types that map naturally to count-by-group data — the only shape the
  // engine produces ([{<dimension>: label, count: n}]).
  var SUPPORTED = [
    "KPI Card", "Bar Chart", "Line Chart", "Donut Chart", "Table",
    "Trend Chart", "Funnel", "Radar",
  ];

  // The rest are stubbed with the specific reason they cannot be drawn from
  // count-by-group data, rather than a bare "not supported". Each would need
  // either a second dimension, an ordering the data does not carry, or a
  // target/relationship the schema has no field for.
  var UNSUPPORTED_REASONS = {
    "Gauge": "needs a target or maximum to measure against; DS Metric has no target field",
    "Lifecycle": "needs an ordered stage sequence — groups arrive alphabetically, so any order shown would be invented",
    "Flow": "needs source-to-target pairs with volumes; the engine groups by a single dimension",
    "Matrix": "needs two dimensions (rows and columns); the engine groups by one",
    "Risk Matrix": "needs two dimensions (likelihood and impact); the engine groups by one",
    "Decision Diagram": "needs branch/condition structure, which counts do not describe",
    "Network Diagram": "needs relationships between records, not aggregated counts",
    "Reconciliation Diagram": "needs two result sets to compare — that is the DS Validation Comparison feature",
    "Maturity Ladder": "needs a defined level scale and a current position, neither of which counts provide",
  };

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
    if (s.values.length === 1) {
      // A one-point polyline draws nothing, so mark the single value instead.
      var only = (54 - (s.values[0] / max) * 48).toFixed(2);
      return '<svg viewBox="0 0 100 60" preserveAspectRatio="none" class="dss-chart-svg">' +
        '<circle cx="50" cy="' + only + '" r="2" fill="' + COLORS[0] + '"><title>' +
        esc(s.labels[0]) + ": " + esc(s.values[0]) + "</title></circle></svg>";
    }
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

  // Trend = the line, plus an area fill and an emphasized endpoint so the
  // latest value reads at a glance.
  function trend(rows) {
    var s = series(rows);
    if (s.values.length === 1) return line(rows);
    var max = Math.max.apply(null, s.values.concat([1]));
    var step = 92 / (s.values.length - 1);
    var pts = s.values.map(function (v, i) {
      return { x: 4 + i * step, y: 54 - (v / max) * 48 };
    });
    var path = pts.map(function (p) { return p.x.toFixed(2) + "," + p.y.toFixed(2); }).join(" ");
    var last = pts[pts.length - 1];
    return '<svg viewBox="0 0 100 60" preserveAspectRatio="none" class="dss-chart-svg">' +
      '<polygon points="4,56 ' + path + " " + last.x.toFixed(2) + ',56" fill="' + COLORS[0] +
      '" fill-opacity="0.15"/>' +
      '<polyline points="' + path + '" fill="none" stroke="' + COLORS[0] + '" stroke-width="2"/>' +
      '<circle cx="' + last.x.toFixed(2) + '" cy="' + last.y.toFixed(2) + '" r="2" fill="' +
      COLORS[0] + '"><title>' + esc(s.labels[s.labels.length - 1]) + ": " +
      esc(s.values[s.values.length - 1]) + "</title></circle></svg>";
  }

  // Funnel = groups ordered by magnitude, tapering. Order is by count
  // descending (what a funnel shows); the data carries no process order.
  function funnel(rows) {
    var s = series(rows);
    var pairs = s.labels.map(function (label, i) { return { label: label, value: s.values[i] }; });
    pairs.sort(function (a, b) { return b.value - a.value; });
    var max = Math.max.apply(null, pairs.map(function (p) { return p.value; }).concat([1]));
    var band = 60 / pairs.length;
    var bars = pairs.map(function (p, i) {
      var w = (p.value / max) * 96;
      return '<rect x="' + ((100 - w) / 2).toFixed(2) + '" y="' + (i * band + band * 0.12).toFixed(2) +
        '" width="' + w.toFixed(2) + '" height="' + (band * 0.76).toFixed(2) +
        '" fill="' + COLORS[i % COLORS.length] + '"><title>' + esc(p.label) + ": " +
        esc(p.value) + "</title></rect>";
    }).join("");
    return '<svg viewBox="0 0 100 60" preserveAspectRatio="none" class="dss-chart-svg">' + bars + "</svg>";
  }

  // Radar = one axis per group, radius proportional to count. Square viewBox so
  // the shape is not distorted (no preserveAspectRatio="none" here).
  function radar(rows) {
    var s = series(rows);
    if (s.values.length < 3) {
      return '<div class="dss-nochart">Radar needs at least 3 groups (this metric returned ' +
        s.values.length + ")</div>";
    }
    var max = Math.max.apply(null, s.values.concat([1]));
    var point = function (value, i) {
      var angle = (-90 + (360 / s.values.length) * i) * (Math.PI / 180);
      var r = (value / max) * 38;
      return (50 + r * Math.cos(angle)).toFixed(2) + "," + (50 + r * Math.sin(angle)).toFixed(2);
    };
    var spokes = s.values.map(function (v, i) {
      return '<line x1="50" y1="50" x2="' + point(max, i).split(",")[0] + '" y2="' +
        point(max, i).split(",")[1] + '" stroke="' + COLORS[3] + '" stroke-width="0.5"/>';
    }).join("");
    var shape = s.values.map(point).join(" ");
    var titles = s.values.map(function (v, i) {
      return '<circle cx="' + point(v, i).split(",")[0] + '" cy="' + point(v, i).split(",")[1] +
        '" r="1.6" fill="' + COLORS[0] + '"><title>' + esc(s.labels[i]) + ": " + esc(v) +
        "</title></circle>";
    }).join("");
    return '<svg viewBox="0 0 100 100" class="dss-chart-svg dss-chart-square">' +
      '<circle cx="50" cy="50" r="38" fill="none" stroke="' + COLORS[3] + '" stroke-width="0.5"/>' +
      spokes +
      '<polygon points="' + shape + '" fill="' + COLORS[0] + '" fill-opacity="0.25" stroke="' +
      COLORS[0] + '" stroke-width="1.5"/>' + titles + "</svg>";
  }

  function table(rows) {
    var dim = inferDimension(rows);
    var body = rows.map(function (r) {
      return "<tr><td>" + esc(r[dim]) + "</td><td>" + esc(r.count) + "</td></tr>";
    }).join("");
    return '<table class="dss-table"><thead><tr><th>' + esc(dim) +
      "</th><th>count</th></tr></thead><tbody>" + body + "</tbody></table>";
  }

  var RENDERERS = {
    "KPI Card": kpi,
    "Bar Chart": bar,
    "Line Chart": line,
    "Donut Chart": donut,
    "Table": table,
    "Trend Chart": trend,
    "Funnel": funnel,
    "Radar": radar,
  };

  function render(chartType, rows) {
    var draw = RENDERERS[chartType];
    if (!draw) {
      var reason = UNSUPPORTED_REASONS[chartType];
      return {
        supported: false,
        html: '<div class="dss-nochart"><strong>' + esc(chartType || "This chart type") +
          "</strong> cannot be drawn from count-by-group data — " +
          esc(reason || "no rendering is defined for it yet") + "</div>",
      };
    }
    if (!rows || !rows.length) return { supported: true, html: empty() };
    return { supported: true, html: draw(rows) };
  }

  var api = {
    SUPPORTED_CHART_TYPES: SUPPORTED,
    inferDimension: inferDimension,
    render: render,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.DSStudioCharts = api;
})(typeof window !== "undefined" ? window : globalThis);
