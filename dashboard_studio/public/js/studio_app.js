/*
 * Dashboard Studio — visual editor (Design view + diagram editor).
 *
 * Browser-only DOM layer. Pure logic lives in studio_core.js; mock records in
 * studio_mock.js. Uses Frappe (frappe.call / frappe.show_alert) when available,
 * and falls back to MOCK data otherwise.
 *
 * ⚠️  NOT YET VERIFIED IN A LIVE FRAPPE DESK — no Bench was available when this
 * was written. The pure logic is covered by studio_core.test.js; the DOM/drag/
 * save wiring has been reviewed but not run against a real site.
 */
(function (root) {
  "use strict";

  var core = root.DSStudioCore;
  var ROW_H = 44; // px per grid row
  var PENDING = "__pending__"; // in-flight marker in the metric result cache

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function hasFrappe() {
    return typeof root.frappe !== "undefined" && root.frappe && typeof root.frappe.call === "function";
  }

  function toast(msg) {
    if (hasFrappe() && root.frappe.show_alert) root.frappe.show_alert({ message: msg, indicator: "blue" });
    else if (root.console) root.console.log("[Dashboard Studio] " + msg);
  }

  function App(mountPoint, options) {
    this.mount = mountPoint;
    this.options = options || {};
    this.state = {
      dashboard: null, charts: [], selected: null, mock: false,
      // Arriving with ?project= means the caller came from a DS Migration
      // Project, so open straight into the Mapping view.
      view: this.options.project ? "mapping" : "design",
      // Mapping view state, built lazily on first open.
      mapNodes: null, mappings: [], pickedSource: null,
    };
  }

  App.prototype.load = function () {
    var self = this;
    var name = this.options.dashboard;
    if (hasFrappe() && name) {
      root.frappe.call({
        method: "dashboard_studio.api.studio.get_studio_dashboard",
        args: { dashboard: name },
      }).then(function (r) {
        var data = r.message || {};
        self.state.dashboard = data.dashboard;
        self.state.charts = data.charts || [];
        self.state.mock = false;
        self.render();
      }).catch(function () {
        self.useMock();
      });
    } else {
      this.useMock();
    }
  };

  App.prototype.useMock = function () {
    var mock = (root.DSStudioMock || {}).MOCK_DASHBOARD || { charts: [] };
    this.state.dashboard = mock;
    this.state.charts = mock.charts.map(function (c) { return Object.assign({}, c); });
    this.state.mock = true;
    this.render();
  };

  App.prototype.render = function () {
    var self = this;
    this.mount.innerHTML = "";
    var wrap = el("div", "dss-wrap");

    if (this.state.mock) {
      wrap.appendChild(el("div", "dss-banner", "⚠ Mock data — not connected to a live DS Dashboard. Edits are not persisted."));
    }

    var head = el("div", "dss-toolbar");
    head.appendChild(el("h2", "dss-title", (this.state.dashboard && this.state.dashboard.dashboard_title) || "Dashboard"));

    var views = el("div", "dss-viewtabs");
    ["design", "mapping"].forEach(function (v) {
      var b = el("button", "dss-btn" + (self.state.view === v ? " dss-btn-primary" : ""),
        v === "design" ? "Design" : "Mapping");
      b.addEventListener("click", function () { self.state.view = v; self.render(); });
      views.appendChild(b);
    });
    head.appendChild(views);

    if (this.state.view === "design") {
      var saveAll = el("button", "dss-btn dss-btn-primary", "Save layout");
      saveAll.addEventListener("click", function () { self.saveLayout(); });
      head.appendChild(saveAll);
    }
    wrap.appendChild(head);

    var main = el("div", "dss-main");
    this.canvas = el("div", "dss-canvas");
    this.canvas.style.minHeight = "480px";
    main.appendChild(this.canvas);
    this.panel = el("div", "dss-panel");
    main.appendChild(this.panel);
    wrap.appendChild(main);

    this.mount.appendChild(wrap);
    if (this.state.view === "mapping") {
      this.renderMapping();
    } else {
      this.state.charts.forEach(function (c) { self.renderCard(c); });
      this.fitCanvas();
      this.renderPanel();
    }
  };

  App.prototype.renderCard = function (chart) {
    var self = this;
    var style = core.layoutStyle(chart);
    var card = el("div", "dss-card" + (this.state.selected === chart.name ? " is-selected" : ""));
    card.style.left = style.left;
    card.style.width = style.width;
    card.style.top = style.top * ROW_H + "px";
    card.style.height = style.heightRows * ROW_H + "px";

    var header = el("div", "dss-card-head");
    header.appendChild(el("span", "dss-card-title", chart.chart_title));
    header.appendChild(el("span", "dss-card-type", chart.chart_type || "—"));
    card.appendChild(header);
    var body = el("div", "dss-card-body");
    card.appendChild(body);
    this.renderChartBody(body, chart);

    var resize = el("div", "dss-resize");
    card.appendChild(resize);

    card.addEventListener("mousedown", function (e) {
      if (e.target === resize) return;
      self.select(chart.name);
    });
    this.dragBehavior(header, chart, "move");
    this.dragBehavior(resize, chart, "resize");

    this.canvas.appendChild(card);
  };

  // Draw the chart's actual visual from its metric result rows. Results are
  // cached per metric so drag/resize refreshes never refetch. Mock sessions read
  // MOCK_METRIC_RESULTS; live sessions call run_ds_metric once per metric.
  App.prototype.renderChartBody = function (body, chart) {
    var charts = root.DSStudioCharts;
    if (!chart.metric) {
      body.innerHTML = '<div class="dss-nochart">No metric linked</div>';
      return;
    }
    this._rowsCache = this._rowsCache || {};
    var cached = this._rowsCache[chart.metric];
    // A request is already out for this metric — every re-render would otherwise
    // fire another one (each response triggers a full refresh), so N charts on N
    // metrics would issue O(N^2) calls.
    if (cached === PENDING) {
      body.innerHTML = '<div class="dss-nochart">Loading…</div>';
      return;
    }
    if (cached !== undefined) {
      body.innerHTML = cached === null
        ? '<div class="dss-nochart">Metric failed to run</div>'
        : charts.render(chart.chart_type, cached).html;
      return;
    }
    var self = this;
    if (this.state.mock || !hasFrappe()) {
      var rows = ((root.DSStudioMock || {}).MOCK_METRIC_RESULTS || {})[chart.metric] || [];
      this._rowsCache[chart.metric] = rows;
      body.innerHTML = charts.render(chart.chart_type, rows).html;
      return;
    }
    this._rowsCache[chart.metric] = PENDING;
    body.innerHTML = '<div class="dss-nochart">Loading…</div>';
    root.frappe.call({
      method: "dashboard_studio.api.metrics.run_ds_metric",
      args: { metric_name: chart.metric },
    }).then(function (r) {
      self._rowsCache[chart.metric] = r.message || [];
      // Cache the result either way, but only repaint if the user is still
      // looking at the Design view — otherwise this wipes the Mapping canvas.
      if (self.state.view === "design") self.refresh();
    }).catch(function () {
      self._rowsCache[chart.metric] = null; // remembered failure — no retry loop
      if (self.state.view === "design") self.refresh();
    });
  };

  // Pointer-driven move/resize. Converts px deltas to grid columns/rows via the
  // canvas width; commits through core.clampLayout so boxes stay on the grid.
  App.prototype.dragBehavior = function (handle, chart, mode) {
    var self = this;
    handle.addEventListener("mousedown", function (e) {
      e.preventDefault();
      var startX = e.clientX, startY = e.clientY;
      var colW = self.canvas.clientWidth / core.GRID_COLUMNS;
      var base = { pos_x: chart.pos_x, pos_y: chart.pos_y, width: chart.width, height: chart.height };

      function onMove(ev) {
        var dCol = Math.round((ev.clientX - startX) / colW);
        var dRow = Math.round((ev.clientY - startY) / ROW_H);
        if (mode === "move") {
          chart.pos_x = base.pos_x + dCol;
          chart.pos_y = base.pos_y + dRow;
        } else {
          chart.width = base.width + dCol;
          chart.height = base.height + dRow;
        }
        Object.assign(chart, core.clampLayout(chart));
        self.refresh();
      }
      function onUp() {
        root.removeEventListener("mousemove", onMove);
        root.removeEventListener("mouseup", onUp);
      }
      root.addEventListener("mousemove", onMove);
      root.addEventListener("mouseup", onUp);
    });
  };

  App.prototype.refresh = function () {
    var self = this;
    this.canvas.innerHTML = "";
    this.state.charts.forEach(function (c) { self.renderCard(c); });
    this.fitCanvas();
  };

  // Cards are absolutely positioned, so the canvas does not grow with them and
  // its overflow is hidden — without this, a card dragged past the fixed height
  // simply vanishes. Size the canvas to its lowest card.
  App.prototype.fitCanvas = function () {
    var bottom = 0;
    this.state.charts.forEach(function (chart) {
      var box = core.clampLayout(chart);
      bottom = Math.max(bottom, (box.pos_y + box.height) * ROW_H);
    });
    this.canvas.style.height = Math.max(480, bottom + 8) + "px";
  };

  App.prototype.select = function (name) {
    this.state.selected = name;
    this.refresh();
    this.renderPanel();
  };

  // The diagram editor: edit a chart's properties visually and save them back to
  // the DS Chart record, instead of hand-editing HTML/CSS/JS.
  App.prototype.renderPanel = function () {
    var self = this;
    this.panel.innerHTML = "";
    var chart = this.state.charts.filter(function (c) { return c.name === self.state.selected; })[0];
    if (!chart) {
      this.panel.appendChild(el("p", "dss-hint", "Select a chart to edit its title, type and description."));
      return;
    }

    this.panel.appendChild(el("h3", "dss-panel-title", "Edit chart"));

    var titleInput = el("input", "dss-input");
    titleInput.value = chart.chart_title || "";
    this.panel.appendChild(field("Title", titleInput));

    // Flag the types that have no rendering from count-by-group data, so the
    // choice is informed rather than discovered as a stub on the card.
    var renderable = (root.DSStudioCharts || {}).SUPPORTED_CHART_TYPES || [];
    var typeSelect = el("select", "dss-input");
    core.CHART_TYPES.forEach(function (t) {
      var o = el("option", null, renderable.indexOf(t) === -1 ? t + " — no chart yet" : t);
      o.value = t;
      if (t === chart.chart_type) o.selected = true;
      typeSelect.appendChild(o);
    });
    this.panel.appendChild(field("Chart type", typeSelect));

    var descInput = el("textarea", "dss-input");
    descInput.value = chart.description || "";
    this.panel.appendChild(field("Description", descInput));

    // Metric selection — which DS Metric this chart draws.
    var metricSelect = el("select", "dss-input");
    this.availableMetrics(function (metrics) {
      var names = metrics.map(function (m) { return m.name; });
      metrics.forEach(function (m) {
        // Show what the metric draws on, so the choice is not name-only.
        var o = el("option", null, m.source_doctype ? m.name + " — " + m.source_doctype : m.name);
        o.value = m.name;
        if (m.name === chart.metric) o.selected = true;
        metricSelect.appendChild(o);
      });
      // A chart may already point at something the picker no longer offers
      // (deprecated, or a calculation the engine cannot run) — keep it visible.
      if (chart.metric && names.indexOf(chart.metric) === -1) {
        var cur = el("option", null, chart.metric + " — not currently executable");
        cur.value = chart.metric;
        cur.selected = true;
        metricSelect.appendChild(cur);
      }
    });
    this.panel.appendChild(field("Metric", metricSelect));

    // Layout, editable numerically as well as by drag: drag is imprecise and
    // cannot be driven from the keyboard. Values are clamped by applyChartEdit.
    var layoutWrap = el("div", "dss-layout-row");
    layoutWrap.appendChild(el("span", "dss-field-label", "Layout (column, row, width, height)"));
    var layoutInputs = {};
    var grid = el("div", "dss-layout-grid");
    ["pos_x", "pos_y", "width", "height"].forEach(function (key) {
      var input = el("input", "dss-input");
      input.type = "number";
      input.min = key === "width" || key === "height" ? "1" : "0";
      input.value = chart[key] == null ? "" : chart[key];
      input.setAttribute("aria-label", key);
      layoutInputs[key] = input;
      grid.appendChild(input);
    });
    layoutWrap.appendChild(grid);
    this.panel.appendChild(layoutWrap);

    // Chart filters (DS Chart Filter rows). Static rows with engine-supported
    // operators are editable; Dynamic or like/between rows appear read-only and
    // are preserved unchanged on save — the engine can't execute them yet.
    chart.chart_filters = chart.chart_filters || [];
    var filtersWrap = el("div", "dss-filters");
    filtersWrap.appendChild(el("span", "dss-field-label", "Filters"));
    chart.chart_filters.forEach(function (row, index) {
      if (!core.isFilterEditable(row)) {
        filtersWrap.appendChild(el(
          "div", "dss-filter-locked",
          row.fieldname + " " + row.operator + " " + (row.value || "") +
          "  (" + (row.filter_type || "Static") + " — not yet supported, preserved)"
        ));
        return;
      }
      var line = el("div", "dss-filter-row");
      var f = el("input", "dss-input"); f.placeholder = "field"; f.value = row.fieldname || "";
      f.addEventListener("input", function () { row.fieldname = f.value; });
      var op = el("select", "dss-input");
      core.OPERATORS.forEach(function (o) {
        var opt = el("option", null, o); opt.value = o;
        if (o === row.operator) opt.selected = true;
        op.appendChild(opt);
      });
      op.addEventListener("change", function () { row.operator = op.value; });
      if (!row.operator) row.operator = core.OPERATORS[0];
      var v = el("input", "dss-input"); v.placeholder = "value"; v.value = row.value == null ? "" : row.value;
      v.addEventListener("input", function () { row.value = v.value; });
      var rm = el("button", "dss-btn dss-btn-small", "✕");
      rm.addEventListener("click", function () {
        chart.chart_filters.splice(index, 1);
        self.renderPanel();
      });
      [f, op, v, rm].forEach(function (n) { line.appendChild(n); });
      filtersWrap.appendChild(line);
    });
    var addFilter = el("button", "dss-btn dss-btn-small", "+ Add filter");
    addFilter.addEventListener("click", function () {
      chart.chart_filters.push({ fieldname: "", operator: "=", value: "", filter_type: "Static" });
      self.renderPanel();
    });
    filtersWrap.appendChild(addFilter);
    this.panel.appendChild(filtersWrap);

    var err = el("div", "dss-error");
    this.panel.appendChild(err);

    var actions = el("div", "dss-actions");
    var applyBtn = el("button", "dss-btn", "Apply");
    var saveBtn = el("button", "dss-btn dss-btn-primary", "Save chart");
    actions.appendChild(applyBtn);
    actions.appendChild(saveBtn);
    this.panel.appendChild(actions);

    function collect() {
      var patch = {
        chart_title: titleInput.value,
        chart_type: typeSelect.value,
        description: descInput.value,
        metric: metricSelect.value || chart.metric,
      };
      Object.keys(layoutInputs).forEach(function (key) {
        var raw = layoutInputs[key].value;
        if (raw !== "") patch[key] = parseInt(raw, 10);
      });
      return patch;
    }
    function applyEdit() {
      // Drop editable rows left fully empty, then validate the rest the way the
      // engine would. Read-only (Dynamic/unsupported) rows pass through as-is.
      chart.chart_filters = (chart.chart_filters || []).filter(function (row) {
        return !core.isFilterEditable(row) || (row.fieldname || "").trim() || (row.value || "").trim();
      });
      for (var i = 0; i < chart.chart_filters.length; i++) {
        var row = chart.chart_filters[i];
        if (!core.isFilterEditable(row)) continue;
        var check = core.validateFilter(row);
        if (!check.ok) { err.textContent = check.error; return null; }
      }
      var res = core.applyChartEdit(chart, collect());
      if (!res.ok) { err.textContent = res.error; return null; }
      err.textContent = "";
      Object.assign(chart, res.chart);
      self.refresh();
      return chart;
    }
    applyBtn.addEventListener("click", applyEdit);
    saveBtn.addEventListener("click", function () {
      if (applyEdit()) self.saveChart(chart);
    });
  };

  // ---- Mapping view: source tables -> DocTypes, persisted shapes mocked ----

  App.prototype.renderMapping = function () {
    if (this.state.mapNodes) {
      this.refreshMapping();
      return;
    }
    var self = this;
    if (this.options.project && hasFrappe()) {
      this.canvas.innerHTML = '<div class="dss-nochart">Loading migration project…</div>';
      root.frappe.call({
        method: "dashboard_studio.api.studio.get_migration_project",
        args: { project: this.options.project },
      }).then(function (r) {
        var data = r.message || {};
        self.state.mappings = (data.mappings || []).map(function (m) {
          return {
            external_table: m.external_table,
            target_doctype: m.target_doctype,
            mapping_status: m.mapping_status || "Suggested",
          };
        });
        self.state.mapNodes = core.nodesFromProject(data.canvas_nodes, self.state.mappings);
        if (!self.state.mapNodes.length) self.state.mapNodes = self.mockNodes();
        // Keep the loaded state either way, but only repaint if the user is
        // still on the Mapping view — otherwise this wipes the Design canvas.
        if (self.state.view === "mapping") self.refreshMapping();
      }).catch(function () {
        self.state.mapNodes = self.mockNodes();
        if (self.state.view === "mapping") self.refreshMapping();
      });
      return;
    }
    this.state.mapNodes = this.mockNodes();
    this.refreshMapping();
  };

  // ⚠️ MOCK node set: used with no ?project=, or for a project with nothing
  // saved yet. Feeding real analyze_sql output into a project is a follow-up.
  App.prototype.mockNodes = function () {
    var mock = root.DSStudioMock || {};
    return core.analysisToNodes(mock.MOCK_ANALYSIS, mock.MOCK_TARGET_DOCTYPES);
  };

  App.prototype._node = function (nodeId) {
    return (this.state.mapNodes || []).filter(function (n) { return n.node_id === nodeId; })[0];
  };

  App.prototype.renderMapNode = function (node) {
    var self = this;
    var isSource = node.node_type === "Source Table";
    var div = el("div", "dss-node " + (isSource ? "dss-node-src" : "dss-node-tgt") +
      (this.state.pickedSource === node.node_id ? " is-picked" : ""));
    div.style.left = node.pos_x + "px";
    div.style.top = node.pos_y + "px";
    div.appendChild(el("div", "dss-node-kind", node.node_type));
    div.appendChild(el("div", "dss-node-label", node.label));

    // A drag that ends over the node still fires a click; without this the
    // drag would also pick a source, or silently create a mapping.
    var dragged = false;

    div.addEventListener("click", function () {
      if (dragged) {
        dragged = false;
        return;
      }
      if (isSource) {
        self.state.pickedSource = self.state.pickedSource === node.node_id ? null : node.node_id;
      } else if (self.state.pickedSource) {
        var source = self._node(self.state.pickedSource);
        var externalTable = source.label;
        var exists = self.state.mappings.some(function (m) {
          return m.external_table === externalTable && m.target_doctype === node.label;
        });
        if (!exists) self.state.mappings.push(core.buildMapping(externalTable, node.label));
        self.state.pickedSource = null;
      }
      self.refreshMapping();
    });

    // Pixel drag to reposition; positions persist in DS Canvas Node shape.
    div.addEventListener("mousedown", function (e) {
      var startX = e.clientX, startY = e.clientY;
      var baseX = node.pos_x, baseY = node.pos_y;
      var moved = false;
      dragged = false;
      function onMove(ev) {
        var dx = ev.clientX - startX, dy = ev.clientY - startY;
        if (Math.abs(dx) + Math.abs(dy) > 3) {
          moved = true;
          dragged = true; // consumed by the click handler above
        }
        if (!moved) return;
        node.pos_x = Math.max(0, baseX + dx);
        node.pos_y = Math.max(0, baseY + dy);
        self.refreshMapping();
      }
      function onUp() {
        root.removeEventListener("mousemove", onMove);
        root.removeEventListener("mouseup", onUp);
      }
      root.addEventListener("mousemove", onMove);
      root.addEventListener("mouseup", onUp);
    });

    this.canvas.appendChild(div);
  };

  // Full rebuild of lines + nodes + panel (same rebuild pattern as the design view).
  App.prototype.refreshMapping = function () {
    var self = this;
    this.canvas.innerHTML = "";
    this.canvas.classList.add("dss-map-canvas");
    var svgNS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("class", "dss-map-svg");
    this.state.mappings.forEach(function (m) {
      var from = self._node("src:" + m.external_table);
      var to = self._node("tgt:" + m.target_doctype);
      if (!from || !to) return;
      var lineEl = document.createElementNS(svgNS, "line");
      lineEl.setAttribute("x1", from.pos_x + 150);
      lineEl.setAttribute("y1", from.pos_y + 20);
      lineEl.setAttribute("x2", to.pos_x);
      lineEl.setAttribute("y2", to.pos_y + 20);
      lineEl.setAttribute("class", "dss-map-line is-" + m.mapping_status.toLowerCase());
      svg.appendChild(lineEl);
    });
    this.canvas.appendChild(svg);
    this.state.mapNodes.forEach(function (n) { self.renderMapNode(n); });
    this.renderMappingPanel();
  };

  App.prototype.renderMappingPanel = function () {
    var self = this;
    this.panel.innerHTML = "";
    this.panel.appendChild(el("h3", "dss-panel-title", "Mappings"));
    this.panel.appendChild(el("p", "dss-hint",
      this.state.pickedSource
        ? "Now click a Target DocType to map it."
        : "Click a Source Table, then a Target DocType, to draw a mapping. Click a mapping to cycle its status."));

    // Show what the parser concluded about the last analyzed query — especially
    // when it declined to translate it, which must never be silent.
    var analysis = this.state.lastAnalysis;
    if (analysis) {
      if (analysis.supported) {
        this.panel.appendChild(el("div", "dss-analysis is-ok",
          "SQL analyzed: " + (analysis.doctypes || []).length + " table(s) found" +
          ((analysis.group_by || []).length ? ", grouped by " + analysis.group_by.join(", ") : "") +
          ". Suggested mappings are marked Suggested until you confirm them."));
      } else {
        this.panel.appendChild(el("div", "dss-analysis is-warn",
          "This query was not translated — " + (analysis.reasons || []).join("; ") +
          ". Tables found are shown so you can map them by hand; nothing was suggested automatically."));
      }
    }

    if (!this.state.mappings.length) {
      this.panel.appendChild(el("p", "dss-hint", "No mappings yet."));
    }
    this.state.mappings.forEach(function (m) {
      var row = el("div", "dss-map-row is-" + m.mapping_status.toLowerCase(),
        m.external_table + " → " + m.target_doctype + "  [" + m.mapping_status + "]");
      row.addEventListener("click", function () {
        m.mapping_status = core.nextMappingStatus(m.mapping_status);
        self.refreshMapping();
      });
      self.panel.appendChild(row);
    });

    var save = el("button", "dss-btn dss-btn-primary", "Save mappings");
    save.addEventListener("click", function () { self.saveMappings(); });
    this.panel.appendChild(save);

    this.renderSqlImport();
  };

  // Paste Metabase SQL to seed the canvas: the parser reports what it found and
  // suggests identity mappings, which the user then confirms or rejects.
  App.prototype.renderSqlImport = function () {
    var self = this;
    var wrap = el("div", "dss-sqlimport");
    wrap.appendChild(el("span", "dss-field-label", "Import from Metabase SQL"));

    var box = el("textarea", "dss-input");
    box.placeholder = "Paste a SELECT query…";
    box.setAttribute("aria-label", "Metabase SQL");
    wrap.appendChild(box);

    var note = el("div", "dss-sqlnote");
    wrap.appendChild(note);

    var analyze = el("button", "dss-btn dss-btn-small", "Analyze SQL");
    analyze.addEventListener("click", function () {
      var sql = (box.value || "").trim();
      if (!sql) { note.textContent = "Paste a query first."; return; }
      if (!hasFrappe()) {
        note.textContent = "SQL analysis needs the server (not available in mock mode).";
        return;
      }
      note.textContent = "Analyzing…";
      root.frappe.call({
        method: "dashboard_studio.api.migration.analyze_migration_sql",
        args: { sql: sql },
      }).then(function (r) {
        var data = r.message || {};
        var analysis = data.analysis || {};
        self.applyAnalysis(analysis, data.suggested_mappings || [], sql);
      }).catch(function () {
        note.textContent = "Could not analyze that query.";
      });
    });
    wrap.appendChild(analyze);
    this.panel.appendChild(wrap);
  };

  // Seed nodes and suggestions from a parsed query. Tables found are always
  // shown (they can still be mapped by hand); mappings are only ever suggested
  // for a query the parser judged safe to translate.
  App.prototype.applyAnalysis = function (analysis, suggestions, sql) {
    var discovered = core.analysisToNodes(analysis, analysis.doctypes || []);
    this.state.mapNodes = core.mergeNodes(this.state.mapNodes, discovered);
    this.state.mappings = core.mergeMappings(this.state.mappings, suggestions);
    this.state.lastAnalysis = analysis;
    // Keep the query itself for the next save — it is the evidence, and it
    // matters most for the queries that were NOT translated.
    if (sql) {
      this.state.analyzedQueries = (this.state.analyzedQueries || []).concat([{
        source_sql: sql,
        supported: !!analysis.supported,
        reasons: analysis.reasons || [],
      }]);
    }
    this.refreshMapping();
  };

  App.prototype.saveMappings = function () {
    var self = this;
    var mappings = this.state.mappings;
    var canvasNodes = core.serializeCanvasNodes(this.state.mapNodes || []);
    var analyzedQueries = this.state.analyzedQueries || [];

    // Without a ?project= there is nothing to save against, so keep the mock
    // path — the payload shape is identical either way.
    if (!this.options.project || !hasFrappe()) {
      if (root.console) {
        root.console.log("[Dashboard Studio] mock mapping payload",
          { mappings: mappings, canvas_nodes: canvasNodes, source_queries: analyzedQueries });
      }
      toast("Captured " + mappings.length + " mapping(s) (mock — no migration project)");
      return;
    }

    root.frappe.call({
      method: "dashboard_studio.api.studio.save_migration_mapping_set",
      args: {
        project: this.options.project,
        mappings: JSON.stringify(mappings),
        canvas_nodes: JSON.stringify(canvasNodes),
        source_queries: JSON.stringify(analyzedQueries),
      },
    }).then(function (r) {
      var result = r.message || {};
      // Recorded evidence is now on the project, so it need not be resent.
      self.state.analyzedQueries = [];
      toast("Saved " + (result.saved_mappings || 0) + " mapping(s)" +
        (result.recorded_queries ? ", " + result.recorded_queries + " query(ies) kept as evidence" : "") +
        " — project is now " + (result.status || "updated"));
    });
  };

  // Metrics for the picker as [{name, source_doctype}]: mock keys this session;
  // live list (already restricted to executable metrics) cached once.
  App.prototype.availableMetrics = function (callback) {
    if (this.state.mock || !hasFrappe()) {
      callback(Object.keys((root.DSStudioMock || {}).MOCK_METRIC_RESULTS || {})
        .map(function (name) { return { name: name }; }));
      return;
    }
    var self = this;
    if (this._metricList) { callback(this._metricList); return; }
    root.frappe.call({ method: "dashboard_studio.api.studio.list_ds_metrics" })
      .then(function (r) {
        self._metricList = (r.message || []).map(function (m) {
          return { name: m.name, source_doctype: m.source_doctype };
        });
        callback(self._metricList);
      })
      .catch(function () { callback([]); });
  };

  App.prototype.saveChart = function (chart) {
    if (this.state.mock || !hasFrappe()) {
      toast("Saved “" + chart.chart_title + "” (mock — not persisted)");
      return;
    }
    root.frappe.call({
      method: "dashboard_studio.api.studio.save_chart",
      args: {
        chart: chart.name,
        patch: JSON.stringify({
          chart_title: chart.chart_title, chart_type: chart.chart_type,
          description: chart.description, metric: chart.metric,
          pos_x: chart.pos_x, pos_y: chart.pos_y,
          width: chart.width, height: chart.height,
          chart_filters: (chart.chart_filters || []).map(function (row) {
            return {
              fieldname: row.fieldname, operator: row.operator,
              value: row.value, filter_type: row.filter_type || "Static",
            };
          }),
        }),
      },
    }).then(function () { toast("Saved " + chart.chart_title); });
  };

  App.prototype.saveLayout = function () {
    var layout = core.serializeLayout(this.state.charts);
    if (this.state.mock || !hasFrappe()) {
      toast("Layout captured for " + layout.length + " charts (mock — not persisted)");
      return;
    }
    var self = this;
    Promise.all(this.state.charts.map(function (c) {
      return root.frappe.call({
        method: "dashboard_studio.api.studio.save_chart",
        args: { chart: c.name, patch: JSON.stringify(core.clampLayout(c)) },
      });
    })).then(function () { toast("Saved layout for " + self.state.charts.length + " charts"); });
  };

  function field(label, input) {
    var wrap = el("label", "dss-field");
    wrap.appendChild(el("span", "dss-field-label", label));
    wrap.appendChild(input);
    return wrap;
  }

  var api = {
    mount: function (mountPoint, options) {
      var app = new App(mountPoint, options);
      app.load();
      return app;
    },
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.DSStudioApp = api;
})(typeof window !== "undefined" ? window : globalThis);
