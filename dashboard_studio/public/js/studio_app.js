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
    this.state = { dashboard: null, charts: [], selected: null, mock: false };
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
    var saveAll = el("button", "dss-btn dss-btn-primary", "Save layout");
    saveAll.addEventListener("click", function () { self.saveLayout(); });
    head.appendChild(saveAll);
    wrap.appendChild(head);

    var main = el("div", "dss-main");
    this.canvas = el("div", "dss-canvas");
    this.canvas.style.minHeight = "480px";
    main.appendChild(this.canvas);
    this.panel = el("div", "dss-panel");
    main.appendChild(this.panel);
    wrap.appendChild(main);

    this.mount.appendChild(wrap);
    this.state.charts.forEach(function (c) { self.renderCard(c); });
    this.renderPanel();
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
    card.appendChild(el("div", "dss-card-body", chart.source_doctype || (chart.metric || "")));

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

    var typeSelect = el("select", "dss-input");
    core.CHART_TYPES.forEach(function (t) {
      var o = el("option", null, t);
      o.value = t;
      if (t === chart.chart_type) o.selected = true;
      typeSelect.appendChild(o);
    });
    this.panel.appendChild(field("Chart type", typeSelect));

    var descInput = el("textarea", "dss-input");
    descInput.value = chart.description || "";
    this.panel.appendChild(field("Description", descInput));

    var err = el("div", "dss-error");
    this.panel.appendChild(err);

    var actions = el("div", "dss-actions");
    var applyBtn = el("button", "dss-btn", "Apply");
    var saveBtn = el("button", "dss-btn dss-btn-primary", "Save chart");
    actions.appendChild(applyBtn);
    actions.appendChild(saveBtn);
    this.panel.appendChild(actions);

    function collect() {
      return { chart_title: titleInput.value, chart_type: typeSelect.value, description: descInput.value };
    }
    function applyEdit() {
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
          description: chart.description, pos_x: chart.pos_x, pos_y: chart.pos_y,
          width: chart.width, height: chart.height,
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
