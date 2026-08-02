/*
 * Dashboard Studio — pure, framework-free core logic for the visual editor.
 * No DOM, no Frappe, no dependencies, so it runs in the browser AND under Node
 * (see studio_core.test.js). UMD-style export.
 */
(function (root) {
  "use strict";

  // Mirrors the DS Chart `chart_type` Select options.
  //
  // Which of these Sophia can actually render is NOT one-to-one — three have
  // no plugin at all, and an unknown type silently falls back to a bar chart
  // there. The table is docs/CHART_TYPE_MAPPING.md; recheck it when a type is
  // added here or a registerChartPlugin call changes on the Sophia side.
  var CHART_TYPES = [
    "KPI Card", "Bar Chart", "Line Chart", "Donut Chart", "Table", "Trend Chart",
    "Gauge", "Funnel", "Lifecycle", "Flow", "Matrix", "Radar", "Decision Diagram",
    "Network Diagram", "Reconciliation Diagram", "Maturity Ladder", "Risk Matrix",
  ];

  // Types the receiving platform has NO plugin for. Copy of
  // dashboard_studio/sophia.py; a Python test asserts the two stay equal, the
  // same drift guard CHART_TYPES has against the DS Chart Select.
  //
  // Why this is a constraint and not a note: Sophia's renderChart does
  //   CHART_PLUGINS.get(type) || CHART_PLUGINS.get("bar")
  // so an unknown type is drawn as a BAR CHART with no error anywhere. Offering
  // one of these is offering a chart that silently becomes something else on
  // publication. Reasons and counts: docs/CHART_TYPE_MAPPING.md.
  var UNPUBLISHABLE_CHART_TYPES = ["KPI Card", "Line Chart", "Table"];

  // The five shapes the Visualize step offers as a starting suggestion. Studio
  // does NOT send the type — Insights owns charting — so this is a hint the
  // person carries across, which is why it is not checked against Insights'
  // own chart list. Insights v2's list is not read anywhere in this repo and
  // guessing it would be asserting something unverified.
  var INSIGHTS_CHART_TYPES = [
    { value: "bar", label: "Bar" },
    { value: "line", label: "Line" },
    { value: "donut", label: "Donut" },
    { value: "number", label: "KPI" },
    { value: "table", label: "Table" },
  ];

  // What Studio can fill in that raw SQL cannot say on its own.
  //
  // Everything here is a GUESS until a person edits it — the Visualize step
  // marks each field Guessed/Confirmed on that basis. Only `title` is actually
  // sent: it lives on the Insights Query. The axes and the type are a handoff
  // note for the person to apply in Insights' own editor, because creating the
  // Chart would mean guessing a data_type per column and drawing a wrong chart
  // in another app with no error this side can catch.
  //
  // ponytail: `title` is derived here AND in api/insights.query_title, because
  // the panel needs a title before it calls the server while the endpoint needs
  // one for callers that send none. They are kept in step by hand. The ceiling
  // is a cosmetic mismatch in a default title — no number can differ — so a
  // drift guard would cost more than the fault it prevents.
  // Insights' title is a Frappe Data field, varchar(140). Trimmed here so the
  // field shows what will actually be stored — the server clamps again, and
  // that one is the guard; this one is honesty about it.
  var MAX_TITLE_LENGTH = 140;

  function clampTitle(name) {
    name = String(name == null ? "" : name).split(/\s+/).filter(Boolean).join(" ");
    if (name.length <= MAX_TITLE_LENGTH) return name;
    return name.slice(0, MAX_TITLE_LENGTH - 1).replace(/\s+$/, "") + "…";
  }

  function insightsPrefill(analysis) {
    analysis = analysis || {};
    var doctypes = (analysis.doctypes || []).filter(Boolean);
    var groupBy = (analysis.group_by || []).filter(Boolean);
    var aggregations = analysis.aggregations || [];
    var first = aggregations[0] || {};
    var fn = String(first.function || "").toUpperCase();
    var argument = String(first.argument || "").replace(/[`\s]/g, "");

    var title;
    if (doctypes.length === 1 && groupBy.length && fn) {
      title = fn.charAt(0) + fn.slice(1).toLowerCase() + " of " + doctypes[0] + " by " + groupBy[0];
    } else if (doctypes.length === 1) {
      title = doctypes[0] + " query";
    } else if (doctypes.length > 1) {
      // The base table plus a count of the rest. Concatenating three names was
      // fine for hand-written SQL and useless for Metabase-compiled MBQL, where
      // a dozen generated join aliases make a title that is both unreadable and
      // over Insights' 140-character limit.
      title = doctypes.slice().sort()[0] + " + " + (doctypes.length - 1) + " more";
    } else {
      title = "Imported SQL query";
    }
    title = clampTitle(title);

    return {
      title: title,
      // The GROUP BY column and the aggregate column — the two things a chart
      // needs and a SELECT does not label as such.
      x_axis: groupBy[0] || "",
      y_axis: fn === "COUNT" && (argument === "*" || !argument) ? "count" : argument,
      // A second GROUP BY column is the colour breakdown — Insights' `split_by`,
      // one bar per x value split into a coloured segment per series value.
      // Only ever the SECOND: the first is the axis, and a query grouped by one
      // column has no series, which is different from having an empty one.
      series: groupBy[1] || "",
      chart_type: suggestedChartType(analysis),
    };
  }

  // A Metabase card's own settings win over anything guessed from its SQL.
  //
  // The guesses exist because pasted SQL is all there was. When the card itself
  // says what its title, axes and chart type are, that is not a better guess —
  // it is the answer, so those fields come back Confirmed rather than Guessed.
  // A blank falls back to the guess: describe_card drops an axis that names a
  // column the card no longer returns, and a guess beats an empty box.
  function mergeImportedFields(prefill, imported) {
    prefill = prefill || {};
    imported = imported || {};
    var out = { fields: {}, confirmed: {} };
    ["title", "x_axis", "y_axis", "series", "chart_type"].forEach(function (key) {
      var value = imported[key];
      if (value) {
        out.fields[key] = value;
        out.confirmed[key] = true;
      } else {
        out.fields[key] = prefill[key] || "";
      }
    });
    return out;
  }

  // One Insights operation, in a line a person can check against Metabase.
  // Reading the operations back is how somebody spots a wrong translation
  // BEFORE running it, so this names columns and values rather than counting.
  function describeOperation(op) {
    op = op || {};
    if (op.type === "source") return (op.table || {}).table_name || "";
    if (op.type === "filter") {
      return ((op.column || {}).column_name || "?") + " " + (op.operator || "?") +
        " " + JSON.stringify(op.value);
    }
    if (op.type === "join") {
      var on = op.join_condition || {};
      return (op.join_type || "") + " join " + ((op.table || {}).table_name || "?") +
        " on " + ((on.left_column || {}).column_name || "?") + " = " +
        ((on.right_column || {}).column_name || "?");
    }
    if (op.type === "summarize") {
      var by = (op.dimensions || []).map(function (d) { return d.column_name; });
      return (op.measures || []).map(function (m) {
        return m.aggregation + "(" + m.column_name + ")";
      }).join(", ") + (by.length ? " by " + by.join(", ") : "");
    }
    return op.type || "";
  }

  function suggestedChartType(analysis) {
    analysis = analysis || {};
    var groupBy = (analysis.group_by || []).filter(Boolean);
    var aggregations = analysis.aggregations || [];
    // One number and nothing to break it down by is a KPI, not a bar of one.
    if (!groupBy.length && aggregations.length === 1) return "number";
    // One or two dimensions with one aggregate is a bar: the first is the axis
    // and the second, if any, is the colour breakdown. Two used to fall through
    // to "table" because there was nowhere to put the second dimension.
    if (groupBy.length <= 2 && groupBy.length && aggregations.length === 1) return "bar";
    // Three or more dimensions, or nothing aggregated, is a list — a chart has
    // an axis and a colour and nothing else to spend a dimension on, so "bar"
    // would be a suggestion that cannot be drawn from what the query returns.
    return "table";
  }

  // Guessed / Confirmed / Not detected, decided in one place so the field and
  // the preview cannot disagree about whether there is an axis.
  //
  // "Not detected" is a third state on purpose. A join with no outer GROUP BY
  // yields no dimension and no aggregate to read, and labelling an empty box
  // "Guessed" claims a guess that was never made — the same over-claim this app
  // refuses everywhere else.
  function axisState(value, confirmed) {
    if (!String(value == null ? "" : value).trim()) return "missing";
    return confirmed ? "confirmed" : "guessed";
  }

  // Why a chart cannot show live data, decided BEFORE asking the server.
  //
  // The engine refuses a metric that is not Approved, or whose calculation is
  // not Count, by raising. Those refusals are right, but they arrive in the
  // browser as Frappe's raw traceback dialog, and a .catch cannot suppress that
  // — it runs after Frappe has already shown it. So the card checks first and
  // does not make a call it knows will fail.
  //
  // Returns null when there is nothing blocking, i.e. go ahead and fetch.
  function chartBlockReason(chart) {
    chart = chart || {};
    if (!chart.metric) {
      return { title: "No metric linked",
               hint: "Select this card and link a metric in the panel on the right." };
    }
    if (chart.metric_missing) {
      return { title: "Metric not found",
               hint: "This card points at “" + chart.metric + "”, which no longer exists. " +
                     "Link a different metric in the panel on the right." };
    }
    // Absent status means an older payload that did not carry one. Say nothing
    // and let the fetch decide, rather than inventing a refusal.
    var status = chart.metric_status;
    if (status && status !== "Approved") {
      return { title: "Metric not yet approved",
               hint: status === "Deprecated"
                 ? "“" + chart.metric + "” is Deprecated, so it no longer runs. " +
                   "Link a current metric, or restore this one in the DS Metric list."
                 : "“" + chart.metric + "” is still " + status + ". Approve it in the " +
                   "DS Metric list to see live data here." };
    }
    var calc = chart.metric_calculation;
    if (calc && String(calc).toLowerCase() !== "count") {
      return { title: "Metric cannot run yet",
               hint: "“" + chart.metric + "” is a " + calc + " metric, and only Count " +
                     "metrics can be executed today." };
    }
    return null;
  }

  // One option list, used by every place a chart type can be chosen, so the rule
  // cannot be enforced in the picker and forgotten in the palette.
  //
  // `current` is never disabled: an existing KPI Card must stay editable and
  // must not be silently retyped by a picker that refuses to show what it is.
  // The publish gate is what refuses it, and it names the chart.
  function chartTypeOptions(current, drawable) {
    var canDraw = drawable || null;
    return CHART_TYPES.map(function (type) {
      var blocked = UNPUBLISHABLE_CHART_TYPES.indexOf(type) !== -1 && type !== current;
      var label = type;
      if (UNPUBLISHABLE_CHART_TYPES.indexOf(type) !== -1) {
        label += type === current ? " — cannot be published" : " — not publishable";
      } else if (canDraw && canDraw.indexOf(type) === -1) {
        label += " — no chart yet";
      }
      return {
        value: type,
        label: label,
        disabled: blocked,
        selected: type === current,
        reason: UNPUBLISHABLE_CHART_TYPES.indexOf(type) !== -1
          ? "The receiving platform has no plugin for this type — it would be " +
            "drawn as a bar chart with no warning. See docs/CHART_TYPE_MAPPING.md."
          : null,
      };
    });
  }

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
    if (patch.sort_order != null) {
      if (SORT_ORDERS.indexOf(patch.sort_order) === -1) {
        return { ok: false, error: "Unknown result order: " + patch.sort_order };
      }
      next.sort_order = patch.sort_order;
    }
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

  // What a query measured, for the node card. Two queries on the same table
  // grouped by different fields produced identical cards; this is the one line
  // that tells them apart, and it is already in the analysis.
  //
  // Display only — serializeCanvasNodes drops it, so nothing new is persisted.
  function describeMeasure(analysis) {
    var a = analysis || {};
    if (!a.supported) return "not translated";
    var agg = (a.aggregations || [])[0];
    var fn = agg && agg.function
      ? agg.function.charAt(0) + agg.function.slice(1).toLowerCase()
      : "";
    var by = (a.group_by || [])[0];
    if (fn && by) return fn + " by " + by;
    if (fn) return fn;
    return by ? "grouped by " + by : "";
  }

  // Lay out analyze_sql output as Source Table nodes (left) and candidate
  // DocTypes as Target DocType nodes (right). analyze_sql returns DocType-ified
  // names, so the source label restores the physical `tab` prefix.
  function analysisToNodes(analysis, targetDoctypes) {
    var nodes = [];
    var measure = describeMeasure(analysis);
    ((analysis || {}).doctypes || []).forEach(function (dt, i) {
      nodes.push({
        node_id: "src:tab" + dt, node_type: "Source Table",
        label: "tab" + dt, measure: measure, pos_x: 20, pos_y: 16 + i * 64,
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

  // Every source table the canvas knows about, with its mapping if it has one.
  //
  // The panel used to render `mappings` alone. The server withholds suggestions
  // for any query it could not translate — correctly, flag-don't-guess — while
  // applyAnalysis still adds a node for every table found. So the canvas grew
  // and the panel did not, and a second and third query were invisible there.
  // One list, derived from the canvas, keeps the two in agreement.
  function mappingRows(nodes, mappings) {
    var byTable = {};
    (mappings || []).forEach(function (m) { byTable[m.external_table] = m; });
    var rows = [];
    var seen = {};
    (nodes || []).forEach(function (n) {
      if (!n || n.node_type !== "Source Table" || !n.label || seen[n.label]) return;
      seen[n.label] = true;
      rows.push(byTable[n.label] || {
        external_table: n.label, target_doctype: "", mapping_status: "Unmapped",
      });
    });
    // A mapping whose source node is gone is still real data — never drop it.
    (mappings || []).forEach(function (m) {
      if (!seen[m.external_table]) { seen[m.external_table] = true; rows.push(m); }
    });
    return rows;
  }

  // What survives "Clear canvas". Confirmed mappings and their nodes are work
  // someone did on purpose; everything else came from a query and can be
  // re-analysed for free. Returns {nodes, mappings, keptConfirmed}.
  function clearedCanvas(nodes, mappings) {
    var confirmed = (mappings || []).filter(function (m) {
      return m.mapping_status === "Confirmed";
    });
    var keep = {};
    confirmed.forEach(function (m) {
      keep["src:" + m.external_table] = true;
      keep["tgt:" + m.target_doctype] = true;
    });
    return {
      nodes: (nodes || []).filter(function (n) { return keep[n.node_id]; }),
      mappings: confirmed,
      keptConfirmed: confirmed.length,
    };
  }

  // DocTypes worth suggesting as a mapping target: the ones already on the
  // canvas, plus the source DocType of every metric this app knows about.
  //
  // Suggestions only — the control is an <input list>, not a select, because
  // this list cannot be complete: there is no endpoint that enumerates every
  // DocType on the site, and a closed list would lock someone out of the right
  // answer. DS Data Mapping.target_doctype is a Link, so Frappe refuses a name
  // that does not exist; the client suggests, the server validates.
  function targetSuggestions(nodes, metrics) {
    var seen = {};
    (nodes || []).forEach(function (n) {
      if (n && n.node_type === "Target DocType" && n.label) seen[n.label] = true;
    });
    (metrics || []).forEach(function (m) {
      if (m && m.source_doctype) seen[m.source_doctype] = true;
    });
    return Object.keys(seen).sort();
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

  // The left rail's Data catalogue: which source DocTypes this dashboard's
  // charts actually draw on, and how many charts use each.
  //
  // The subtitle is a chart count, NOT a field count. The mockup shows
  // "43 fields · live", which needs live DocType metadata this app does not
  // have — inventing it would be a confident wrong number on an audit tool.
  //
  // `resolve` maps a metric name to its record; a chart whose metric is not in
  // the list yet (still loading, or no longer executable) is skipped rather
  // than filed under a guessed source.
  function dashboardSources(charts, resolve, query) {
    var counts = {};
    (charts || []).forEach(function (chart) {
      var source = ((resolve && resolve(chart.metric)) || {}).source_doctype;
      if (!source) return;
      counts[source] = (counts[source] || 0) + 1;
    });
    var needle = String(query || "").trim().toLowerCase();
    return Object.keys(counts)
      .filter(function (s) { return !needle || s.toLowerCase().indexOf(needle) !== -1; })
      .sort()
      .map(function (source) {
        return {
          source: source,
          glyph: sourceGlyph(source),
          charts: counts[source],
          subtitle: counts[source] === 1 ? "1 chart" : counts[source] + " charts",
        };
      });
  }

  // Two letters, from the initials of the first two words, else the first two
  // characters. Text, not an icon set.
  function sourceGlyph(name) {
    var words = String(name || "").trim().split(/\s+/).filter(Boolean);
    if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
    return String(name || "?").slice(0, 2).toUpperCase();
  }

  // Width, as the mockup's percentage select over the 12-column grid. No new
  // field: these are DS Chart.width values, labelled as the fraction they are.
  //
  // Drag-resize can leave a width the presets do not contain, so the current
  // value is always offered — otherwise opening the panel on a 7-wide card and
  // saving would silently resize it.
  var WIDTH_PRESETS = [[3, "25%"], [4, "33%"], [6, "50%"], [12, "100%"]];

  function widthOptions(current) {
    var width = Number(current);
    var out = WIDTH_PRESETS.map(function (p) { return { value: p[0], label: p[1] }; });
    if (width > 0 && !WIDTH_PRESETS.some(function (p) { return p[0] === width; })) {
      out.push({ value: width, label: width + " of 12 (custom)" });
      out.sort(function (a, b) { return a.value - b.value; });
    }
    return out;
  }

  // The toolbar readiness chip: one line answering "what stage am I at, and what
  // is blocking me", from the server's publish_readiness payload.
  //
  // Assembly only — every fact here is computed by publish_readiness, the same
  // function the publish gate throws on. Nothing in this file decides whether a
  // dashboard is publishable, and nothing here should ever start to: a chip that
  // disagreed with the gate would say ready and then refuse.
  function readinessChip(readiness, status) {
    if (!readiness) return null;
    var stage = status || "Draft";
    var blockers = readiness.blockers || [];

    if (!blockers.length) {
      return {
        tone: "ready",
        text: stage === "Published" ? stage : stage + " · ready to publish",
        detail: "Nothing is blocking publication.",
      };
    }
    // One blocker is named; several would not fit, so the first is named and the
    // rest counted. The full list is on Governance, which the chip links to.
    var text = stage + " · " + blockers[0].summary;
    if (blockers.length > 1) text += ", +" + (blockers.length - 1) + " more";
    return {
      tone: "blocked",
      text: text,
      detail: blockers.map(function (b) { return b.summary; }).join("\n"),
    };
  }

  // Display order for one chart's result rows (DS Chart.sort_order).
  //
  // Presentation only. It never changes a value, only the order they are drawn
  // in, so it is applied at render rather than in the query engine: the engine
  // is scoped to a DS Metric, and one approved metric is drawn by many charts
  // that may each want a different order. Anything unrecognised — including a
  // chart saved before the field existed — sorts ascending, which is exactly
  // what execute_query_plan already returns, so no existing chart moves.
  var SORT_ORDERS = ["Ascending", "Descending", "Highest first"];

  function sortResultRows(rows, order) {
    var list = (rows || []).slice(); // never reorder the shared result cache
    if (!list.length) return list;
    var dimension = dimensionKey(list[0]);

    if (order === "Highest first") {
      return list.sort(function (a, b) { return (b.count || 0) - (a.count || 0); });
    }
    // Nulls last in both directions: a missing dimension is not a low value.
    var descending = order === "Descending";
    return list.sort(function (a, b) {
      var left = a[dimension], right = b[dimension];
      if (left == null || right == null) return (left == null) - (right == null);
      // Mixed types (2024 and "2023") are not reliably comparable; compare as
      // text rather than throwing, matching the engine's own fallback.
      if (typeof left !== typeof right) { left = String(left); right = String(right); }
      if (left === right) return 0;
      return (left < right ? -1 : 1) * (descending ? -1 : 1);
    });
  }

  // The dimension is whichever key is not the count — the shape the engine returns.
  function dimensionKey(row) {
    var keys = Object.keys(row || {}).filter(function (k) { return k !== "count"; });
    return keys[0];
  }

  // The DS Dashboard record form for a dashboard. Names are titles (the DocType
  // is autonamed field:dashboard_title), so they routinely contain spaces and
  // may contain a slash — both have to be encoded or the path breaks.
  function dashboardFormUrl(name) {
    return "/app/ds-dashboard/" + encodeURIComponent(name);
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
    var added = 0;
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
      added += 1;
    });
    // The count travels with the list: re-analysing a query that suggests
    // mappings already present is a no-op, and the panel has to be able to say
    // that rather than looking like it ignored the query.
    merged.added = added;
    return merged;
  }

  // Add newly discovered nodes without moving ones already on the canvas — a
  // re-analysis must not undo the arrangement someone has made.
  // Add nodes a new analysis discovered, keeping everything already placed.
  //
  // Incoming positions are RE-COMPUTED, not trusted: analysisToNodes numbers
  // from 0 within its own analysis, so every analysis puts its first source node
  // at y=16. Appending them verbatim stacked each new query's nodes exactly on
  // top of the previous query's — which read as "the canvas is stale", and made
  // an older mapping's line appear to connect the newer pair sitting on those
  // coordinates. Place them below what is already there instead.
  function mergeNodes(existing, incoming) {
    var merged = (existing || []).slice();
    var seen = {};
    var bottom = {};
    merged.forEach(function (n) {
      seen[n.node_id] = true;
      bottom[n.node_type] = Math.max(bottom[n.node_type] || 0, (n.pos_y || 0) + 64);
    });
    (incoming || []).forEach(function (n) {
      if (!n || !n.node_id) return;
      if (seen[n.node_id]) {
        // Already placed: keep its position, but take the newer query's measure
        // or the card would still describe the query before last.
        if (n.measure) {
          merged.forEach(function (m) { if (m.node_id === n.node_id) m.measure = n.measure; });
        }
        return;
      }
      seen[n.node_id] = true;
      var y = bottom[n.node_type] || 16;
      bottom[n.node_type] = y + 64;
      merged.push(Object.assign({}, n, { pos_y: y }));
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
    UNPUBLISHABLE_CHART_TYPES: UNPUBLISHABLE_CHART_TYPES,
    chartTypeOptions: chartTypeOptions,
    chartBlockReason: chartBlockReason,
    INSIGHTS_CHART_TYPES: INSIGHTS_CHART_TYPES,
    insightsPrefill: insightsPrefill,
    describeOperation: describeOperation,
    clampTitle: clampTitle,
    mergeImportedFields: mergeImportedFields,
    axisState: axisState,
    suggestedChartType: suggestedChartType,
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
    dashboardFormUrl: dashboardFormUrl,
    sortResultRows: sortResultRows,
    readinessChip: readinessChip,
    widthOptions: widthOptions,
    targetSuggestions: targetSuggestions,
    mappingRows: mappingRows,
    describeMeasure: describeMeasure,
    clearedCanvas: clearedCanvas,
    dashboardSources: dashboardSources,
    sourceGlyph: sourceGlyph,
    SORT_ORDERS: SORT_ORDERS,
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
