/*
 * Dashboard Studio — pure, framework-free core logic for the visual editor.
 * No DOM, no Frappe, no dependencies, so it runs in the browser AND under Node
 * (see studio_core.test.js). UMD-style export.
 */
(function (root) {
  "use strict";

  // Mirrors the DS Chart `chart_type` Select options.
  var CHART_TYPES = [
    "KPI Card", "Bar Chart", "Line Chart", "Donut Chart", "Table", "Trend Chart",
    "Gauge", "Funnel", "Lifecycle", "Flow", "Matrix", "Radar", "Decision Diagram",
    "Network Diagram", "Reconciliation Diagram", "Maturity Ladder", "Risk Matrix",
  ];

  // Mirrors DS Chart/Metric Filter `operator` options that the query engine
  // actually accepts (like/between are deliberately excluded — the engine
  // rejects them, so the editor should not offer them as valid).
  var OPERATORS = ["=", "!=", ">", "<", ">=", "<="];

  var GRID_COLUMNS = 12;

  function clampInt(value, min, max, fallback) {
    var n = parseInt(value, 10);
    if (isNaN(n)) n = fallback;
    return Math.max(min, Math.min(max, n));
  }

  // Keep a chart's grid box inside sane bounds (0..11 columns, >=1 size).
  function clampLayout(chart) {
    var width = clampInt(chart.width, 1, GRID_COLUMNS, 4);
    var height = clampInt(chart.height, 1, 100, 3);
    var posX = clampInt(chart.pos_x, 0, GRID_COLUMNS - width, 0);
    var posY = clampInt(chart.pos_y, 0, 1000, 0);
    return { pos_x: posX, pos_y: posY, width: width, height: height };
  }

  // Grid box -> inline style fractions (pure; the app turns these into CSS).
  function layoutStyle(chart) {
    var box = clampLayout(chart);
    return {
      left: (box.pos_x / GRID_COLUMNS) * 100 + "%",
      width: (box.width / GRID_COLUMNS) * 100 + "%",
      top: box.pos_y,
      heightRows: box.height,
    };
  }

  // Extract just the persistable layout of every chart, for a bulk save.
  function serializeLayout(charts) {
    return charts.map(function (c) {
      var box = clampLayout(c);
      return { name: c.name, pos_x: box.pos_x, pos_y: box.pos_y, width: box.width, height: box.height };
    });
  }

  // Apply an editor patch to a chart. Returns {ok, chart, error}. Never mutates
  // the input. Validates chart_type against the known set.
  function applyChartEdit(chart, patch) {
    var next = Object.assign({}, chart);
    if (patch.chart_title != null) {
      var title = String(patch.chart_title).trim();
      if (!title) return { ok: false, error: "Chart title cannot be empty" };
      next.chart_title = title;
    }
    if (patch.chart_type != null) {
      if (CHART_TYPES.indexOf(patch.chart_type) === -1) {
        return { ok: false, error: "Unknown chart type: " + patch.chart_type };
      }
      next.chart_type = patch.chart_type;
    }
    if (patch.description != null) next.description = String(patch.description);
    ["pos_x", "pos_y", "width", "height"].forEach(function (k) {
      if (patch[k] != null) next[k] = patch[k];
    });
    Object.assign(next, clampLayout(next));
    return { ok: true, chart: next };
  }

  // Validate a single filter row the way the engine would (supported operators
  // only). Returns {ok, error}.
  function validateFilter(filter) {
    if (!filter.fieldname || !String(filter.fieldname).trim()) {
      return { ok: false, error: "Filter needs a field name" };
    }
    if (OPERATORS.indexOf(filter.operator) === -1) {
      return { ok: false, error: "Operator '" + filter.operator + "' is not supported by the query engine" };
    }
    return { ok: true };
  }

  var api = {
    CHART_TYPES: CHART_TYPES,
    OPERATORS: OPERATORS,
    GRID_COLUMNS: GRID_COLUMNS,
    clampLayout: clampLayout,
    layoutStyle: layoutStyle,
    serializeLayout: serializeLayout,
    applyChartEdit: applyChartEdit,
    validateFilter: validateFilter,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.DSStudioCore = api;
})(typeof window !== "undefined" ? window : globalThis);
