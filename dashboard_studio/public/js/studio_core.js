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
    if (patch.metric != null) next.metric = String(patch.metric);
    ["pos_x", "pos_y", "width", "height"].forEach(function (k) {
      if (patch[k] != null) next[k] = patch[k];
    });
    Object.assign(next, clampLayout(next));
    return { ok: true, chart: next };
  }

  // A filter row the editor may modify: Static, with an operator the engine
  // executes (or none yet). Dynamic rows and like/between rows are preserved
  // read-only — the engine rejects them, so the editor must not produce them.
  function isFilterEditable(filter) {
    var isStatic = (filter.filter_type || "Static") === "Static";
    var opOk = !filter.operator || OPERATORS.indexOf(filter.operator) !== -1;
    return isStatic && opOk;
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

  // ---- Mapping view core (pure) ----

  // Mirrors DS Data Mapping's mapping_status options.
  var MAPPING_STATUSES = ["Suggested", "Confirmed", "Rejected", "Missing"];

  // Click-cycle for a mapping row. "Missing" is set by absence, not clicking,
  // so it is not in the cycle; any unknown status resets to Suggested.
  function nextMappingStatus(status) {
    var cycle = ["Suggested", "Confirmed", "Rejected"];
    return cycle[(cycle.indexOf(status) + 1) % cycle.length];
  }

  // DS Data Mapping record shape (table-level; data_source attached server-side).
  function buildMapping(externalTable, targetDoctype) {
    return {
      external_table: externalTable,
      target_doctype: targetDoctype,
      mapping_status: "Suggested",
    };
  }

  // DS Canvas Node child-row shape.
  function serializeCanvasNodes(nodes) {
    return nodes.map(function (n) {
      return {
        node_id: n.node_id,
        node_type: n.node_type,
        pos_x: Math.round(n.pos_x) || 0,
        pos_y: Math.round(n.pos_y) || 0,
      };
    });
  }

  // Lay out analyze_sql output as Source Table nodes (left) and candidate
  // DocTypes as Target DocType nodes (right). analyze_sql returns DocType-ified
  // names, so the source label restores the physical `tab` prefix.
  function analysisToNodes(analysis, targetDoctypes) {
    var nodes = [];
    ((analysis || {}).doctypes || []).forEach(function (dt, i) {
      nodes.push({
        node_id: "src:tab" + dt, node_type: "Source Table",
        label: "tab" + dt, pos_x: 20, pos_y: 16 + i * 64,
      });
    });
    (targetDoctypes || []).forEach(function (dt, i) {
      nodes.push({
        node_id: "tgt:" + dt, node_type: "Target DocType",
        label: dt, pos_x: 340, pos_y: 16 + i * 64,
      });
    });
    return nodes;
  }

  var api = {
    CHART_TYPES: CHART_TYPES,
    OPERATORS: OPERATORS,
    GRID_COLUMNS: GRID_COLUMNS,
    MAPPING_STATUSES: MAPPING_STATUSES,
    clampLayout: clampLayout,
    layoutStyle: layoutStyle,
    serializeLayout: serializeLayout,
    applyChartEdit: applyChartEdit,
    validateFilter: validateFilter,
    isFilterEditable: isFilterEditable,
    nextMappingStatus: nextMappingStatus,
    buildMapping: buildMapping,
    serializeCanvasNodes: serializeCanvasNodes,
    analysisToNodes: analysisToNodes,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.DSStudioCore = api;
})(typeof window !== "undefined" ? window : globalThis);
