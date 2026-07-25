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

  // Palette glyphs. Plain characters on purpose — an icon set would be a
  // dependency, and this app has none.
  var PALETTE_GLYPHS = {
    "KPI Card": "#", "Bar Chart": "▥", "Line Chart": "⌁", "Donut Chart": "◌",
    "Table": "▤", "Trend Chart": "◹", "Funnel": "▽", "Radar": "◈",
  };

  // Workspace header: kicker / title / what this screen is for. The Design view
  // has no entry — its heading is the dashboard title in the toolbar.
  var HEROES = {
    mapping: ["Metabase migration", "Map a Metabase query onto DocTypes",
      "Paste the query behind a Metabase card. Tables it finds become nodes you " +
      "map to DocTypes; anything it cannot safely translate is reported, never guessed."],
    data: ["Source of truth", "Records, relationships and safe fields",
      "What this app has stored, how those records link to each other, and which " +
      "fields each metric is allowed to read."],
    validation: ["Result comparison", "Validation Centre",
      "Compare a reference result against this app's result for the same chart " +
      "before publishing. Differences are only ever accepted by a person."],
    governance: ["Governance", "Review and publish",
      "A dashboard moves Draft → Technical Review → QA Approval → Published. " +
      "Whoever builds it cannot be the one who publishes it."],
  };

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
      dashboard: null, charts: [], selected: null, mock: false, mockReason: null,
      // Every dashboard the user may open, for the toolbar switcher. null = not
      // fetched yet (distinct from [] = fetched, none exist).
      dashboards: null,
      pickerOpen: false, pickerQuery: "", pickerIndex: 0,
      // Layout moved/edited in memory but not written back yet.
      dirty: false,
      // Arriving with ?project= means the caller came from a DS Migration
      // Project, so open straight into the Mapping view.
      view: this.options.project ? "mapping" : "design",
      // Mapping view state, built lazily on first open.
      mapNodes: null, mappings: [], pickedSource: null,
      // Sections group charts in the Design view; collapse state is per session.
      sections: [], collapsedSections: {},
    };
  }

  // Real records are the default. Mock is only reached when there is no server
  // at all, or a call to it failed — never simply because no dashboard was named
  // in the route.
  App.prototype.load = function () {
    var self = this;
    // Only reachable outside the Desk (the standalone render harness) — inside
    // Frappe, frappe.require loaded this file, so frappe exists by definition.
    if (!hasFrappe()) {
      this.useMock("No Frappe backend is reachable from this page.");
      return;
    }
    if (this.options.dashboard) {
      this.openDashboard(this.options.dashboard);
      return;
    }
    root.frappe.call({ method: "dashboard_studio.api.studio.list_dashboards" })
      .then(function (r) {
        self.state.dashboards = r.message || [];
        if (self.state.dashboards.length) {
          self.openDashboard(self.state.dashboards[0].name);
        } else {
          self.renderEmpty();
        }
      })
      .catch(function () {
        self.renderError("Could not load the list of dashboards.");
      });
  };

  // ---- Dashboard picker ----------------------------------------------------
  //
  // The dashboard title is the trigger: the thing you want to change is the
  // thing you click. Scale behaviour (search, grouping) lives in
  // core.pickerModel so it can be tested without a browser.

  var SVG_NS = "http://www.w3.org/2000/svg";
  // Geometry taken from prototypes/ds_picker_revised.html.
  var CHEVRON_PATH = "M4 6.5 8 10.5l4-4";
  var TICK_PATH = "M3.5 8.5 6.5 11.5 12.5 5";
  var PENCIL_PATH = "M11.4 2.6a1.5 1.5 0 0 1 2.1 2.1L6.2 12 3 13l1-3.2 7.4-7.2z";

  // A real 16px icon, not a text glyph — a caret character sitting next to a
  // bold title reads as stray punctuation.
  function icon(d, cls, width) {
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", cls);
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("width", "16");
    svg.setAttribute("height", "16");
    svg.setAttribute("fill", "none");
    svg.setAttribute("aria-hidden", "true");
    var path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", d);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", width || "2");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    svg.appendChild(path);
    return svg;
  }

  // The magnifier in the search field. Two shapes rather than one path, so it
  // gets its own builder.
  function searchIcon() {
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "dss-picker-searchicon");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("fill", "none");
    svg.setAttribute("aria-hidden", "true");
    var ring = document.createElementNS(SVG_NS, "circle");
    ring.setAttribute("cx", "6.8");
    ring.setAttribute("cy", "6.8");
    ring.setAttribute("r", "4.6");
    ring.setAttribute("stroke", "currentColor");
    ring.setAttribute("stroke-width", "1.7");
    var handle = document.createElementNS(SVG_NS, "path");
    handle.setAttribute("d", "M10.3 10.3 14 14");
    handle.setAttribute("stroke", "currentColor");
    handle.setAttribute("stroke-width", "1.7");
    handle.setAttribute("stroke-linecap", "round");
    svg.appendChild(ring);
    svg.appendChild(handle);
    return svg;
  }

  function statusPill(status, cls) {
    return el("span", (cls || "dss-picker-pill") + " " + statusClass(status), status || "Draft");
  }

  // Status carries real meaning, so the pills are colour-coded — but quietly,
  // so the eye lands on the dashboard name first. Anything unrecognised falls
  // back to neutral rather than being coloured by guesswork.
  function statusClass(status) {
    if (status === "Published") return "is-published";
    if (status === "Technical Review" || status === "QA Approval") return "is-review";
    // Archived is retired, so it reads quieter than anything active — quieter
    // than Draft too, which is a live dashboard someone is still working on.
    if (status === "Archived") return "is-archived";
    return "is-draft"; // Draft, or unset
  }

  App.prototype.buildTitle = function () {
    var self = this;
    var title = (this.state.dashboard && this.state.dashboard.dashboard_title) || "Dashboard";
    var box = el("div", "dss-titlebox");

    // With no live list there is nothing to pick from — a plain heading, not a
    // control that opens an empty panel.
    if (this.state.mock || !(this.state.dashboards || []).length) {
      box.appendChild(el("h2", "dss-title", title));
      return box;
    }

    var trigger = el("button", "dss-picker-trigger" + (this.state.pickerOpen ? " is-open" : ""));
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", this.state.pickerOpen ? "true" : "false");
    trigger.setAttribute("title", "Open a different dashboard");
    trigger.appendChild(el("h2", "dss-title", title));
    // The open dashboard's status, right where its name is: which stage the
    // thing you are editing sits at is worth knowing without changing tab.
    if (this.state.dashboard && this.state.dashboard.status) {
      trigger.appendChild(statusPill(this.state.dashboard.status));
    }
    trigger.appendChild(icon(CHEVRON_PATH, "dss-chevron", "1.8"));
    trigger.addEventListener("click", function () {
      self.togglePicker(!self.state.pickerOpen);
    });
    this.pickerTrigger = trigger;
    box.appendChild(trigger);

    this.pickerHost = el("div", "dss-picker-host");
    box.appendChild(this.pickerHost);
    if (this.state.pickerOpen) this.paintPicker();
    return box;
  };

  App.prototype.togglePicker = function (open) {
    this.state.pickerOpen = open;
    if (!open) {
      this.state.pickerQuery = "";
      this.state.pickerIndex = 0;
    }
    if (this.pickerTrigger) {
      this.pickerTrigger.classList.toggle("is-open", open);
      this.pickerTrigger.setAttribute("aria-expanded", open ? "true" : "false");
    }
    this.paintPicker();
    // Closing returns focus to what opened it, so keyboard users are not
    // dropped back at the top of the document.
    if (!open && this.pickerTrigger) this.pickerTrigger.focus();
  };

  App.prototype.paintPicker = function () {
    var self = this;
    var host = this.pickerHost;
    if (!host) return;
    host.innerHTML = "";
    if (!this.state.pickerOpen) return;

    var panel = el("div", "dss-picker-panel");
    panel.setAttribute("role", "listbox");
    panel.setAttribute("aria-label", "Open dashboard");

    var model = core.pickerModel(this.state.dashboards, { query: this.state.pickerQuery });
    var search = null;

    // The search box only exists past the threshold — a short list does not
    // need one, and showing it would imply the list is longer than it is.
    if (model.searchable) {
      var searchWrap = el("div", "dss-picker-search");
      var searchBox = el("div", "dss-picker-searchbox");
      searchBox.appendChild(searchIcon());
      search = el("input", "dss-input");
      search.type = "text";
      search.placeholder = "Search dashboards";
      search.setAttribute("aria-label", "Search dashboards");
      search.value = this.state.pickerQuery || "";
      searchBox.appendChild(search);
      searchWrap.appendChild(searchBox);
      panel.appendChild(searchWrap);
    }

    var listHost = el("div", "dss-picker-list");
    panel.appendChild(listHost);

    var footer = el("div", "dss-picker-footer");
    panel.appendChild(footer);

    function repaint() {
      var current = self.state.dashboard && self.state.dashboard.name;
      model = core.pickerModel(self.state.dashboards, { query: self.state.pickerQuery });
      listHost.innerHTML = "";
      footer.innerHTML = "";

      // Guidance only — the create action stays in the footer, where it sits in
      // every other state, rather than moving into the message and competing
      // for the click.
      if (!model.shown) {
        var none = el("div", "dss-picker-empty");
        none.appendChild(el("strong", null, 'No dashboard matches “' + model.query + '”'));
        none.appendChild(document.createTextNode(
          "Create one, or clear the search to see all " + model.total + "."));
        listHost.appendChild(none);
      }

      model.groups.forEach(function (group) {
        if (group.title && group.items.length) {
          var head = el("div", "dss-picker-group");
          head.appendChild(el("span", "dss-picker-group-label", group.title));
          head.appendChild(el("span", "dss-picker-group-rule"));
          listHost.appendChild(head);
        }
        group.items.forEach(function (d) {
          var isCurrent = d.name === current;
          // Wrapper, because the edit link cannot live inside the row: nesting
          // an <a> in a <button> is invalid and browsers handle it however they
          // like. As siblings they each get their own click, with nothing to
          // suppress.
          var item = el("div", "dss-picker-item" + (isCurrent ? " is-current" : ""));

          var row = el("button", "dss-picker-row");
          row.setAttribute("role", "option");
          row.setAttribute("aria-selected", isCurrent ? "true" : "false");
          // A tick, not just a pale fill: colour alone is not an accessible
          // signal. The fill stays as reinforcement.
          var mark = el("span", "dss-picker-mark");
          if (isCurrent) mark.appendChild(icon(TICK_PATH, "dss-tick"));
          row.appendChild(mark);
          row.appendChild(el("span", "dss-picker-name", core.dashboardTitle(d)));
          row.appendChild(statusPill(d.status));
          row.addEventListener("click", function () {
            self.togglePicker(false);
            if (!isCurrent) self.openDashboard(d.name);
          });
          item.appendChild(row);

          // The record form holds what the Studio does not expose — description,
          // publish target, reviewer, review comments. A real link rather than
          // window.open, so ctrl/middle-click behave as expected and the person
          // keeps their place here.
          var edit = el("a", "dss-picker-edit");
          edit.href = core.dashboardFormUrl(d.name);
          edit.target = "_blank";
          edit.rel = "noopener";
          edit.title = "Edit this dashboard's record (opens a new tab)";
          edit.setAttribute("aria-label",
            "Edit the record for " + core.dashboardTitle(d) + " (opens a new tab)");
          edit.appendChild(icon(PENCIL_PATH, "dss-pencil", "1.6"));
          item.appendChild(edit);

          listHost.appendChild(item);
        });
      });

      // While filtering the count says "N of M", so a narrowed list is never
      // mistaken for a short one.
      footer.appendChild(el("span", "dss-picker-count",
        model.shown === model.total
          ? model.total + (model.total === 1 ? " dashboard" : " dashboards")
          : model.shown + " of " + model.total));
      // "+ New dashboard" stays put in every state. The reference mockup swaps
      // it out for "View all →" on a long list, but that was only safe while a
      // "New Dashboard" button existed in the page header; without it, the swap
      // would strand creation behind a trip to the record list for exactly the
      // people with the most dashboards.
      //
      // Both links plus the ↑↓/esc keycaps overflow 392px, so the keycaps went:
      // they only advertise behaviour that works either way, whereas the link
      // is the only way to do the thing.
      var actions = el("div", "dss-picker-actions");
      actions.appendChild(self.pickerCreateButton());
      // Past the threshold the picker stops trying to be a list view and hands
      // bulk work to the real one.
      if (model.searchable && model.shown) {
        var all = el("button", "dss-picker-link", "View all →");
        all.addEventListener("click", function () {
          self.togglePicker(false);
          if (hasFrappe()) root.frappe.set_route("List", "DS Dashboard");
          else toast("The DS Dashboard list needs the server.");
        });
        actions.appendChild(all);
      }
      footer.appendChild(actions);
    }

    function rows() {
      return Array.prototype.slice.call(listHost.querySelectorAll(".dss-picker-row"));
    }

    if (search) {
      search.addEventListener("input", function () {
        self.state.pickerQuery = search.value;
        self.state.pickerIndex = 0;
        repaint();
      });
    }

    panel.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        e.preventDefault();
        self.togglePicker(false);
        return;
      }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp" && e.key !== "Enter") return;
      var list = rows();
      if (!list.length) return;
      if (e.key === "Enter") {
        // Enter on a row is the row's own click. From the search box it opens
        // whichever row the arrows last landed on.
        if (e.target === search) {
          e.preventDefault();
          list[Math.min(self.state.pickerIndex || 0, list.length - 1)].click();
        }
        return;
      }
      e.preventDefault();
      var at = list.indexOf(document.activeElement);
      var next = e.key === "ArrowDown"
        ? (at < 0 ? 0 : (at + 1) % list.length)
        : (at < 0 ? list.length - 1 : (at - 1 + list.length) % list.length);
      self.state.pickerIndex = next;
      list[next].focus();
    });

    host.appendChild(panel);
    repaint();

    // Clicking anywhere else closes it, the way every other menu behaves.
    var away = function (e) {
      if (panel.contains(e.target) || self.pickerTrigger.contains(e.target)) return;
      document.removeEventListener("mousedown", away, true);
      self.togglePicker(false);
    };
    document.addEventListener("mousedown", away, true);

    // Opening lands where typing or picking would start: the search box past
    // the threshold, otherwise the dashboard already open.
    if (search) {
      search.focus();
    } else {
      var list = rows();
      var current = listHost.querySelector(".dss-picker-item.is-current .dss-picker-row");
      (current || list[0] || panel).focus();
    }
  };

  App.prototype.pickerCreateButton = function () {
    var self = this;
    var btn = el("button", "dss-picker-link", "+ New dashboard");
    btn.addEventListener("click", function () {
      self.togglePicker(false);
      self.newDashboard();
    });
    return btn;
  };

  App.prototype.openDashboard = function (name) {
    var self = this;
    root.frappe.call({
      method: "dashboard_studio.api.studio.get_studio_dashboard",
      args: { dashboard: name },
    }).then(function (r) {
      var data = r.message || {};
      self.state.dashboard = data.dashboard;
      self.state.charts = data.charts || [];
      self.state.sections = data.sections || [];
      self.state.mock = false;
      self.state.mockReason = null;
      // Both caches are keyed by metric name but their contents depend on which
      // backend answered. Loading a real dashboard after the demo must not keep
      // serving the demo's metrics or its numbers.
      self.dropMetricCaches();
      self.render();
      // Keep the toolbar switcher populated even when opened straight from a route.
      if (!self.state.dashboards) self.listDashboards();
    }).catch(function () {
      self.renderError("Could not open “" + name + "”. It may have been renamed or deleted.");
    });
  };

  App.prototype.listDashboards = function () {
    var self = this;
    root.frappe.call({ method: "dashboard_studio.api.studio.list_dashboards" })
      .then(function (r) {
        self.state.dashboards = r.message || [];
        self.render();
      })
      .catch(function () { /* switcher is optional; the dashboard is already open */ });
  };

  // One card, centred: used for both "nothing exists yet" and "the server said
  // no". Neither is a reason to show invented records.
  App.prototype.renderNotice = function (title, message, actions) {
    this.mount.innerHTML = "";
    var wrap = el("div", "dss-wrap");
    var box = el("div", "dss-empty");
    box.appendChild(el("div", "dss-empty-kicker", "Dashboard Studio"));
    box.appendChild(el("h2", "dss-empty-title", title));
    box.appendChild(el("p", "dss-hint", message));
    actions.forEach(function (a) { box.appendChild(a); });
    wrap.appendChild(box);
    this.mount.appendChild(wrap);
  };

  // The demo, offered as a deliberate choice and never as a default.
  App.prototype.demoButton = function (reason) {
    var self = this;
    var btn = el("button", "dss-btn dss-btn-ghost", "Explore the demo");
    btn.title = "Loads invented sample records. Nothing is saved.";
    btn.addEventListener("click", function () { self.useMock(reason); });
    return btn;
  };

  // No dashboards exist yet: invite creating one.
  App.prototype.renderEmpty = function () {
    var self = this;
    var create = el("button", "dss-btn dss-btn-primary", "Create your first dashboard");
    create.addEventListener("click", function () { self.newDashboard(); });
    this.renderNotice(
      "No dashboards yet",
      "There are no DS Dashboard records to open. Creating one saves a real " +
      "record straight away, and the editor opens on it.",
      [create, this.demoButton("You chose the demo from the empty state.")]
    );
  };

  // Something went wrong talking to the server. Say so — falling back to sample
  // data here is what made a broken connection look like a working studio.
  App.prototype.renderError = function (message) {
    var self = this;
    var retry = el("button", "dss-btn dss-btn-primary", "Try again");
    retry.addEventListener("click", function () {
      self.state.dashboards = null;
      self.load();
    });
    this.renderNotice("Could not load your dashboards", message,
      [retry, this.demoButton("You chose the demo after a failed load.")]);
  };

  App.prototype.newDashboard = function () {
    var self = this;
    if (!hasFrappe()) { toast("Creating a dashboard needs the server."); return; }
    var title = root.prompt("Dashboard title");
    if (title == null) return;
    if (!title.trim()) { toast("A dashboard needs a title."); return; }
    root.frappe.call({
      method: "dashboard_studio.api.studio.create_dashboard",
      args: { dashboard_title: title.trim() },
    }).then(function (r) {
      var created = r.message || {};
      self.state.dashboards = null; // refetched by openDashboard
      self.openDashboard(created.name);
      toast("Created " + created.dashboard_title);
    }).catch(function () {
      toast("Could not create the dashboard.");
    });
  };

  // Metric name -> source, and metric name -> result rows. Both are answered by
  // whichever backend is live, so switching backend has to drop them.
  App.prototype.dropMetricCaches = function () {
    this._metricList = null;
    this._metricListWarming = false;
    this._rowsCache = {};
  };

  App.prototype.useMock = function (reason) {
    var mock = (root.DSStudioMock || {}).MOCK_DASHBOARD || { charts: [] };
    this.state.dashboard = mock;
    this.state.charts = mock.charts.map(function (c) { return Object.assign({}, c); });
    this.state.sections = mock.sections || [];
    this.state.mock = true;
    this.state.mockReason = reason || null;
    this.dropMetricCaches();
    this.render();
  };

  App.prototype.render = function () {
    var self = this;
    this.mount.innerHTML = "";
    var wrap = el("div", "dss-wrap");

    if (this.state.mock) {
      wrap.appendChild(el("div", "dss-banner",
        "⚠ Sample data — not a live DS Dashboard, and nothing you change here is saved. " +
        (this.state.mockReason || "")));
    }

    var head = el("div", "dss-toolbar");
    head.appendChild(this.buildTitle());
    // Unsaved-layout marker. saveLayout writes every chart unconditionally, so
    // without this there is no way to tell whether pressing it does anything.
    if (this.state.view === "design" && !this.state.mock) {
      head.appendChild(el("span",
        "dss-savestate" + (this.state.dirty ? " is-dirty" : ""),
        this.state.dirty ? "● Unsaved layout changes" : "● All changes saved"));
    }

    if (this.state.view === "design") {
      var addSection = el("button", "dss-btn", "+ Section");
      addSection.title = "Add a section to group charts";
      addSection.addEventListener("click", function () { self.addSection(); });
      head.appendChild(addSection);

      var saveAll = el("button", "dss-btn dss-btn-primary", "Save layout");
      saveAll.addEventListener("click", function () { self.saveLayout(); });
      head.appendChild(saveAll);
    }
    wrap.appendChild(head);

    // Workspace tab bar (underlined active tab), not a row of buttons.
    var tabs = el("div", "dss-tabs");
    tabs.setAttribute("role", "tablist");
    [["design", "Dashboard Builder"], ["mapping", "Metabase Migration"],
     ["data", "Data & DocTypes"], ["validation", "Validation"],
     ["governance", "Governance & Publish"]].forEach(function (pair) {
      var v = pair[0];
      var active = self.state.view === v;
      var tab = el("button", "dss-tab" + (active ? " is-active" : ""), pair[1]);
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", active ? "true" : "false");
      tab.addEventListener("click", function () { self.state.view = v; self.render(); });
      tabs.appendChild(tab);
    });
    wrap.appendChild(tabs);

    // The Builder has no fixed hero — its heading is the dashboard title in the
    // toolbar — but DS Dashboard.description was being stored and never shown
    // anywhere. Reuses the hero block rather than adding a second style for it.
    var dashboardDescription = this.state.dashboard && this.state.dashboard.description;
    if (this.state.view === "design" && dashboardDescription) {
      var descBox = el("div", "dss-hero");
      descBox.appendChild(el("p", "dss-hero-blurb", dashboardDescription));
      wrap.appendChild(descBox);
    }

    var hero = HEROES[this.state.view];
    if (hero) {
      var heroBox = el("div", "dss-hero");
      heroBox.appendChild(el("div", "dss-kicker", hero[0]));
      heroBox.appendChild(el("h3", "dss-hero-title", hero[1]));
      heroBox.appendChild(el("p", "dss-hero-blurb", hero[2]));
      wrap.appendChild(heroBox);
    }

    // Pasting SQL is how a migration actually starts, so it leads the workspace
    // rather than sitting under the mapping list in the side panel.
    if (this.state.view === "mapping") wrap.appendChild(this.buildSqlImport());
    if (this.state.view === "validation") wrap.appendChild(this.buildValidationRun());

    var main = el("div", "dss-main");
    // Visual catalogue, Builder only: the palette has to stay reachable while a
    // card is selected, so it gets its own column rather than sharing the
    // properties panel.
    if (this.state.view === "design") {
      main.classList.add("dss-main-builder");
      main.appendChild(this.buildPalette());
    }
    this.canvas = el("div", "dss-canvas");
    this.canvas.style.minHeight = "480px";
    main.appendChild(this.canvas);
    this.panel = el("div", "dss-panel");
    main.appendChild(this.panel);
    wrap.appendChild(main);

    this.mount.appendChild(wrap);
    if (this.state.view === "mapping") {
      this.renderMapping();
    } else if (this.state.view === "data") {
      this.renderCatalogue();
    } else if (this.state.view === "validation") {
      this.renderValidation();
    } else if (this.state.view === "governance") {
      this.renderGovernance();
    } else {
      this.refresh();
      this.renderPanel();
    }
  };

  // Visual catalogue. Only the types that can actually be drawn are offered —
  // the other 9 in CHART_TYPES render a stub, so putting them in a "click to
  // add" palette would be an invitation to create a broken card.
  //
  // ponytail: click-to-add, not drag-to-drop. The card lands on the first free
  // row and is then positioned with the existing drag behaviour. Drag from the
  // palette needs px->grid mapping onto a drop target; add it if placing cards
  // one at a time proves annoying. Click also keeps this keyboard-reachable,
  // which a drag-only palette would not be.
  App.prototype.buildPalette = function () {
    var self = this;
    var wrap = el("aside", "dss-palette");
    wrap.appendChild(el("div", "dss-kicker", "Visual catalogue"));
    wrap.appendChild(el("h3", "dss-palette-title", "Charts"));

    var drawable = (root.DSStudioCharts || {}).SUPPORTED_CHART_TYPES || [];
    var list = el("div", "dss-palette-list");
    drawable.forEach(function (type) {
      var item = el("button", "dss-palette-item");
      item.type = "button";
      item.title = "Add a " + type + " to this dashboard";
      item.appendChild(el("span", "dss-palette-glyph", PALETTE_GLYPHS[type] || "▦"));
      item.appendChild(el("span", "dss-palette-label", type));
      item.addEventListener("click", function () { self.addChart(type); });
      list.appendChild(item);
    });
    wrap.appendChild(list);
    wrap.appendChild(el("p", "dss-hint",
      "Adds a card below the existing ones. Drag it to position, then link a " +
      "metric in the panel on the right."));
    return wrap;
  };

  App.prototype.addChart = function (chartType, copyFrom) {
    var self = this;
    var dashboard = this.state.dashboard && this.state.dashboard.name;
    if (this.state.mock || !hasFrappe() || !dashboard) {
      toast("Adding a chart needs a live dashboard (not available in sample mode).");
      return;
    }
    root.frappe.call({
      method: "dashboard_studio.api.studio.create_chart",
      args: { dashboard: dashboard, chart_type: chartType, copy_from: copyFrom || null },
    }).then(function (r) {
      var created = r.message || {};
      self.reloadDashboard("Added " + (created.chart_title || "chart"));
      self.state.selected = created.name;
    }).catch(function () {
      toast("Could not add that chart.");
    });
  };

  App.prototype.deleteChart = function (chart) {
    var self = this;
    if (this.state.mock || !hasFrappe()) {
      toast("Deleting a chart needs a live dashboard (not available in sample mode).");
      return;
    }
    if (!root.confirm('Delete "' + (chart.chart_title || chart.name) +
        '"? Its metric is kept and stays available to other charts.')) return;
    root.frappe.call({
      method: "dashboard_studio.api.studio.delete_chart",
      args: { chart: chart.name },
    }).then(function () {
      self.state.selected = null;
      self.reloadDashboard("Deleted " + (chart.chart_title || chart.name));
    }).catch(function () {
      toast("Could not delete that chart.");
    });
  };

  App.prototype.renderCard = function (chart, container) {
    var self = this;
    var style = core.layoutStyle(chart);
    var card = el("div", "dss-card" + (this.state.selected === chart.name ? " is-selected" : ""));
    card.style.left = style.left;
    card.style.width = style.width;
    card.style.top = style.top * ROW_H + "px";
    card.style.height = style.heightRows * ROW_H + "px";

    var header = el("div", "dss-card-head");
    var titleWrap = el("div", "dss-card-title-wrap");
    titleWrap.appendChild(el("span", "dss-card-title", chart.chart_title));
    // The description was editable but never shown, so nothing on the canvas
    // said what a card actually measures.
    if (chart.description) {
      titleWrap.appendChild(el("span", "dss-card-subtitle", chart.description));
    }
    header.appendChild(titleWrap);
    header.appendChild(el("span", "dss-card-type", chart.chart_type || "—"));
    card.appendChild(header);
    var body = el("div", "dss-card-body");
    card.appendChild(body);
    this.renderChartBody(body, chart);

    // Which DocType the numbers come from — evidence provenance belongs on the
    // card, not only in the properties panel.
    var source = this.metricSource(chart.metric);
    if (source) {
      card.appendChild(el("div", "dss-card-foot", "Source: " + source));
    }

    var resize = el("div", "dss-resize");
    card.appendChild(resize);

    card.addEventListener("mousedown", function (e) {
      if (e.target === resize) return;
      self.select(chart.name);
    });
    this.dragBehavior(header, chart, "move", container);
    this.dragBehavior(resize, chart, "resize", container);

    container.appendChild(card);
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
  App.prototype.dragBehavior = function (handle, chart, mode, container) {
    var self = this;
    handle.addEventListener("mousedown", function (e) {
      e.preventDefault();
      var startX = e.clientX, startY = e.clientY;
      // Measure the surface this card actually sits on — with sections, that is
      // the band's own canvas, not the outer wrapper.
      var colW = container.clientWidth / core.GRID_COLUMNS;
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
        self.state.dirty = true; // layout moved but not yet written back
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
    var bands = core.groupChartsBySection(this.state.charts, this.state.sections);

    // No sections defined: keep the single flat canvas exactly as before.
    if (!bands.length) {
      this.canvas.className = "dss-canvas";
      this.state.charts.forEach(function (chart) { self.renderCard(chart, self.canvas); });
      this.fitCanvas(this.canvas, this.state.charts);
      return;
    }

    // With sections, the outer element becomes a plain wrapper and each band
    // gets its own surface, so coordinates and drag are scoped to the section.
    this.canvas.className = "dss-bandwrap";
    this.canvas.style.height = "";
    bands.forEach(function (band) { self.renderBand(band); });
  };

  // ---- section management ----
  //
  // ponytail: window.prompt for the title. It works in the Desk and the render
  // harness alike; swap for a Frappe dialog if the interaction ever needs more
  // than one field.

  // Call a section endpoint, or just mutate local state when there is no
  // backend — the mock path keeps the view usable without pretending to persist.
  App.prototype.sectionCall = function (method, args, mockApply, describe) {
    var self = this;
    if (this.state.mock || !hasFrappe()) {
      mockApply();
      this.refresh();
      toast(describe + " (mock — not persisted)");
      return;
    }
    root.frappe.call({ method: "dashboard_studio.api.studio." + method, args: args })
      .then(function () { self.reloadDashboard(describe); })
      .catch(function () { toast("Could not " + describe.toLowerCase()); });
  };

  // Re-read the dashboard so section order and chart assignment come back from
  // the server rather than being guessed at locally.
  App.prototype.reloadDashboard = function (describe) {
    var self = this;
    root.frappe.call({
      method: "dashboard_studio.api.studio.get_studio_dashboard",
      args: { dashboard: this.options.dashboard },
    }).then(function (r) {
      var data = r.message || {};
      self.state.charts = data.charts || [];
      self.state.sections = data.sections || [];
      if (self.state.view === "design") self.refresh();
      toast(describe);
    });
  };

  App.prototype.addSection = function () {
    var title = (root.prompt && root.prompt("New section title")) || "";
    title = title.trim();
    if (!title) return;
    var self = this;
    this.sectionCall(
      "create_section",
      { dashboard: this.options.dashboard, section_title: title },
      function () {
        self.state.sections = (self.state.sections || []).concat([{
          name: "mock-sec-" + (self.state.sections.length + 1),
          section_title: title,
          sort_order: self.state.sections.length + 1,
        }]);
      },
      "Added section “" + title + "”"
    );
  };

  App.prototype.renameSection = function (band) {
    var title = (root.prompt && root.prompt("Rename section", band.title)) || "";
    title = title.trim();
    if (!title || title === band.title) return;
    var self = this;
    this.sectionCall(
      "update_section",
      { section: band.name, patch: JSON.stringify({ section_title: title }) },
      function () {
        (self.state.sections || []).forEach(function (s) {
          if (s.name === band.name) s.section_title = title;
        });
      },
      "Renamed section to “" + title + "”"
    );
  };

  App.prototype.moveSection = function (name, delta) {
    var order = core.moveSection(this.state.sections, name, delta);
    if (!order) return; // already at the end it is moving toward
    var self = this;
    this.sectionCall(
      "reorder_sections",
      { dashboard: this.options.dashboard, order: JSON.stringify(order) },
      function () {
        var byName = {};
        self.state.sections.forEach(function (s) { byName[s.name] = s; });
        self.state.sections = order.map(function (n) { return byName[n]; });
      },
      "Reordered sections"
    );
  };

  App.prototype.deleteSection = function (band) {
    var count = band.charts.length;
    var warning = "Delete section “" + band.title + "”?" +
      (count ? "\n\nIts " + count + " chart(s) will be kept and moved to Ungrouped." : "");
    if (root.confirm && !root.confirm(warning)) return;
    var self = this;
    this.sectionCall(
      "delete_section",
      { section: band.name },
      function () {
        // Mirror the server: keep the charts, just un-assign them.
        self.state.sections = (self.state.sections || []).filter(function (s) {
          return s.name !== band.name;
        });
        self.state.charts.forEach(function (chart) {
          if (chart.section === band.name) chart.section = null;
        });
      },
      "Deleted section “" + band.title + "”" + (count ? "; " + count + " chart(s) kept" : "")
    );
  };

  App.prototype.isBandCollapsed = function (band) {
    var key = band.name || "__ungrouped__";
    var overrides = this.state.collapsedSections || {};
    return key in overrides ? overrides[key] : band.collapsed;
  };

  App.prototype.renderBand = function (band) {
    var self = this;
    var collapsed = this.isBandCollapsed(band);
    var wrap = el("div", "dss-band");

    var head = el("div", "dss-band-head");
    var toggle = el("button", "dss-band-toggle", (collapsed ? "▸ " : "▾ ") + band.title);
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    toggle.addEventListener("click", function () {
      self.state.collapsedSections[band.name || "__ungrouped__"] = !collapsed;
      self.refresh();
    });
    head.appendChild(toggle);
    head.appendChild(el("span", "dss-band-count", band.charts.length + " chart(s)"));

    // Ungrouped is a derived bucket, not a record — it has nothing to manage.
    if (band.name) {
      var controls = el("div", "dss-band-controls");
      [
        ["↑", "Move section up", function () { self.moveSection(band.name, -1); }],
        ["↓", "Move section down", function () { self.moveSection(band.name, 1); }],
        ["Rename", "Rename section", function () { self.renameSection(band); }],
        ["Delete", "Delete section (charts are kept)", function () { self.deleteSection(band); }],
      ].forEach(function (spec) {
        var btn = el("button", "dss-btn dss-btn-small", spec[0]);
        btn.title = spec[1];
        btn.addEventListener("click", spec[2]);
        controls.appendChild(btn);
      });
      head.appendChild(controls);
    }
    wrap.appendChild(head);

    if (!collapsed) {
      var surface = el("div", "dss-canvas dss-band-canvas");
      wrap.appendChild(surface);
      band.charts.forEach(function (chart) { self.renderCard(chart, surface); });
      this.fitCanvas(surface, band.charts);
    }
    this.canvas.appendChild(wrap);
  };

  // Cards are absolutely positioned, so a surface does not grow with them and
  // its overflow is hidden — without this, a card dragged past the fixed height
  // simply vanishes. Size the surface to its lowest card.
  App.prototype.fitCanvas = function (surface, charts) {
    var bottom = 0;
    (charts || []).forEach(function (chart) {
      var box = core.clampLayout(chart);
      bottom = Math.max(bottom, (box.pos_y + box.height) * ROW_H);
    });
    // A band only needs to fit its own charts; the flat canvas keeps its floor.
    var floor = surface === this.canvas ? 480 : 120;
    surface.style.height = Math.max(floor, bottom + 8) + "px";
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

    // Section assignment — only offered once the dashboard actually has
    // sections, so a single-section dashboard is not cluttered by an empty list.
    var sectionSelect = null;
    if ((this.state.sections || []).length) {
      sectionSelect = el("select", "dss-input");
      var none = el("option", null, "— Ungrouped —");
      none.value = "";
      if (!chart.section) none.selected = true;
      sectionSelect.appendChild(none);
      this.state.sections.forEach(function (s) {
        var o = el("option", null, s.section_title || s.name);
        o.value = s.name;
        if (s.name === chart.section) o.selected = true;
        sectionSelect.appendChild(o);
      });
      this.panel.appendChild(field("Section", sectionSelect));
    }

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

    var cardActions = el("div", "dss-actions dss-card-actions");
    var dupBtn = el("button", "dss-btn dss-btn-small", "Duplicate");
    dupBtn.title = "Create a copy of this chart on the same dashboard";
    dupBtn.addEventListener("click", function () { self.addChart(null, chart.name); });
    cardActions.appendChild(dupBtn);
    var delBtn = el("button", "dss-btn dss-btn-small dss-btn-danger", "Delete");
    delBtn.title = "Remove this chart. Its metric is kept.";
    delBtn.addEventListener("click", function () { self.deleteChart(chart); });
    cardActions.appendChild(delBtn);
    this.panel.appendChild(cardActions);

    function collect() {
      var patch = {
        chart_title: titleInput.value,
        chart_type: typeSelect.value,
        description: descInput.value,
        metric: metricSelect.value || chart.metric,
      };
      if (sectionSelect) patch.section = sectionSelect.value || null;
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
      self.state.dirty = true; // Apply changes the in-memory chart only
      self.refresh();
      return chart;
    }
    applyBtn.addEventListener("click", applyEdit);
    saveBtn.addEventListener("click", function () {
      if (applyEdit()) self.saveChart(chart);
    });
  };

  // ---- Data & DocTypes: what records exist, and how the schema fits together ----

  App.prototype.renderCatalogue = function () {
    var self = this;
    this.canvas.className = "dss-bandwrap";
    this.canvas.style.height = "";
    this.canvas.innerHTML = "";
    this.panel.innerHTML = "";

    if (this.state.catalogue) { this.paintCatalogue(); return; }
    if (!hasFrappe()) {
      var mock = root.DSStudioMock || {};
      this.state.catalogue = mock.MOCK_CATALOGUE || { doctypes: [], relationships: [] };
      this.state.fieldCatalogue = mock.MOCK_FIELD_CATALOGUE || [];
      this.paintCatalogue();
      return;
    }
    this.canvas.appendChild(el("div", "dss-hint", "Loading catalogue…"));
    Promise.all([
      root.frappe.call({ method: "dashboard_studio.api.catalogue.get_catalogue" }),
      root.frappe.call({ method: "dashboard_studio.api.catalogue.get_field_catalogue" }),
    ]).then(function (responses) {
      self.state.catalogue = responses[0].message || { doctypes: [], relationships: [] };
      self.state.fieldCatalogue = responses[1].message || [];
      if (self.state.view === "data") self.paintCatalogue();
    }).catch(function () {
      if (self.state.view === "data") {
        self.canvas.innerHTML = '<div class="dss-hint">Could not load the catalogue.</div>';
      }
    });
  };

  App.prototype.paintCatalogue = function () {
    var self = this;
    this.canvas.innerHTML = "";
    var data = this.state.catalogue || {};

    // Record summary cards.
    var recordsBand = el("div", "dss-band");
    var recordsHead = el("div", "dss-band-head");
    recordsHead.appendChild(el("span", "dss-band-toggle", "Records"));
    recordsHead.appendChild(el("span", "dss-band-count",
      (data.doctypes || []).length + " doctype(s)"));
    recordsBand.appendChild(recordsHead);

    var grid = el("div", "dss-cat-grid");
    (data.doctypes || []).forEach(function (entry) {
      var card = el("div", "dss-cat-card");
      card.appendChild(el("div", "dss-node-kind", "DocType"));
      card.appendChild(el("div", "dss-cat-name", entry.doctype));
      card.appendChild(el("div", "dss-cat-count", String(entry.count)));
      var statuses = Object.keys(entry.statuses || {});
      if (statuses.length) {
        var pills = el("div", "dss-cat-pills");
        statuses.forEach(function (status) {
          pills.appendChild(el("span", "dss-pill is-" + status.toLowerCase().replace(/\s+/g, "-"),
            status + " " + entry.statuses[status]));
        });
        card.appendChild(pills);
      }
      if ((entry.recent || []).length) {
        card.appendChild(el("div", "dss-cat-recent", entry.recent.join(" · ")));
      }
      // The records themselves live in Frappe's own list view — link to it
      // rather than rebuilding a record browser here.
      if (hasFrappe()) {
        var open = el("button", "dss-btn dss-btn-small", "Open list");
        open.addEventListener("click", function () {
          root.frappe.set_route("List", entry.doctype);
        });
        card.appendChild(open);
      }
      grid.appendChild(card);
    });
    recordsBand.appendChild(grid);
    this.canvas.appendChild(recordsBand);

    // Relationship graph, from the real schema.
    var relBand = el("div", "dss-band");
    var relHead = el("div", "dss-band-head");
    relHead.appendChild(el("span", "dss-band-toggle", "Relationships"));
    relHead.appendChild(el("span", "dss-band-count", "parent · link · child"));
    relBand.appendChild(relHead);
    var relBody = el("div", "dss-rel-body");
    core.groupRelationships(data.relationships).forEach(function (group) {
      var row = el("div", "dss-rel-group");
      row.appendChild(el("div", "dss-rel-source", group.source));
      var list = el("div", "dss-rel-edges");
      group.edges.forEach(function (edge) {
        var e = el("div", "dss-rel-edge is-" + edge.kind);
        e.appendChild(el("span", "dss-rel-field", edge.fieldname));
        e.appendChild(el("span", "dss-rel-arrow", edge.kind === "child" ? "1 ─── ∞" : "1 ─── 1"));
        e.appendChild(el("span", "dss-rel-target",
          edge.target + (edge.self_reference ? " (self)" : "")));
        list.appendChild(e);
      });
      row.appendChild(list);
      relBand.appendChild(row);
    });
    relBand.appendChild(relBody);
    this.canvas.appendChild(relBand);

    this.paintFieldCatalogue();
  };

  // The real safe-field concept: each metric's allowlist. Field types and any
  // "restricted" classification are deliberately absent — nothing backs them.
  App.prototype.paintFieldCatalogue = function () {
    this.panel.innerHTML = "";
    this.panel.appendChild(el("h3", "dss-panel-title", "Safe field catalogue"));
    this.panel.appendChild(el("p", "dss-hint",
      "Fields each metric may reference. An empty allowlist blocks the metric from running."));

    (this.state.fieldCatalogue || []).forEach(function (row) {
      var card = el("div", "dss-field-card" + (row.executable ? "" : " is-blocked"));
      card.appendChild(el("div", "dss-cat-name", row.metric_name || row.metric));
      card.appendChild(el("div", "dss-node-kind", row.source_doctype || "—"));
      if (row.fields.length) {
        var tags = el("div", "dss-cat-pills");
        row.fields.forEach(function (field) {
          tags.appendChild(el("span", "dss-pill is-allowed", field));
        });
        card.appendChild(tags);
      } else {
        card.appendChild(el("div", "dss-field-warn", "No allowed fields — cannot run"));
      }
      if (hasFrappe()) {
        var edit = el("button", "dss-btn dss-btn-small", "Edit metric");
        edit.addEventListener("click", function () {
          root.frappe.set_route("Form", "DS Metric", row.metric);
        });
        card.appendChild(edit);
      }
      this.panel.appendChild(card);
    }, this);

    // Say plainly what is NOT shown, rather than showing an invented version of it.
    this.panel.appendChild(el("p", "dss-hint dss-note",
      "Field types and a Restricted/Blocked classification are not shown: the " +
      "allowlist is the control this app enforces, and there is no denylist to read."));
  };

  // ---- Validation Centre: source vs target, with human-only acceptance ----

  App.prototype.renderValidation = function () {
    var self = this;
    this.canvas.className = "dss-bandwrap";
    this.canvas.style.height = "";
    this.canvas.innerHTML = "";

    if (this.state.comparisons) { this.paintValidation(); return; }
    if (!hasFrappe()) {
      this.state.comparisons = ((root.DSStudioMock || {}).MOCK_COMPARISONS || []).map(
        function (row) { return Object.assign({}, row); });
      this.paintValidation();
      return;
    }
    this.canvas.appendChild(el("div", "dss-hint", "Loading comparisons…"));
    root.frappe.call({ method: "dashboard_studio.api.validation.list_comparisons" })
      .then(function (r) {
        self.state.comparisons = r.message || [];
        if (self.state.view === "validation") self.paintValidation();
      })
      .catch(function () {
        if (self.state.view === "validation") {
          self.canvas.innerHTML = '<div class="dss-hint">Could not load comparisons.</div>';
        }
      });
  };

  // Entry point for run_validation. Without this the endpoint existed but there
  // was no way to start a comparison from the editor — only to read old ones.
  App.prototype.buildValidationRun = function () {
    var self = this;
    var wrap = el("div", "dss-sqlimport");
    var head = el("div", "dss-sqlimport-head");
    head.appendChild(el("div", "dss-kicker", "Step 1 — reference result"));
    head.appendChild(el("h3", "dss-sqlimport-title", "Run a validation"));
    wrap.appendChild(head);
    wrap.appendChild(el("p", "dss-hint",
      "Paste what the source system reports for a chart, one group per line as " +
      "“group, value”. This app runs the chart's own metric and compares " +
      "the two group by group. A blank value stays blank — it is flagged as " +
      "uncomparable, never read as zero."));

    // Only charts that have a metric can be validated: without one there is
    // nothing for this app to compute and compare against.
    var charts = (this.state.charts || []).filter(function (c) { return c.metric; });
    if (!charts.length) {
      wrap.appendChild(el("p", "dss-hint dss-note",
        "No chart on this dashboard has a metric, so there is nothing to validate yet."));
      return wrap;
    }

    var picker = el("select", "dss-input");
    picker.setAttribute("aria-label", "Chart to validate");
    charts.forEach(function (c) {
      var opt = el("option", null, c.chart_title || c.name);
      opt.value = c.name;
      picker.appendChild(opt);
    });
    wrap.appendChild(picker);

    var box = el("textarea", "dss-input");
    box.placeholder = "2022, 62\n2023, 57";
    box.setAttribute("aria-label", "Reference result");
    wrap.appendChild(box);

    var note = el("div", "dss-sqlnote");
    var run = el("button", "dss-btn dss-btn-primary", "Run validation");
    run.addEventListener("click", function () {
      var parsed = core.parseReferenceRows(box.value);
      if (parsed.errors.length) {
        note.textContent = "Could not read: " + parsed.errors.join("; ");
        return;
      }
      if (!parsed.rows.length) { note.textContent = "Paste a reference result first."; return; }
      if (!hasFrappe()) {
        note.textContent = "Running a validation needs the server (not available in sample mode).";
        return;
      }
      note.textContent = "Comparing…";
      root.frappe.call({
        method: "dashboard_studio.api.validation.run_validation",
        args: { chart: picker.value, source_rows: JSON.stringify(parsed.rows) },
      }).then(function (r) {
        var result = r.message || {};
        toast("Validation recorded: " + result.status);
        self.state.comparisons = null; // refetched by renderValidation
        self.render();
      }).catch(function () {
        note.textContent = "Could not run that validation.";
      });
    });
    var actions = el("div", "dss-sqlimport-actions");
    actions.appendChild(run);
    actions.appendChild(note);
    wrap.appendChild(actions);
    return wrap;
  };

  App.prototype.paintValidation = function () {
    var self = this;
    this.canvas.innerHTML = "";
    var rows = this.state.comparisons || [];
    var summary = core.validationSummary(rows);

    var band = el("div", "dss-band");
    var head = el("div", "dss-band-head");
    head.appendChild(el("span", "dss-band-toggle", "Validation results"));
    var chips = el("div", "dss-cat-pills");
    ["Match", "Discrepancy", "Flagged", "Accepted"].forEach(function (status) {
      if (!summary[status]) return;
      chips.appendChild(el("span", "dss-pill is-" + status.toLowerCase(),
        summary[status] + " " + status.toLowerCase()));
    });
    head.appendChild(chips);
    band.appendChild(head);

    var table = el("table", "dss-val-table");
    var thead = el("thead");
    var hrow = el("tr");
    ["Chart", "Source", "Target", "Difference", "Status", ""].forEach(function (label) {
      hrow.appendChild(el("th", null, label));
    });
    thead.appendChild(hrow);
    table.appendChild(thead);

    var tbody = el("tbody");
    if (!rows.length) {
      var empty = el("tr");
      var cell = el("td", "dss-hint", "No comparisons recorded yet.");
      cell.colSpan = 6;
      empty.appendChild(cell);
      tbody.appendChild(empty);
    }
    rows.forEach(function (row) {
      var tr = el("tr", "is-" + String(row.status || "").toLowerCase());
      var chartCell = el("td");
      var expand = el("button", "dss-expand",
        (self.state.expandedComparison === row.name ? "▾ " : "▸ ") + (row.chart || "—"));
      expand.title = "Show the per-group breakdown";
      expand.addEventListener("click", function () { self.toggleComparison(row); });
      chartCell.appendChild(expand);
      tr.appendChild(chartCell);
      tr.appendChild(el("td", "dss-num", row.original_value === "" ? "—" : row.original_value));
      // A blank target is a missing result, not a zero — say so.
      tr.appendChild(el("td", "dss-num", row.new_value === "" ? "missing" : row.new_value));
      tr.appendChild(el("td", "dss-num",
        row.difference_pct == null ? "—" : Number(row.difference_pct).toFixed(1) + "%"));
      var statusCell = el("td");
      statusCell.appendChild(el("span", "dss-pill is-" + String(row.status || "").toLowerCase(),
        row.status || "—"));
      tr.appendChild(statusCell);

      var action = el("td");
      if (core.canAccept(row)) {
        var btn = el("button", "dss-btn dss-btn-small", "Accept…");
        btn.title = "Accept this difference (a reason is required)";
        btn.addEventListener("click", function () { self.acceptComparison(row); });
        action.appendChild(btn);
      } else if (row.status === "Accepted") {
        action.appendChild(el("span", "dss-val-reason",
          row.accepted_reason + (row.reviewed_by ? " — " + row.reviewed_by : "")));
      }
      tr.appendChild(action);
      tbody.appendChild(tr);

      // Per-group breakdown — the detail the summary totals are made of.
      if (self.state.expandedComparison === row.name) {
        var detail = el("tr", "dss-detail-row");
        var cell = el("td");
        cell.colSpan = 6;
        var groups = row.comparison_rows;
        if (!groups) {
          cell.appendChild(el("div", "dss-hint", "Loading breakdown…"));
        } else if (!groups.length) {
          cell.appendChild(el("div", "dss-hint", "No per-group detail recorded for this run."));
        } else {
          var inner = el("table", "dss-val-table dss-val-inner");
          var ihead = el("tr");
          ["Group", "Source", "Target", "Diff", "Diff %", "Status"].forEach(function (label) {
            ihead.appendChild(el("th", null, label));
          });
          inner.appendChild(ihead);
          groups.forEach(function (g) {
            var gtr = el("tr", "is-" + String(g.status || "").toLowerCase());
            gtr.appendChild(el("td", null, g.group_label));
            gtr.appendChild(el("td", "dss-num", g.original_value === "" ? "—" : g.original_value));
            // Blank stays blank: an incomparable value is not a zero.
            gtr.appendChild(el("td", "dss-num", g.new_value === "" ? "missing" : g.new_value));
            gtr.appendChild(el("td", "dss-num", g.difference === "" ? "—" : g.difference));
            gtr.appendChild(el("td", "dss-num", g.difference_pct === "" ? "—" : g.difference_pct));
            var gs = el("td");
            gs.appendChild(el("span", "dss-pill is-" + String(g.status || "").toLowerCase(),
              g.status || "—"));
            if (g.reason) gs.appendChild(el("span", "dss-val-reason", " " + g.reason));
            gtr.appendChild(gs);
            inner.appendChild(gtr);
          });
          cell.appendChild(inner);
        }
        detail.appendChild(cell);
        tbody.appendChild(detail);
      }
    });
    table.appendChild(tbody);
    band.appendChild(table);
    this.canvas.appendChild(band);

    this.panel.innerHTML = "";
    this.panel.appendChild(el("h3", "dss-panel-title", "Validation"));
    this.panel.appendChild(el("p", "dss-hint",
      "Each row compares a reference result against this app's result for the same chart. " +
      "Flagged means a value could not be compared at all — that is different from a " +
      "difference, and is treated as more serious."));
    this.panel.appendChild(el("p", "dss-hint",
      "Accepting a difference is a human decision: it always requires a reason and records " +
      "who accepted it. Nothing is ever marked Accepted automatically."));
  };

  // Expand a run to show its per-group rows, fetching them once if needed.
  App.prototype.toggleComparison = function (row) {
    var self = this;
    if (this.state.expandedComparison === row.name) {
      this.state.expandedComparison = null;
      this.paintValidation();
      return;
    }
    this.state.expandedComparison = row.name;
    if (row.comparison_rows || !hasFrappe()) {
      // Mock rows are already attached; nothing to fetch.
      if (!row.comparison_rows) row.comparison_rows = [];
      this.paintValidation();
      return;
    }
    this.paintValidation(); // show "Loading breakdown…" immediately
    root.frappe.call({
      method: "dashboard_studio.api.validation.get_comparison",
      args: { comparison: row.name },
    }).then(function (r) {
      row.comparison_rows = (r.message || {}).comparison_rows || [];
      if (self.state.view === "validation") self.paintValidation();
    }).catch(function () {
      row.comparison_rows = [];
      if (self.state.view === "validation") self.paintValidation();
    });
  };

  App.prototype.acceptComparison = function (row) {
    var reason = (root.prompt && root.prompt(
      "Reason for accepting this difference (required):", "")) || "";
    reason = reason.trim();
    if (!reason) {
      toast("Not accepted — a reason is required.");
      return;
    }
    var self = this;
    if (!hasFrappe()) {
      row.status = "Accepted";
      row.accepted_reason = reason;
      row.reviewed_by = "(mock)";
      this.paintValidation();
      toast("Accepted (mock — not persisted)");
      return;
    }
    root.frappe.call({
      method: "dashboard_studio.api.validation.accept_comparison",
      args: { comparison: row.name, accepted_reason: reason },
    }).then(function () {
      self.state.comparisons = null; // re-read from the server
      self.renderValidation();
      toast("Difference accepted");
    }).catch(function () { toast("Could not accept that difference."); });
  };

  // ---- Governance & Publish: four-stage workflow with separated duties ----

  App.prototype.renderGovernance = function () {
    var self = this;
    this.canvas.className = "dss-bandwrap";
    this.canvas.style.height = "";
    this.canvas.innerHTML = "";

    if (this.state.governance) { this.paintGovernance(); return; }
    if (!hasFrappe() || !this.options.dashboard) {
      this.state.governance = (root.DSStudioMock || {}).MOCK_GOVERNANCE || null;
      this.paintGovernance();
      return;
    }
    this.canvas.appendChild(el("div", "dss-hint", "Loading governance…"));
    root.frappe.call({
      method: "dashboard_studio.api.governance.get_governance",
      args: { dashboard: this.options.dashboard },
    }).then(function (r) {
      self.state.governance = r.message || null;
      if (self.state.view === "governance") self.paintGovernance();
    }).catch(function () {
      if (self.state.view === "governance") {
        self.canvas.innerHTML = '<div class="dss-hint">Could not load governance.</div>';
      }
    });
  };

  App.prototype.paintGovernance = function () {
    var self = this;
    this.canvas.innerHTML = "";
    this.panel.innerHTML = "";
    var gov = this.state.governance;
    if (!gov) {
      this.canvas.appendChild(el("div", "dss-hint", "No dashboard selected."));
      return;
    }

    // Stage indicator.
    var band = el("div", "dss-band");
    var head = el("div", "dss-band-head");
    head.appendChild(el("span", "dss-band-toggle", "Workflow"));
    head.appendChild(el("span", "dss-band-count", gov.status));
    band.appendChild(head);

    var stepper = el("div", "dss-stepper");
    var reached = gov.stages.indexOf(gov.status);
    gov.stages.forEach(function (stage, index) {
      var state = index < reached ? " is-done" : (index === reached ? " is-current" : "");
      var step = el("div", "dss-step" + state);
      step.appendChild(el("span", "dss-step-dot", String(index + 1)));
      step.appendChild(el("span", "dss-step-label", stage));
      stepper.appendChild(step);
    });
    // Archived sits outside the forward path, so it is shown only when reached.
    if (gov.stages.indexOf(gov.status) === -1) {
      stepper.appendChild(el("div", "dss-step is-current", gov.status));
    }
    band.appendChild(stepper);

    var actions = el("div", "dss-gov-actions");
    (gov.transitions || []).forEach(function (move) {
      var btn = el("button", "dss-btn" + (move.allowed ? " dss-btn-primary" : ""), move.label);
      if (!move.allowed) {
        btn.disabled = true;
        // Say WHY it is unavailable rather than hiding the step.
        btn.title = "Requires: " + move.requires.join(" or ");
        btn.className += " is-disabled";
      } else {
        btn.addEventListener("click", function () { self.advanceStage(move); });
      }
      actions.appendChild(btn);
    });
    band.appendChild(actions);
    this.canvas.appendChild(band);

    // Change impact — every number here is computed from real Link fields.
    var impact = gov.impact || {};
    var impactBand = el("div", "dss-band");
    var impactHead = el("div", "dss-band-head");
    impactHead.appendChild(el("span", "dss-band-toggle", "Change impact"));
    impactBand.appendChild(impactHead);
    var stats = el("div", "dss-cat-grid");
    [["Charts", impact.charts], ["Sections", impact.sections], ["Metrics", impact.metrics]]
      .forEach(function (pair) {
        var card = el("div", "dss-cat-card");
        card.appendChild(el("div", "dss-node-kind", pair[0]));
        card.appendChild(el("div", "dss-cat-count", String(pair[1] == null ? "—" : pair[1])));
        stats.appendChild(card);
      });
    impactBand.appendChild(stats);
    (impact.shared_metrics || []).forEach(function (row) {
      impactBand.appendChild(el("div", "dss-gov-warn",
        "“" + row.metric + "” is used by " + row.used_by_charts +
        " charts — changing it affects all of them."));
    });
    this.canvas.appendChild(impactBand);

    // Native Frappe version history, not a bespoke one.
    this.panel.appendChild(el("h3", "dss-panel-title", "Version history"));
    this.panel.appendChild(el("p", "dss-hint",
      "Frappe records every change automatically; this is that history, not a separate one."));
    var versions = gov.versions || [];
    if (!versions.length) this.panel.appendChild(el("p", "dss-hint", "No changes recorded yet."));
    versions.forEach(function (v) {
      var row = el("div", "dss-ver-row");
      row.appendChild(el("div", "dss-ver-when", v.creation));
      row.appendChild(el("div", "dss-ver-who", v.owner));
      self.panel.appendChild(row);
    });
    this.panel.appendChild(el("p", "dss-hint",
      "Publishing is separated from editing: an Editor can submit work for approval, " +
      "but only a QA Approver can publish it."));
  };

  App.prototype.advanceStage = function (move) {
    var self = this;
    if (!hasFrappe() || !this.options.dashboard) {
      this.state.governance.status = move.to;
      this.paintGovernance();
      toast("Moved to " + move.to + " (mock — not persisted)");
      return;
    }
    root.frappe.call({
      method: "dashboard_studio.api.governance.advance_status",
      args: { dashboard: this.options.dashboard, to_status: move.to },
    }).then(function (r) {
      self.state.governance = null; // re-read, so the next legal moves come from the server
      self.renderGovernance();
      toast((r.message || {}).applied || "Updated");
    }).catch(function () { toast("That move was refused."); });
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
  };

  // Paste Metabase SQL — the way a migration starts. The parser reports what it
  // found and suggests identity mappings, which the user then confirms or
  // rejects. Returned as an element so the caller can place it prominently
  // instead of tucking it under the mapping list.
  App.prototype.buildSqlImport = function () {
    var self = this;
    var wrap = el("div", "dss-sqlimport");
    var head = el("div", "dss-sqlimport-head");
    head.appendChild(el("div", "dss-kicker", "Step 1 — import"));
    head.appendChild(el("h3", "dss-sqlimport-title", "Paste the Metabase SQL"));
    wrap.appendChild(head);
    wrap.appendChild(el("p", "dss-hint",
      "Copy the query behind a Metabase card and paste it here. Tables it finds " +
      "become nodes on the canvas below; a query it cannot safely translate is " +
      "reported with reasons and nothing is suggested for it."));

    var box = el("textarea", "dss-input");
    box.placeholder = "SELECT COUNT(*) FROM `tabStudent Applicant` WHERE …";
    box.setAttribute("aria-label", "Metabase SQL");
    wrap.appendChild(box);

    var note = el("div", "dss-sqlnote");

    var analyze = el("button", "dss-btn dss-btn-primary", "Analyze SQL");
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
    var actions = el("div", "dss-sqlimport-actions");
    actions.appendChild(analyze);
    actions.appendChild(note);
    wrap.appendChild(actions);
    // The other prototype import routes (dashboard URL / API, result CSV) are
    // not built — say so rather than showing dead controls.
    wrap.appendChild(el("p", "dss-hint dss-note",
      "Pasting SQL is the only import route. Importing straight from a Metabase " +
      "URL or API is not built."));
    return wrap;
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
  // Source DocType for a metric, for the card footer. Synchronous by design —
  // cards redraw constantly — so it warms the metric list once and repaints
  // when it lands, rather than blocking the first render on a call.
  App.prototype.metricSource = function (metricName) {
    if (!metricName) return null;
    var self = this;
    if (!this._metricList) {
      if (!this._metricListWarming) {
        this._metricListWarming = true;
        this.availableMetrics(function () {
          if (self.state.view === "design") self.refresh();
        });
      }
      return null;
    }
    var match = this._metricList.filter(function (m) { return m.name === metricName; })[0];
    return (match && match.source_doctype) || null;
  };

  App.prototype.availableMetrics = function (callback) {
    if (this.state.mock || !hasFrappe()) {
      var mock = root.DSStudioMock || {};
      var sources = {};
      (mock.MOCK_FIELD_CATALOGUE || []).forEach(function (row) {
        sources[row.metric_name] = row.source_doctype;
      });
      this._metricList = Object.keys(mock.MOCK_METRIC_RESULTS || {})
        .map(function (name) { return { name: name, source_doctype: sources[name] }; });
      callback(this._metricList);
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
          section: chart.section || null,
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
    })).then(function () {
      self.state.dirty = false;
      toast("Saved layout for " + self.state.charts.length + " charts");
      self.render();
    });
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
