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
    // section may legitimately be cleared back to Ungrouped, so "" and null count.
    if ("section" in patch) next.section = patch.section || null;
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

  // ---- Data & DocTypes ----

  // Group schema edges by the DocType they start from, for a readable graph.
  // Child (Table) edges are listed before Link edges because they describe
  // ownership rather than a reference.
  function groupRelationships(edges) {
    var bySource = {};
    (edges || []).forEach(function (edge) {
      if (!edge || !edge.source) return;
      (bySource[edge.source] = bySource[edge.source] || []).push(edge);
    });
    return Object.keys(bySource).sort().map(function (source) {
      var list = bySource[source].slice().sort(function (a, b) {
        if (a.kind !== b.kind) return a.kind === "child" ? -1 : 1;
        return String(a.fieldname).localeCompare(String(b.fieldname));
      });
      return { source: source, edges: list };
    });
  }

  // ---- Validation Centre ----

  var VALIDATION_STATUSES = ["Match", "Discrepancy", "Flagged", "Accepted"];

  // Tally comparisons by status. Statuses outside the known set are counted
  // under "other" rather than silently dropped.
  function validationSummary(rows) {
    var summary = { Match: 0, Discrepancy: 0, Flagged: 0, Accepted: 0, other: 0, total: 0 };
    (rows || []).forEach(function (row) {
      var status = row && row.status;
      summary.total += 1;
      if (VALIDATION_STATUSES.indexOf(status) === -1) summary.other += 1;
      else summary[status] += 1;
    });
    return summary;
  }

  // A comparison can only be accepted by a person, and only when there is a
  // real difference to accept — mirrors the server's rule so the button is not
  // offered where the server would refuse.
  function canAccept(row) {
    if (!row) return false;
    return row.status === "Discrepancy" || row.status === "Flagged";
  }

  // Parse a reference result pasted from the source system into the row shape
  // the comparison engine indexes: {<label>, count}. One "label,value" per line,
  // splitting on the LAST comma so labels may contain commas.
  //
  // A blank value is kept blank: an unknown figure must reach the comparison as
  // unknown, so it is Flagged, rather than being read as zero and matching one.
  // A line that cannot be read is reported, never guessed at.
  function parseReferenceRows(text) {
    var rows = [];
    var errors = [];
    String(text == null ? "" : text).split("\n").forEach(function (raw, i) {
      var line = raw.trim();
      if (!line) return;
      var cut = line.lastIndexOf(",");
      if (cut === -1) {
        errors.push("line " + (i + 1) + ': no comma — expected "group, value"');
        return;
      }
      var label = line.slice(0, cut).trim();
      if (!label) {
        errors.push("line " + (i + 1) + ": no group name before the comma");
        return;
      }
      rows.push({ label: label, count: line.slice(cut + 1).trim() });
    });
    return { rows: rows, errors: errors };
  }

  // ---- Dashboard picker ----
  //
  // Scale features switch on only past a threshold, so a short list stays a
  // short list: no search box, no group headers, no reason to read twice.
  var PICKER_SCALE_THRESHOLD = 8; // above this — 9 or more — search + grouping
  var PICKER_RECENT_COUNT = 5;

  function dashboardTitle(d) {
    return String((d && (d.dashboard_title || d.name)) || "");
  }

  // Shape the picker's contents for a given list and search query.
  //
  // Groups are "Recent" (the order list_dashboards already returns, which is
  // last-modified, so it costs nothing) then "All dashboards" alphabetically —
  // predictable beats clever once a list is long enough to scan. While a search
  // is active the groups collapse to a single flat list: they help browsing and
  // get in the way of narrowing.
  function pickerModel(dashboards, options) {
    var list = (dashboards || []).slice();
    var opts = options || {};
    var total = list.length;
    var searchable = total > PICKER_SCALE_THRESHOLD;
    // A list too short to have a search box cannot be filtered.
    var query = searchable ? String(opts.query || "").trim() : "";
    var groups;

    if (query) {
      var needle = query.toLowerCase();
      groups = [{
        title: null,
        items: list.filter(function (d) {
          return dashboardTitle(d).toLowerCase().indexOf(needle) !== -1;
        }),
      }];
    } else if (searchable) {
      groups = [
        { title: "Recent", items: list.slice(0, PICKER_RECENT_COUNT) },
        {
          title: "All dashboards",
          items: list.slice().sort(function (a, b) {
            return dashboardTitle(a).localeCompare(dashboardTitle(b));
          }),
        },
      ];
    } else {
      groups = [{ title: null, items: list }];
    }

    return {
      groups: groups,
      total: total,
      // What the footer reports: while filtering this is the match count, so a
      // narrowed list never reads as a short one.
      shown: query ? groups[0].items.length : total,
      searchable: searchable,
      query: query,
    };
  }

  // Every row the picker will render, in display order. This is what the
  // keyboard walks — group headers are labels, not stops. A dashboard listed
  // under both Recent and All appears twice, because it is two rows on screen.
  function pickerRows(model) {
    var rows = [];
    ((model && model.groups) || []).forEach(function (g) {
      (g.items || []).forEach(function (d) { rows.push(d); });
    });
    return rows;
  }

  // Move a section one place up or down. Returns the reordered names, or null
  // if the move is a no-op (already at the end it is moving toward), so the
  // caller can skip a pointless save.
  function moveSection(sections, name, delta) {
    var names = (sections || []).map(function (s) { return s.name; });
    var from = names.indexOf(name);
    var to = from + delta;
    if (from === -1 || to < 0 || to >= names.length) return null;
    names.splice(to, 0, names.splice(from, 1)[0]);
    return names;
  }

  // Group charts under their sections for the Design view.
  //
  // Sections are ordered by the server (sort_order); charts with no section, or
  // pointing at a section that no longer exists, fall into a trailing Ungrouped
  // band rather than disappearing. Returns [] when there are no sections at all,
  // so the caller can keep rendering a single flat canvas as before.
  function groupChartsBySection(charts, sections) {
    if (!sections || !sections.length) return [];
    var bands = sections.map(function (s) {
      return {
        name: s.name,
        title: s.section_title || s.name,
        collapsed: !!s.is_collapsed_default,
        charts: [],
      };
    });
    var byName = {};
    bands.forEach(function (band) { byName[band.name] = band; });

    var ungrouped = { name: null, title: "Ungrouped", collapsed: false, charts: [] };
    (charts || []).forEach(function (chart) {
      var band = chart.section ? byName[chart.section] : null;
      (band || ungrouped).charts.push(chart);
    });

    if (ungrouped.charts.length) bands.push(ungrouped);
    return bands;
  }

  // Add suggested mappings without disturbing what is already there: an existing
  // row keeps its status (a Confirmed or Rejected decision must not be reset to
  // Suggested by re-analyzing the same SQL).
  function mergeMappings(existing, incoming) {
    var merged = (existing || []).slice();
    var seen = {};
    merged.forEach(function (m) { seen[m.external_table + " " + m.target_doctype] = true; });
    (incoming || []).forEach(function (m) {
      if (!m || !m.external_table || !m.target_doctype) return;
      var key = m.external_table + " " + m.target_doctype;
      if (seen[key]) return;
      seen[key] = true;
      merged.push({
        external_table: m.external_table,
        target_doctype: m.target_doctype,
        mapping_status: m.mapping_status || "Suggested",
      });
    });
    return merged;
  }

  // Add newly discovered nodes without moving ones already on the canvas — a
  // re-analysis must not undo the arrangement someone has made.
  function mergeNodes(existing, incoming) {
    var merged = (existing || []).slice();
    var seen = {};
    merged.forEach(function (n) { seen[n.node_id] = true; });
    (incoming || []).forEach(function (n) {
      if (!n || !n.node_id || seen[n.node_id]) return;
      seen[n.node_id] = true;
      merged.push(n);
    });
    return merged;
  }

  // Rebuild the mapping canvas from persisted data: saved node positions first,
  // then any node implied by a mapping that has no saved position yet (so a
  // mapping made elsewhere still shows up). Labels come from the node_id.
  function nodesFromProject(canvasNodes, mappings) {
    var nodes = [];
    var seen = {};
    var counts = { "Source Table": 0, "Target DocType": 0 };

    (canvasNodes || []).forEach(function (n) {
      var id = n && n.node_id;
      if (!id || seen[id]) return;
      seen[id] = true;
      counts[n.node_type] = (counts[n.node_type] || 0) + 1;
      nodes.push({
        node_id: id,
        node_type: n.node_type,
        label: String(id).replace(/^(src|tgt):/, ""),
        pos_x: n.pos_x || 0,
        pos_y: n.pos_y || 0,
      });
    });

    (mappings || []).forEach(function (m) {
      [
        ["src:" + m.external_table, "Source Table", m.external_table, 20],
        ["tgt:" + m.target_doctype, "Target DocType", m.target_doctype, 340],
      ].forEach(function (spec) {
        var id = spec[0], type = spec[1], label = spec[2], x = spec[3];
        if (!label || seen[id]) return;
        seen[id] = true;
        var index = counts[type] || 0;
        counts[type] = index + 1;
        nodes.push({ node_id: id, node_type: type, label: label, pos_x: x, pos_y: 16 + index * 64 });
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
    nodesFromProject: nodesFromProject,
    groupChartsBySection: groupChartsBySection,
    groupRelationships: groupRelationships,
    validationSummary: validationSummary,
    canAccept: canAccept,
    parseReferenceRows: parseReferenceRows,
    pickerModel: pickerModel,
    pickerRows: pickerRows,
    dashboardTitle: dashboardTitle,
    PICKER_SCALE_THRESHOLD: PICKER_SCALE_THRESHOLD,
    PICKER_RECENT_COUNT: PICKER_RECENT_COUNT,
    VALIDATION_STATUSES: VALIDATION_STATUSES,
    moveSection: moveSection,
    mergeMappings: mergeMappings,
    mergeNodes: mergeNodes,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.DSStudioCore = api;
})(typeof window !== "undefined" ? window : globalThis);
