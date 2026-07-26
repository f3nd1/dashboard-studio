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
    mapping: ["Source mapping", "Map a source query onto DocTypes",
      "Paste the query behind a Metabase card. Tables it finds become nodes you " +
      "map to DocTypes; anything it cannot safely translate is reported with " +
      "reasons and nothing is suggested for it."],
    data: ["Source of truth", "Records, relationships and safe fields",
      "What this app has stored, how those records link to each other, and which " +
      "fields each metric is allowed to read."],
    validation: ["Result comparison", "Validation Centre",
      "Compare a reference result against this app's result for the same chart " +
      "before publishing. Differences are only ever accepted by a person."],
    visualize: ["Visualize", "Turn a query into an Insights chart",
      "Two steps: paste the query, then fill in the few things raw SQL cannot " +
      "say — title, axes, shape. Studio creates the Insights query; once you have " +
      "run it there, it can set the axes on the chart Insights made for it."],
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

  // EVERY server call goes through here. Frappe RESOLVES this promise when the
  // server refused: the ajax .always path hands back the error payload instead
  // of rejecting, so `.then(r => r.message)` sees undefined and cannot tell
  // "worked, returned nothing" from "threw". That is how creating a migration
  // project failed in total silence — request sent, refusal returned, .then ran,
  // nothing said. Normalise it once, here, into a real rejection carrying the
  // server's own text, which refusalMessage() already knows how to read.
  //
  // A missing `message` is NOT an error: get_migration_project returns null for
  // an empty project. Only an explicit refusal marker counts.
  function dsCall(opts) {
    return root.frappe.call(opts).then(function (r) {
      r = r || {};
      if (r.exc_type || r.exc || r._server_messages) {
        // Empty message on purpose: refusalMessage() prefers err.message, so a
        // class name like "ValidationError" here would hide the server's actual
        // sentence. Only fall back to the class when there is no sentence.
        var e = new Error(r._server_messages ? "" : (r.exc_type || ""));
        e._server_messages = r._server_messages;
        e.exc = r.exc;
        throw e;
      }
      return r;
    });
  }

  function toast(msg) {
    if (hasFrappe() && root.frappe.show_alert) root.frappe.show_alert({ message: msg, indicator: "blue" });
    else if (root.console) root.console.log("[Dashboard Studio] " + msg);
  }

  // A refused frappe.call carries the server's own message. The publish gate
  // names every offending chart in that message; discarding it and toasting a
  // generic line is how a refusal that knew the answer stopped giving it.
  //
  // ponytail: reads the two shapes Frappe puts a thrown message in. Frappe also
  // raises its own dialog for _server_messages, so this may be the second place
  // the text appears — a duplicate is a far cheaper fault than a swallowed one.
  function refusalMessage(err, fallback) {
    var raw = err && (err.message || err._server_messages);
    if (typeof raw === "string" && raw.charAt(0) === "[") {
      try { raw = JSON.parse(JSON.parse(raw)[0]).message; } catch (e) { /* not that shape */ }
    }
    if (typeof raw !== "string" || !raw.trim()) return fallback;
    return raw.replace(/<[^>]*>/g, "").trim() || fallback;
  }

  // How far the pointer may travel between mousedown and mouseup and still count
  // as a click. The old rule was |dx|+|dy| > 3, which trips at 2px diagonal —
  // essentially every trackpad click — so clicking a node did nothing on the
  // real site while a Playwright click, which moves zero pixels, passed.
  //
  // ponytail: 12px flat. Deliberate drags travel far more; the cost is that a
  // sub-12px reposition is ignored, which no one needs.
  var DRAG_THRESHOLD_PX = 12;

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
      dirty: false, savedNote: null,
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
    dsCall({ method: "dashboard_studio.api.studio.list_dashboards" })
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
          // A row built from separate spans has no separator in its accessible
          // name, so "1234" + "Draft" is announced as "1234Draft". Name it
          // explicitly rather than padding the markup with whitespace, which
          // would fix the reading and leave the structure fragile.
          row.setAttribute("aria-label",
            core.dashboardTitle(d) + ", " + (d.status || "Draft"));
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
    dsCall({
      method: "dashboard_studio.api.studio.get_studio_dashboard",
      args: { dashboard: name },
    }).then(function (r) {
      var data = r.message || {};
      self.state.dashboard = data.dashboard;
      // Resolved server-side from the stored code — never persisted here.
      self.state.scope = data.scope || null;
      self.state.charts = data.charts || [];
      self.state.sections = data.sections || [];
      self.state.readiness = data.readiness || null;
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
    dsCall({ method: "dashboard_studio.api.studio.list_dashboards" })
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

  // In-canvas load failure. Matches the landing failure's shape: say what broke
  // and offer the retry, rather than printing the fact and stopping there.
  App.prototype.canvasError = function (message, retryFn) {
    var self = this;
    this.canvas.innerHTML = "";
    var box = el("div", "dss-loadfail");
    box.appendChild(el("p", "dss-hint", message));
    var retry = el("button", "dss-btn", "Try again");
    retry.addEventListener("click", function () { retryFn.call(self); });
    box.appendChild(retry);
    this.canvas.appendChild(box);
  };

  App.prototype.newDashboard = function () {
    var self = this;
    if (!hasFrappe()) { toast("Creating a dashboard needs the server."); return; }
    var title = root.prompt("Dashboard title");
    if (title == null) return;
    if (!title.trim()) { toast("A dashboard needs a title."); return; }
    dsCall({
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
    // The publish rules, in the one element that renders in every workspace.
    // Reaching Governance and only then discovering the work was incomplete is
    // the fault this fixes, so it cannot live inside a single view.
    var chip = this.buildReadinessChip();
    if (chip) head.appendChild(chip);
    // Unsaved-layout marker. saveLayout writes every chart unconditionally, so
    // without this there is no way to tell whether pressing it does anything.
    if (this.state.view === "design" && !this.state.mock) {
      head.appendChild(el("span",
        "dss-savestate" + (this.state.dirty ? " is-dirty" : "") +
          (this.state.savedNote ? " is-just-saved" : ""),
        this.state.savedNote ? "● " + this.state.savedNote
          : this.state.dirty ? "● Unsaved layout changes" : "● All changes saved"));
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
    [["design", "Dashboard Builder"], ["mapping", "Source Mapping"],
     ["visualize", "Visualize"], ["data", "Data & DocTypes"],
     ["validation", "Validation"],
     ["governance", "Governance & Publish"]].forEach(function (pair) {
      var v = pair[0];
      var active = self.state.view === v;
      var tab = el("button", "dss-tab" + (active ? " is-active" : ""), pair[1]);
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", active ? "true" : "false");
      tab.addEventListener("click", function () {
        // Returning to Visualize is the signal that the person may have run the
        // query in Insights meanwhile, so let the auto-apply have another go.
        if (v === "visualize") self._autoApplyTried = null;
        self.state.view = v;
        self.render();
      });
      tabs.appendChild(tab);
    });
    wrap.appendChild(tabs);

    // The Builder has no fixed hero — its heading is the dashboard title in the
    // toolbar — but DS Dashboard.description was being stored and never shown
    // anywhere. Reuses the hero block rather than adding a second style for it.
    var dashboard = this.state.dashboard || {};
    var scope = this.state.scope;
    if (this.state.view === "design" && dashboard.name) {
      // Kicker, title and subtitle, per the mockup's .canvas-hero. The two
      // right-aligned buttons there are skipped: neither has behaviour.
      var heroBox = el("section", "dss-canvashero");
      heroBox.appendChild(el("div", "dss-canvashero-kicker",
        scope ? scope.label + " · " + scope.subcriterion_title : "Unscoped dashboard"));
      heroBox.appendChild(el("h1", "dss-canvashero-title",
        dashboard.dashboard_title || dashboard.name));
      if (dashboard.description) {
        heroBox.appendChild(el("p", "dss-canvashero-sub", dashboard.description));
      }
      wrap.appendChild(heroBox);
    }

    var hero = HEROES[this.state.view];
    if (hero) {
      var heroBox = el("div", "dss-hero");
      heroBox.appendChild(el("div", "dss-kicker", hero[0]));
      heroBox.appendChild(el("h3", "dss-hero-title", hero[1]));
      heroBox.appendChild(el("p", "dss-hero-blurb", hero[2]));
      wrap.appendChild(heroBox);
    }

    // Visualize is a two-step flow, not a canvas with a side panel, so it takes
    // over the workspace body instead of borrowing the shared main block. The
    // canvas and panel are still created, detached, because code elsewhere reads
    // them without checking which view is up.
    if (this.state.view === "visualize") {
      wrap.appendChild(this.buildVisualize());
      this.canvas = el("div");
      this.panel = el("div");
      this.mount.appendChild(wrap);
      return;
    }

    // Source Mapping is a fixed-height stack so the split is real: the query box
    // takes a quarter, the canvas the rest. Without a bounded parent the box
    // grows to its content and pushes the canvas below the fold, which is what
    // "make it 25/75" kept failing to do.
    var stack = this.state.view === "mapping" ? el("div", "dss-mapstack") : wrap;
    if (stack !== wrap) wrap.appendChild(stack);

    // Pasting SQL is how a migration actually starts, so it leads the workspace
    // rather than sitting under the mapping list in the side panel.
    if (this.state.view === "mapping") stack.appendChild(this.buildSqlImport());
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
    stack.appendChild(main);

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

  // Data catalogue: the source DocTypes this dashboard's charts actually draw
  // on, per the mockup's Sources panel. No add button and no drag handles —
  // sources are a consequence of the metrics chosen, not something added here.
  App.prototype.buildSourceCatalogue = function () {
    var self = this;
    var box = el("div", "dss-sources");
    box.appendChild(el("div", "dss-kicker", "Data catalogue"));
    box.appendChild(el("h3", "dss-palette-title", "Sources"));

    var search = el("input", "dss-input dss-source-search");
    search.type = "search";
    search.placeholder = "Search sources";
    search.setAttribute("aria-label", "Search sources");
    search.value = this.state.sourceQuery || "";
    box.appendChild(search);

    var list = el("div", "dss-source-list");
    box.appendChild(list);

    function paint() {
      list.innerHTML = "";
      var rows = core.dashboardSources(
        self.state.charts,
        function (name) { return self.metricInfo(name); },
        self.state.sourceQuery
      );
      if (!rows.length) {
        // Two different nothings: nothing matched the search, versus nothing to
        // search. Only the second is worth pointing somewhere.
        list.appendChild(el("p", "dss-hint dss-note", self.state.sourceQuery
          ? "No source matches “" + self.state.sourceQuery + "”."
          : "No chart on this dashboard has a metric yet, so there are no sources. " +
            "Select a card and link a metric in the panel on the right."));
        return;
      }
      rows.forEach(function (row) {
        var item = el("div", "dss-source-item");
        item.appendChild(el("span", "dss-source-glyph", row.glyph));
        var copy = el("span", "dss-source-copy");
        copy.appendChild(el("strong", null, row.source));
        copy.appendChild(el("small", null, row.subtitle));
        item.appendChild(copy);
        list.appendChild(item);
      });
    }

    // Repaint the list only — re-rendering the panel would drop focus mid-type.
    search.addEventListener("input", function () {
      self.state.sourceQuery = search.value;
      paint();
    });
    paint();
    return box;
  };

  // Stage plus what blocks publishing, in every workspace, linking to the place
  // that lists the blockers in full. Nothing is computed here — see
  // core.readinessChip and governance.publish_readiness.
  App.prototype.buildReadinessChip = function () {
    var self = this;
    if (this.state.mock || !this.state.dashboard) return null;
    var model = core.readinessChip(
      this.state.readiness, (this.state.dashboard || {}).status);
    if (!model) return null;

    var chip = el("button", "dss-readiness is-" + model.tone, model.text);
    chip.type = "button";
    chip.title = model.detail + "\n\nOpen Governance & Publish";
    chip.addEventListener("click", function () {
      self.state.view = "governance";
      self.state.governance = null; // re-read, so the stage shown is the stored one
      self.render();
    });
    return chip;
  };

  // Re-read the publish rules after something that could have changed them.
  // Same server function as the gate; the chip repaints from the result.
  App.prototype.refreshReadiness = function () {
    var self = this;
    if (!hasFrappe() || this.state.mock || !this.currentDashboard()) return;
    dsCall({
      method: "dashboard_studio.api.governance.publish_readiness",
      args: { dashboard: this.currentDashboard() },
    }).then(function (r) {
      self.state.readiness = r.message || null;
      self.render();
    }).catch(function () { /* the chip keeps its last known state */ });
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

    // Dashboard scope. The record stores only the EduTrust code; the label comes
    // from the server so a retitle upstream never strands a stored string.
    if (!this.state.mock && this.state.dashboard) {
      wrap.appendChild(el("div", "dss-kicker", "Dashboard scope"));
      wrap.appendChild(el("h3", "dss-palette-title", "EduTrust subcriterion"));
      var scopeSelect = el("select", "dss-input");
      scopeSelect.setAttribute("aria-label", "EduTrust subcriterion");
      var current = this.state.dashboard.subcriterion || "";
      var none = el("option", null, "Choose a subcriterion…");
      none.value = "";
      if (!current) none.selected = true;
      scopeSelect.appendChild(none);
      (this.state.subcriteria || []).forEach(function (s) {
        var o = el("option", null, s.label + " · " + s.subcriterion_title);
        o.value = s.subcriterion;
        if (s.subcriterion === current) o.selected = true;
        scopeSelect.appendChild(o);
      });
      scopeSelect.addEventListener("change", function () {
        self.setScope(scopeSelect.value);
      });
      wrap.appendChild(scopeSelect);
      wrap.appendChild(el("p", "dss-hint dss-note",
        "Required before publishing — an unscoped dashboard has no section to " +
        "publish into."));
      this.loadSubcriteria();
    }

    wrap.appendChild(this.buildSourceCatalogue());

    wrap.appendChild(el("div", "dss-kicker", "Visual catalogue"));
    wrap.appendChild(el("h3", "dss-palette-title", "Charts"));

    var drawable = (root.DSStudioCharts || {}).SUPPORTED_CHART_TYPES || [];
    var list = el("div", "dss-palette-list");
    drawable.forEach(function (type) {
      var item = el("button", "dss-palette-item");
      item.type = "button";
      // The palette is where charts are CREATED, so this is the constraint that
      // matters most: three of the eight drawable types have no plugin on the
      // receiving platform, and creating one makes work that cannot be published.
      var blocked = core.UNPUBLISHABLE_CHART_TYPES.indexOf(type) !== -1;
      if (blocked) {
        item.disabled = true;
        item.className += " is-blocked";
        item.title = type + " cannot be published: the receiving platform has no " +
          "plugin for it and would draw it as a bar chart with no warning. " +
          "See docs/CHART_TYPE_MAPPING.md.";
      } else {
        item.title = "Add a " + type + " to this dashboard";
        item.addEventListener("click", function () { self.addChart(type); });
      }
      item.appendChild(el("span", "dss-palette-glyph", PALETTE_GLYPHS[type] || "▦"));
      item.appendChild(el("span", "dss-palette-label", type));
      if (blocked) item.appendChild(el("span", "dss-palette-note", "not publishable"));
      list.appendChild(item);
    });
    wrap.appendChild(list);
    // One sentence: the control's immediate effect. Positioning is discoverable,
    // and linking a metric now belongs on the card that needs one.
    wrap.appendChild(el("p", "dss-hint", "Adds a card below the existing ones."));
    return wrap;
  };

  // Confirm a write that already succeeded. Without this a scope change — which
  // persists immediately — moved the indicator from "All changes saved" to "All
  // changes saved", so a successful silent write looked identical to nothing
  // happening. The note clears itself so it never reads as permanent state.
  App.prototype.markSaved = function (note) {
    var self = this;
    this.state.dirty = false;
    this.state.savedNote = note;
    root.clearTimeout(this._savedTimer);
    this._savedTimer = root.setTimeout(function () {
      self.state.savedNote = null;
      if (self.state.view === "design") self.render();
    }, 4000);
    this.render();
  };

  App.prototype.loadSubcriteria = function () {
    var self = this;
    if (this.state.subcriteria || this._subcriteriaWarming || !hasFrappe()) return;
    this._subcriteriaWarming = true;
    dsCall({ method: "dashboard_studio.api.studio.list_subcriteria" })
      .then(function (r) {
        self.state.subcriteria = r.message || [];
        if (self.state.view === "design") self.render();
      })
      .catch(function () { self._subcriteriaWarming = false; });
  };

  App.prototype.setScope = function (code) {
    var self = this;
    dsCall({
      method: "dashboard_studio.api.studio.set_dashboard_scope",
      args: { dashboard: this.state.dashboard.name, subcriterion: code || null },
    }).then(function (r) {
      var result = r.message || {};
      self.state.dashboard.subcriterion = result.subcriterion || "";
      self.state.scope = result.scope || null;
      toast(result.scope ? "Scoped to " + result.scope.label : "Scope cleared");
      self.markSaved(result.scope ? "Scope saved" : "Scope cleared");
      self.refreshReadiness();   // scope is one of the four publish rules
    }).catch(function () {
      toast("Could not set the dashboard scope.");
    });
  };

  App.prototype.addChart = function (chartType, copyFrom) {
    var self = this;
    var dashboard = this.state.dashboard && this.state.dashboard.name;
    if (this.state.mock || !hasFrappe() || !dashboard) {
      toast("Adding a chart needs a live dashboard (not available in sample mode).");
      return;
    }
    dsCall({
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
    dsCall({
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
  // The empty-card state, built as nodes rather than an HTML string: the hint
  // carries a metric name, which is user-authored text. Concatenating it into
  // innerHTML would make a chart title an injection point on every card.
  function noChart(title, hint) {
    var box = el("div", "dss-nochart", title);
    if (hint) box.appendChild(el("span", null, hint));
    return box;
  }

  App.prototype.renderChartBody = function (body, chart) {
    var charts = root.DSStudioCharts;
    // The remedy belongs here, on the card that has the problem, rather than in
    // the palette hint where it was one of three instructions on a control that
    // does something else. "No metric linked" used to be the only state handled
    // this way; an unapproved metric took the fetch path and came back as
    // Frappe's traceback dialog. Same treatment for every reason now.
    var blocked = core.chartBlockReason(chart);
    if (blocked) {
      body.innerHTML = "";
      body.appendChild(noChart(blocked.title, blocked.hint));
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
      body.innerHTML = "";
      if (cached && cached.__error) {
        // The server's own sentence, not "Metric failed to run". The engine's
        // refusals name the metric and the field; discarding that and printing a
        // flat line is how a refusal that knew the answer stopped giving it.
        body.appendChild(noChart("Metric could not run", cached.__error));
      } else {
        body.innerHTML =
          charts.render(chart.chart_type, core.sortResultRows(cached, chart.sort_order)).html;
      }
      return;
    }
    var self = this;
    if (this.state.mock || !hasFrappe()) {
      var rows = ((root.DSStudioMock || {}).MOCK_METRIC_RESULTS || {})[chart.metric] || [];
      this._rowsCache[chart.metric] = rows;
      body.innerHTML = charts.render(
        chart.chart_type, core.sortResultRows(rows, chart.sort_order)).html;
      return;
    }
    this._rowsCache[chart.metric] = PENDING;
    body.innerHTML = '<div class="dss-nochart">Loading…</div>';
    dsCall({
      method: "dashboard_studio.api.metrics.run_ds_metric",
      args: { metric_name: chart.metric },
    }).then(function (r) {
      self._rowsCache[chart.metric] = r.message || [];
      // Cache the result either way, but only repaint if the user is still
      // looking at the Design view — otherwise this wipes the Mapping canvas.
      if (self.state.view === "design") self.refresh();
    }).catch(function (err) {
      // Remembered failure — no retry loop. Kept as a message rather than null so
      // the card can say WHAT failed: the checks above cannot cover a metric
      // un-approved after this page loaded, or a source DocType since deleted.
      self._rowsCache[chart.metric] = {
        __error: refusalMessage(err, "The server refused to run this metric."),
      };
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
    if (!this.canvas) return;   // same synchronous-warm case as renderPanel
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
    dsCall({ method: "dashboard_studio.api.studio." + method, args: args })
      .then(function () { self.reloadDashboard(describe); })
      .catch(function () { toast("Could not " + describe.toLowerCase()); });
  };

  // Re-read the dashboard so section order and chart assignment come back from
  // the server rather than being guessed at locally.
  // The dashboard actually open — NOT the one named in the route.
  //
  // options.dashboard is only set when the page was opened at
  // /app/dashboard-studio/<name>. The picker and the default landing both open a
  // dashboard through openDashboard() without touching it, so in every other
  // case it is null (a reload then asks the server for a dashboard called
  // "null", which 404s) or stale (pointing at whichever dashboard the route
  // named before the user switched).
  App.prototype.currentDashboard = function () {
    return (this.state.dashboard && this.state.dashboard.name) || this.options.dashboard || null;
  };

  App.prototype.reloadDashboard = function (describe) {
    var self = this;
    dsCall({
      method: "dashboard_studio.api.studio.get_studio_dashboard",
      args: { dashboard: this.currentDashboard() },
    }).then(function (r) {
      var data = r.message || {};
      self.state.charts = data.charts || [];
      self.state.sections = data.sections || [];
      // Adding or deleting a chart changes what blocks publishing, and this is
      // the path every such write already goes through.
      self.state.readiness = data.readiness || null;
      // Full render rather than refresh(): the chip lives in the toolbar, which
      // refresh() does not touch, and a stale chip is worse than no chip.
      self.render();
      toast(describe);
    }).catch(function () {
      // Without this the write succeeded server-side and the screen never
      // changed, so the natural response was to click again — which is how one
      // failure became six charts nobody could see.
      toast("Saved, but the dashboard could not be reloaded. Refresh to see it.");
    });
  };

  App.prototype.addSection = function () {
    var title = (root.prompt && root.prompt("New section title")) || "";
    title = title.trim();
    if (!title) return;
    var self = this;
    this.sectionCall(
      "create_section",
      { dashboard: this.currentDashboard(), section_title: title },
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
      { dashboard: this.currentDashboard(), order: JSON.stringify(order) },
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
    // The metric list can warm SYNCHRONOUSLY in mock mode, from inside
    // buildPalette — before render() has created the panel and canvas. Guard
    // here rather than at each caller: every path into the panel comes through
    // this function, and render() paints it a moment later anyway.
    if (!this.panel) return;
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
    core.chartTypeOptions(chart.chart_type, renderable).forEach(function (opt) {
      var o = el("option", null, opt.label);
      o.value = opt.value;
      o.selected = opt.selected;
      // Disabled, not omitted: a type that is missing from the list teaches
      // nothing, and the reason is the useful part.
      o.disabled = opt.disabled;
      if (opt.reason) o.title = opt.reason;
      typeSelect.appendChild(o);
    });
    // Width as the mockup's percentage select. No new field — these are
    // DS Chart.width values on the 12-column grid, labelled as the fraction they
    // are. It replaces the width box in the layout grid rather than sitting
    // beside it: two controls writing one value is a bug farm.
    var widthSelect = el("select", "dss-input");
    core.widthOptions(chart.width).forEach(function (o) {
      var opt = el("option", null, o.label);
      opt.value = String(o.value);
      if (o.value === Number(chart.width)) opt.selected = true;
      widthSelect.appendChild(opt);
    });
    this.panel.appendChild(twoUp(field("Visual type", typeSelect), field("Width", widthSelect)));

    var descInput = el("textarea", "dss-input");
    descInput.value = chart.description || "";
    this.panel.appendChild(field("Description", descInput));

    // Display order. Ascending is what the engine returns, so a chart saved
    // before this field existed keeps the order it has always had.
    var orderSelect = el("select", "dss-input");
    core.SORT_ORDERS.forEach(function (o) {
      var opt = el("option", null, o);
      opt.value = o;
      if (o === (chart.sort_order || "Ascending")) opt.selected = true;
      orderSelect.appendChild(opt);
    });
    this.panel.appendChild(field("Result order", orderSelect));

    // What the metric defines, shown as values rather than disabled inputs.
    // Source, dimension, measure and aggregation belong to the APPROVED
    // DS Metric — a chart selects a metric and controls presentation. Rendering
    // them as inputs, even disabled ones, would imply they are a chart's to set.
    var info = this.metricInfo(chart.metric) || {};
    var derived = el("div", "dss-derived");
    [["Data source", info.source_doctype],
     ["Dimension / X-axis", info.group_by_field],
     ["Measure / Y-axis", info.value_field],
     ["Aggregation", info.calculation_type]].forEach(function (pair) {
      var row = el("div", "dss-derived-row");
      row.appendChild(el("span", "dss-field-label", pair[0]));
      row.appendChild(el("span", "dss-derived-value" + (pair[1] ? "" : " is-unset"),
        pair[1] || (chart.metric ? "—" : "no metric linked")));
      derived.appendChild(row);
    });
    derived.appendChild(el("p", "dss-prop-help",
      "From the linked metric. Change these on the DS Metric, where they are approved."));
    this.panel.appendChild(derived);

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
    layoutWrap.appendChild(el("span", "dss-field-label", "Position and height (column, row, height)"));
    var layoutInputs = {};
    var grid = el("div", "dss-layout-grid");
    // ponytail: width moved to the select above. Drag-resize still sets any
    // width, and widthOptions keeps an off-preset one selectable.
    ["pos_x", "pos_y", "height"].forEach(function (key) {
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
        sort_order: orderSelect.value,
        width: parseInt(widthSelect.value, 10),
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
      dsCall({ method: "dashboard_studio.api.catalogue.get_catalogue" }),
      dsCall({ method: "dashboard_studio.api.catalogue.get_field_catalogue" }),
    ]).then(function (responses) {
      self.state.catalogue = responses[0].message || { doctypes: [], relationships: [] };
      self.state.fieldCatalogue = responses[1].message || [];
      if (self.state.view === "data") self.paintCatalogue();
    }).catch(function () {
      if (self.state.view === "data") {
        self.canvasError("Could not load the catalogue.", self.renderCatalogue);
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
    dsCall({ method: "dashboard_studio.api.validation.list_comparisons" })
      .then(function (r) {
        self.state.comparisons = r.message || [];
        if (self.state.view === "validation") self.paintValidation();
      })
      .catch(function () {
        if (self.state.view === "validation") {
          self.canvasError("Could not load comparisons.", self.renderValidation);
        }
      });
  };

  // Entry point for run_validation. Without this the endpoint existed but there
  // was no way to start a comparison from the editor — only to read old ones.
  App.prototype.buildValidationRun = function () {
    var self = this;
    var wrap = el("div", "dss-sqlimport");
    var head = el("div", "dss-sqlimport-head");
    head.appendChild(el("div", "dss-kicker", "Reference result"));
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
      var note = el("div", "dss-loadfail");
      note.appendChild(el("p", "dss-hint dss-note",
        "No chart on this dashboard has a metric, so there is nothing to validate yet. " +
        "Select a card in the Builder and link a metric in the panel on the right."));
      var toBuilder = el("button", "dss-btn", "Go to the Builder");
      toBuilder.addEventListener("click", function () {
        self.state.view = "design";
        self.render();
      });
      note.appendChild(toBuilder);
      wrap.appendChild(note);
      return wrap;
    }

    var picker = el("select", "dss-input");
    picker.setAttribute("aria-label", "Chart to validate");
    charts.forEach(function (c) {
      // run_validation executes the chart's own metric, so it hits exactly the
      // refusals the Builder card checks for. Same helper, so the two cannot
      // disagree about which charts can be run.
      var blocked = core.chartBlockReason(c);
      var opt = el("option", null,
        (c.chart_title || c.name) + (blocked ? " — " + blocked.title.toLowerCase() : ""));
      opt.value = c.name;
      opt.disabled = !!blocked;
      if (blocked) opt.title = blocked.hint;
      picker.appendChild(opt);
    });
    // A picker whose first option is disabled selects nothing; land on the first
    // chart that can actually be validated.
    var runnable = charts.filter(function (c) { return !core.chartBlockReason(c); });
    if (runnable.length) picker.value = runnable[0].name;
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
      var picked = (self.state.charts || []).filter(function (c) {
        return c.name === picker.value;
      })[0];
      // No selectable chart at all: every option was disabled, so the browser
      // reports an empty value. Without this the guard below fell straight
      // through on `picked === undefined` and called the server anyway.
      if (!picked) {
        note.textContent = "No chart on this dashboard can be validated yet — " +
          "each one's metric is unapproved, missing, or not a Count metric.";
        return;
      }
      var blocked = core.chartBlockReason(picked);
      if (blocked) {
        // Refuse here rather than letting the server raise: the engine's refusal
        // is a bare exception, so it reaches the browser as Frappe's traceback
        // dialog rather than as this note.
        note.textContent = blocked.title + ". " + blocked.hint;
        return;
      }
      note.textContent = "Comparing…";
      dsCall({
        method: "dashboard_studio.api.validation.run_validation",
        args: { chart: picker.value, source_rows: JSON.stringify(parsed.rows) },
      }).then(function (r) {
        var result = r.message || {};
        toast("Validation recorded: " + result.status);
        self.state.comparisons = null; // refetched by renderValidation
        self.refreshReadiness();       // a pass can clear the validation blocker
        self.render();
      }).catch(function (err) {
        note.textContent = refusalMessage(err, "Could not run that validation.");
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
        (self.state.expandedComparison === row.name ? "▾ " : "▸ ") +
        (row.chart_title || row.chart || "—"));
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
    dsCall({
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
    dsCall({
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
    if (!hasFrappe() || this.state.mock) {
      this.state.governance = (root.DSStudioMock || {}).MOCK_GOVERNANCE || null;
      this.paintGovernance();
      return;
    }
    // Same fault as the Migration canvas: a live session with no dashboard open
    // was served MOCK_GOVERNANCE, which also made paintGovernance's "No
    // dashboard is open" branch unreachable on a real site.
    if (!this.currentDashboard()) {
      this.state.governance = null;
      this.paintGovernance();
      return;
    }
    this.canvas.appendChild(el("div", "dss-hint", "Loading governance…"));
    dsCall({
      method: "dashboard_studio.api.governance.get_governance",
      args: { dashboard: this.currentDashboard() },
    }).then(function (r) {
      self.state.governance = r.message || null;
      if (self.state.view === "governance") self.paintGovernance();
    }).catch(function () {
      if (self.state.view === "governance") {
        self.canvasError("Could not load governance.", self.renderGovernance);
      }
    });
  };

  App.prototype.paintGovernance = function () {
    var self = this;
    this.canvas.innerHTML = "";
    this.panel.innerHTML = "";
    var gov = this.state.governance;
    if (!gov) {
      var none = el("div", "dss-loadfail");
      none.appendChild(el("p", "dss-hint",
        "No dashboard is open, so there is no workflow to show."));
      var pick = el("button", "dss-btn", "Open a dashboard");
      pick.addEventListener("click", function () { self.togglePicker(true); });
      none.appendChild(pick);
      this.canvas.appendChild(none);
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

    // What stands between this dashboard and Published, ABOVE the buttons rather
    // than after pressing one. The chip promises this list, so this is where the
    // promise is kept; both read the same publish_readiness payload.
    var readiness = this.state.readiness;
    if (readiness && (readiness.blockers || []).length) {
      var blocked = el("div", "dss-gov-blockers");
      blocked.appendChild(el("div", "dss-gov-blockers-head",
        "Not ready to publish — " + readiness.blockers.length +
        (readiness.blockers.length === 1 ? " thing to resolve" : " things to resolve")));
      readiness.blockers.forEach(function (b) {
        var item = el("div", "dss-gov-blocker");
        item.appendChild(el("div", "dss-gov-blocker-what", b.summary));
        // The named records, not just the count — "not ready" without the list
        // is the dead end this whole change is about.
        if ((b.charts || []).length) {
          item.appendChild(el("div", "dss-gov-blocker-who", b.charts.join(", ")));
        }
        blocked.appendChild(item);
      });
      band.appendChild(blocked);
    } else if (readiness) {
      band.appendChild(el("div", "dss-gov-ready", "Nothing is blocking publication."));
    }

    var actions = el("div", "dss-gov-actions");
    (gov.transitions || []).forEach(function (move) {
      var btn = el("button", "dss-btn dss-btn-transition" +
        (move.allowed ? " is-allowed" : ""), move.label);
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
    this.canvas.appendChild(this.buildExportBand());

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
    if (!hasFrappe() || this.state.mock || !this.currentDashboard()) {
      this.state.governance.status = move.to;
      this.paintGovernance();
      toast("Moved to " + move.to + " (mock — not persisted)");
      return;
    }
    dsCall({
      method: "dashboard_studio.api.governance.advance_status",
      args: { dashboard: this.currentDashboard(), to_status: move.to },
    }).then(function (r) {
      self.state.governance = null; // re-read, so the next legal moves come from the server
      if (self.state.dashboard) self.state.dashboard.status = (r.message || {}).status;
      self.renderGovernance();
      self.refreshReadiness();
      toast((r.message || {}).applied || "Updated");
    }).catch(function (err) {
      // The server names every offending chart. Replacing that with five words
      // is how the publish rules became invisible until they refused.
      toast(refusalMessage(err, "That move was refused."));
    });
  };

  // ---- Mapping view: source tables -> DocTypes, persisted shapes mocked ----

  App.prototype.renderMapping = function () {
    if (this.state.mapNodes) {
      this.refreshMapping();
      return;
    }
    var self = this;
    // A chosen demo session is the ONLY place invented nodes are allowed. Every
    // other branch below shows what is really there, including nothing.
    if (this.state.mock) {
      this.state.mapNodes = this.mockNodes();
      this.refreshMapping();
      return;
    }
    if (this.options.project && hasFrappe()) {
      this.canvas.innerHTML = '<div class="dss-nochart">Loading mapping project…</div>';
      dsCall({
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
        // An empty project is empty. Substituting demo nodes here is what put
        // "(MOCK)" next to a target DocType on a real site.
        self.state.mapNodes = core.nodesFromProject(data.canvas_nodes, self.state.mappings);
        // Keep the loaded state either way, but only repaint if the user is
        // still on the Mapping view — otherwise this wipes the Design canvas.
        if (self.state.view === "mapping") self.refreshMapping();
      }).catch(function () {
        // Same rule as the Builder landing: a failed call says so and offers a
        // retry. Falling back to demo data made a broken call look like a
        // working migration.
        if (self.state.view === "mapping") {
          self.canvasError("Could not load that mapping project.", self.renderMapping);
          self.renderMappingPanel();
        }
      });
      return;
    }
    // No ?project= is not a failure — the SQL box above still works, and
    // analysis is read-only. The panel offers a project to pick or create, so
    // nobody has to leave for /app/ds-migration-project and hand-build a URL.
    this.state.mapNodes = [];
    this.loadProjectOptions();
    this.refreshMapping();
  };

  // ⚠️ MOCK node set. Reachable ONLY from a deliberately chosen demo session,
  // where the sample-data banner is already up.
  App.prototype.mockNodes = function () {
    var mock = root.DSStudioMock || {};
    return core.analysisToNodes(mock.MOCK_ANALYSIS, mock.MOCK_TARGET_DOCTYPES);
  };

  // Is this node part of a Confirmed mapping? Confirmed work never dims and is
  // never cleared — it is the only thing here someone deliberately agreed to.
  App.prototype.isConfirmedNode = function (node) {
    return (this.state.mappings || []).some(function (m) {
      return m.mapping_status === "Confirmed" &&
        ("src:" + m.external_table === node.node_id || "tgt:" + m.target_doctype === node.node_id);
    });
  };

  App.prototype._node = function (nodeId) {
    return (this.state.mapNodes || []).filter(function (n) { return n.node_id === nodeId; })[0];
  };

  App.prototype.renderMapNode = function (node) {
    var self = this;
    var isSource = node.node_type === "Source Table";
    var fromLastQuery = (this.state.lastQueryTables || []).indexOf(node.label) !== -1;
    // Left over from an earlier query and never confirmed. Dimmed rather than
    // removed: it may still be work in progress, but it should not compete with
    // what was just analyzed.
    var stale = !fromLastQuery && (this.state.lastQueryTables || []).length &&
      !this.isConfirmedNode(node);
    var div = el("div", "dss-node " + (isSource ? "dss-node-src" : "dss-node-tgt") +
      (this.state.pickedSource === node.node_id ? " is-picked" : "") +
      (fromLastQuery ? " is-fresh" : "") + (stale ? " is-stale" : ""));
    if (fromLastQuery) div.title = "Named by the query you just analyzed";
    else if (stale) div.title = "From an earlier query, not confirmed";
    div.style.left = node.pos_x + "px";
    div.style.top = node.pos_y + "px";
    div.appendChild(el("div", "dss-node-kind", node.node_type));
    div.appendChild(el("div", "dss-node-label", node.label));
    // What the query actually measured. Without it, "grouped by nationality" and
    // "grouped by agent" on the same table drew identical cards.
    if (node.measure) div.appendChild(el("div", "dss-node-measure", node.measure));

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
        // Clicking a node is now a way INTO its mapping, not only a way to draw
        // one: its row is highlighted, scrolled to, and its target field focused,
        // so the correction can be made from the canvas.
        if (self.state.pickedSource) self._focusRow = node.label;
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
    //
    // The drag moves THIS element and rebuilds the canvas once, on mouseup.
    // It used to call refreshMapping() on every mousemove, which replaced every
    // node div mid-gesture — so mouseup landed on a different element than
    // mousedown and the browser fired no click at all. A Playwright click moves
    // zero pixels and never triggered it; a human trackpad moves several, so
    // clicking a node did nothing on the real site while the test passed.
    div.addEventListener("mousedown", function (e) {
      var startX = e.clientX, startY = e.clientY;
      var baseX = node.pos_x, baseY = node.pos_y;
      dragged = false;
      function onMove(ev) {
        var dx = ev.clientX - startX, dy = ev.clientY - startY;
        // Euclidean, and at a human threshold. The old rule was |dx|+|dy| > 3,
        // which a trackpad click clears without anyone meaning to drag — so a
        // normal click was classified as a drag and the node did nothing.
        // Playwright's click() moves zero pixels, which is why the test passed.
        if (!dragged && Math.sqrt(dx * dx + dy * dy) <= DRAG_THRESHOLD_PX) return;
        dragged = true; // consumed by the click handler above
        node.pos_x = Math.max(0, baseX + dx);
        node.pos_y = Math.max(0, baseY + dy);
        div.style.left = node.pos_x + "px";
        div.style.top = node.pos_y + "px";
      }
      function onUp() {
        root.removeEventListener("mousemove", onMove);
        root.removeEventListener("mouseup", onUp);
        // ponytail: connector lines redraw here rather than per frame. They lag
        // the node during a drag; wire them per-move if that ever grates.
        if (dragged) self.refreshMapping();
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
    if (!this.state.mapNodes.length) {
      this.canvas.appendChild(el("div", "dss-nochart",
        this.options.project
          ? "This mapping project has nothing mapped yet."
          : "Opened without a mapping project, so there is nothing to load." +
            " Paste a query above to analyze it; mappings can only be saved from a project."));
    }
    this.state.mapNodes.forEach(function (n) { self.renderMapNode(n); });
    this.renderMappingPanel();

    // After the panel exists, not before — the row was only just created.
    var focus = this._focusRow;
    this._focusRow = null;
    if (focus) {
      var row = this.panel.querySelector('[data-table="' + focus.replace(/"/g, '\\"') + '"]');
      if (row) {
        row.scrollIntoView({ block: "nearest" });
        var input = row.querySelector(".dss-map-target");
        if (input) input.focus();
      }
    }
  };

  App.prototype.renderMappingPanel = function () {
    var self = this;
    this.panel.innerHTML = "";
    this.panel.appendChild(el("h3", "dss-panel-title", "Mappings"));
    this.panel.appendChild(el("p", "dss-hint",
      this.state.pickedSource
        ? "Now click a Target DocType to map it."
        : "Click a Source Table, then a Target DocType, to draw a mapping. Edit a target below to point it somewhere else, or click its status to cycle it."));

    // Show what the parser concluded about the last analyzed query — especially
    // when it declined to translate it, which must never be silent.
    var analysis = this.state.lastAnalysis;
    var added = this.state.lastAdded || { nodes: 0, mappings: 0 };
    // What the LAST query did, in its own terms. Without this the list is
    // cumulative with nothing marking which query produced what, so a query that
    // added nothing new is indistinguishable from one that was ignored.
    function whatChanged() {
      if (added.mappings) {
        return " Added " + added.mappings + " mapping(s)" +
          (added.nodes ? " and " + added.nodes + " node(s)" : "") + " below.";
      }
      if (added.nodes) return " Added " + added.nodes + " node(s) to the canvas.";
      return " Everything it names was already on the canvas — nothing new to add.";
    }
    if (analysis) {
      if (analysis.supported) {
        this.panel.appendChild(el("div", "dss-analysis is-ok",
          "Last query: " + (analysis.doctypes || []).length + " table(s) found" +
          ((analysis.group_by || []).length ? ", grouped by " + analysis.group_by.join(", ") : "") +
          "." + whatChanged() + " Mappings stay Suggested until you confirm them."));
      } else {
        this.panel.appendChild(el("div", "dss-analysis is-warn",
          "Last query was not translated — " + (analysis.reasons || []).join("; ") +
          "." + whatChanged() +
          " Its tables are on the canvas unmapped; draw the mapping by hand if it is right."));
      }
    }

    if (!core.mappingRows(this.state.mapNodes, this.state.mappings).length) {
      this.panel.appendChild(el("p", "dss-hint", "No source tables yet — analyze a query above."));
    }
    // Suggestions for the target picker, shared by every row.
    var suggestions = core.targetSuggestions(this.state.mapNodes, this._metricList);
    var listId = "dss-doctype-options";
    var datalist = el("datalist");
    datalist.id = listId;
    suggestions.forEach(function (dt) {
      var opt = el("option");
      opt.value = dt;
      datalist.appendChild(opt);
    });
    this.panel.appendChild(datalist);

    // Derived from the canvas so the two can never disagree: a table the parser
    // found but could not map still gets a row, with an empty target to fill in.
    var rows = core.mappingRows(this.state.mapNodes, this.state.mappings);
    rows.forEach(function (m) {
      var row = el("div", "dss-map-row is-" + m.mapping_status.toLowerCase());
      row.setAttribute("data-table", m.external_table);
      if ((self.state.lastQueryTables || []).indexOf(m.external_table) !== -1) {
        row.className += " is-fresh";
        row.title = "Named by the query you just analyzed";
      }
      if (self.state.pickedSource === "src:" + m.external_table) row.className += " is-picked";
      row.appendChild(el("span", "dss-map-src", m.external_table));

      // The correction path. An <input list> rather than a select: there is no
      // endpoint that enumerates every DocType on the site, so a closed list
      // would lock someone out of the right answer. target_doctype is a Link, so
      // Frappe refuses a name that does not exist — the client suggests, the
      // server validates.
      var target = el("input", "dss-input dss-map-target");
      target.setAttribute("list", listId);
      target.setAttribute("aria-label", "Target DocType for " + m.external_table);
      target.placeholder = "Target DocType…";
      // The full value must be readable, not clipped to its first word: the
      // panel is 240px and the input was 64px, which is why picking a target
      // felt like nothing was happening.
      target.title = m.target_doctype || "";
      target.value = m.target_doctype || "";
      target.addEventListener("change", function () {
        var next = target.value.trim();
        if (!next || next === m.target_doctype) { target.value = m.target_doctype || ""; return; }
        m.target_doctype = next;
        // Retargeting is an edit, not a confirmation — back to Suggested so the
        // status still means "a person agreed to THIS pair".
        m.mapping_status = "Suggested";
        // A row derived from a bare canvas node is not in state.mappings yet;
        // giving it a target is what makes it one.
        if (self.state.mappings.indexOf(m) === -1) self.state.mappings.push(m);
        self.state.mapNodes = core.mergeNodes(self.state.mapNodes,
          [{ node_id: "tgt:" + next, node_type: "Target DocType", label: next, pos_x: 340 }]);
        self.refreshMapping();
      });
      row.appendChild(target);

      var status = el("button", "dss-map-status", m.mapping_status);
      status.type = "button";
      status.disabled = !m.target_doctype;
      status.title = m.target_doctype
        ? "Cycle Suggested → Confirmed → Rejected"
        : "Set a target DocType before confirming this table";
      status.addEventListener("click", function () {
        if (!m.target_doctype) return;
        m.mapping_status = core.nextMappingStatus(m.mapping_status);
        self.refreshMapping();
      });
      row.appendChild(status);
      self.panel.appendChild(row);
    });

    if (!this.options.project && !this.state.mock && hasFrappe()) {
      this.loadProjectOptions();
      this.panel.appendChild(this.buildProjectPicker());
    }

    var actions = el("div", "dss-map-actions");
    var save = el("button", "dss-btn dss-btn-primary", "Save mappings");
    save.addEventListener("click", function () { self.saveMappings(); });
    actions.appendChild(save);

    this.panel.appendChild(actions);

    // What the last save did. A save that writes nothing must say so here, not
    // only in a toast that has already gone.
    var saveResult = this.state.saveResult;
    if (saveResult) {
      var box = el("div", "dss-saveresult" + (saveResult.ok ? " is-ok" : " is-warn"));
      box.appendChild(el("div", "dss-saveresult-title", saveResult.title));
      box.appendChild(el("div", "dss-saveresult-detail", saveResult.detail));
      this.panel.appendChild(box);
    }

    // What the save generated. Every analyzed query is reported — created,
    // reused, or skipped with the reason — because a silent skip is a metric
    // someone thinks they have.
    var generated = this.state.generatedMetrics;
    if (generated && generated.length) {
      this.panel.appendChild(el("div", "dss-kicker", "Metrics from these queries"));
      generated.forEach(function (row) {
        var item = el("div", "dss-genmetric" + (row.metric ? "" : " is-skipped"));
        item.appendChild(el("div", "dss-genmetric-name",
          row.metric || "No metric generated"));
        item.appendChild(el("div", "dss-genmetric-note", row.metric
          ? (row.created ? "Created as Draft — approve it before a chart can use it."
                         : "Already existed; reused rather than duplicated.")
          : row.skipped));

        // The handoff to the Builder. Preview answers "are these numbers sane?"
        // before approval; Create chart makes the DS Chart and switches views.
        // Neither belongs in Source Mapping beyond this point — the Builder owns
        // charts, and this workspace owns the query that produced the metric.
        if (row.metric) {
          var acts = el("div", "dss-genmetric-actions");
          var preview = el("button", "dss-btn dss-btn-small", "Preview numbers");
          preview.title = "Run this metric now, even though it is not approved yet";
          preview.addEventListener("click", function () { self.previewMetric(row.metric); });
          acts.appendChild(preview);

          var where = el("select", "dss-input dss-genmetric-where");
          where.setAttribute("aria-label", "Dashboard to create the chart on");
          // `self`, not `this` — this runs inside a forEach callback.
          (self.state.dashboards || []).forEach(function (d) {
            var o = el("option", null, core.dashboardTitle(d));
            o.value = d.name;
            if (d.name === self.currentDashboard()) o.selected = true;
            where.appendChild(o);
          });
          var make = el("button", "dss-btn dss-btn-small", "Create chart");
          make.disabled = !(self.state.dashboards || []).length;
          make.addEventListener("click", function () {
            self.createChartFromMetric(row.metric, where.value);
          });
          acts.appendChild(where);
          acts.appendChild(make);
          item.appendChild(acts);
        }
        var pv = self.state.metricPreview;
        if (pv && pv.metric === row.metric) item.appendChild(self.buildMetricPreview(pv));
        self.panel.appendChild(item);
      });
    }
  };

  // Paste Metabase SQL — the way a migration starts. The parser reports what it
  // found and suggests identity mappings, which the user then confirms or
  // rejects. Returned as an element so the caller can place it prominently
  // instead of tucking it under the mapping list.
  // ---------------------------------------------------------------- Visualize
  //
  // Its own workspace, deliberately: this was first shipped as one button bolted
  // onto Source Mapping, which hid the fact that it is a different job with a
  // different destination. Two steps, in order, and a visible line between what
  // Studio does and what Insights does.
  //
  // Its SQL box is NOT shared with Source Mapping. Two Analyze buttons acting on
  // one hidden box is the kind of coupling that reads as a bug the first time
  // someone hits it.
  App.prototype.buildVisualize = function () {
    var grid = el("div", "dss-steps");
    grid.appendChild(this.buildVizStepOne());
    grid.appendChild(this.buildVizStepTwo());
    return grid;
  };

  App.prototype.buildVizStepOne = function () {
    var self = this;
    var card = el("section", "dss-vizstep");
    var head = el("div", "dss-vizstep-head");
    head.appendChild(el("div", "dss-vizstep-eyebrow", "Step 1"));
    head.appendChild(el("h3", "dss-vizstep-title", "Paste the source query"));
    card.appendChild(head);
    var body = el("div", "dss-vizstep-body");

    var box = el("textarea", "dss-input dss-sqlbox");
    box.placeholder = "SELECT `agent`, COUNT(*) FROM `tabStudent Applicant` GROUP BY `agent`";
    box.setAttribute("aria-label", "Source SQL");
    box.value = this.state.vizSql || "";
    box.addEventListener("input", function () { self.state.vizSql = box.value; });
    body.appendChild(box);

    var note = el("div", "dss-sqlnote", this.state.vizAnalysis
      ? this.vizAnalysisNote()
      : "Not analyzed yet.");
    var run = el("button", "dss-btn dss-btn-primary", "Analyze SQL");
    run.addEventListener("click", function () {
      var sql = (box.value || "").trim();
      if (!sql) { note.textContent = "Paste a query first."; return; }
      if (!hasFrappe()) {
        note.textContent = "Analysis needs the server (not available in sample mode).";
        return;
      }
      note.textContent = "Analyzing…";
      dsCall({
        method: "dashboard_studio.api.migration.analyze_migration_sql",
        args: { sql: sql },
      }).then(function (r) {
        var analysis = (r.message || {}).analysis || {};
        self.state.vizAnalysis = analysis;
        // Re-guess from the new query. Anything the person had confirmed for a
        // DIFFERENT query is not a confirmation of this one.
        self.state.vizFields = core.insightsPrefill(analysis);
        self.state.vizConfirmed = {};
        self.state.insightsResult = null;
        self.render();
      }).catch(function (err) {
        note.textContent = refusalMessage(err, "Could not analyze that query.");
      });
    });

    var row = el("div", "dss-vizstep-actions");
    row.appendChild(run);
    row.appendChild(note);
    body.appendChild(row);
    card.appendChild(body);
    return card;
  };

  App.prototype.vizAnalysisNote = function () {
    var a = this.state.vizAnalysis || {};
    var tables = (a.doctypes || []).length;
    if (!a.supported) {
      // Not a failure for this flow: Insights runs the SQL as written, so a
      // query the DS parser will not translate can still be handed over. Only
      // the guesses below get weaker.
      return "Analyzed, but not translated — Insights will still run it as written. " +
        "Check the fields on the right.";
    }
    return "Analyzed: " + tables + " table(s), grouped by " +
      ((a.group_by || []).join(", ") || "nothing") + ".";
  };

  // Step 2 — the only thing Studio contributes. Kept to four controls on
  // purpose: everything else (colour, reference line, curve, area) is Insights'
  // job and rebuilding it here is what this workspace exists to avoid.
  App.prototype.buildVizStepTwo = function () {
    var self = this;
    var ready = !!this.state.vizAnalysis;
    var card = el("section", "dss-vizstep" + (ready ? "" : " is-waiting"));
    var head = el("div", "dss-vizstep-head");
    head.appendChild(el("div", "dss-vizstep-eyebrow", "Step 2 — Studio's job, and only this"));
    head.appendChild(el("h3", "dss-vizstep-title", "Fill what SQL can't say"));
    card.appendChild(head);
    var body = el("div", "dss-vizstep-body");

    if (!ready) {
      body.appendChild(el("p", "dss-hint", "Analyze a query first."));
      card.appendChild(body);
      return card;
    }

    var fields = this.state.vizFields || {};
    var confirmed = this.state.vizConfirmed || (this.state.vizConfirmed = {});

    // Only the title travels with the record. Saying so here is the difference
    // between a handoff and a form that quietly drops three of its four fields.
    body.appendChild(this.vizField("title", "Chart title", fields.title,
      "Stored on the Insights query.", true));
    // Each axis carries its own "nothing to guess from" sentence. A join with no
    // outer GROUP BY has neither a dimension nor an aggregate to read, and the
    // fields used to render as an empty box under a "Guessed" tag.
    body.appendChild(this.vizField("x_axis", "X Axis field", fields.x_axis,
      "From the GROUP BY column.", false,
      "No GROUP BY in this query — set the X axis in Insights."));
    body.appendChild(this.vizField("y_axis", "Y Axis field", fields.y_axis,
      "From the aggregate column.", false,
      "No aggregate column in this query — set the Y axis in Insights."));

    // Chart type
    var typeWrap = el("div", "dss-field");
    var typeRow = el("div", "dss-guessrow");
    typeRow.appendChild(el("label", "dss-field-label", "Suggested chart type"));
    var typeTag = el("span", "dss-guesstag " + (confirmed.chart_type ? "is-confirmed" : "is-guessed"),
      confirmed.chart_type ? "Confirmed" : "Guessed");
    typeRow.appendChild(typeTag);
    typeWrap.appendChild(typeRow);
    var typeGrid = el("div", "dss-typegrid");
    core.INSIGHTS_CHART_TYPES.forEach(function (option) {
      var opt = el("button", "dss-typeopt" +
        (fields.chart_type === option.value ? " is-active" : ""), option.label);
      opt.type = "button";
      opt.addEventListener("click", function () {
        fields.chart_type = option.value;
        confirmed.chart_type = true;
        self.render();
      });
      typeGrid.appendChild(opt);
    });
    typeWrap.appendChild(typeGrid);
    typeWrap.appendChild(el("p", "dss-hint",
      "Applied by “Set the axes in Insights” after the query has been run there."));
    body.appendChild(typeWrap);

    this._vizPreview = this.vizPreview(fields);
    body.appendChild(this._vizPreview);

    // Where this goes, before the button rather than after it.
    var dest = el("div", "dss-destination");
    dest.appendChild(el("span", "dss-destination-dot"));
    dest.appendChild(el("span", null,
      "Creates an Insights query holding this SQL. Insights makes the chart " +
      "itself; Studio can set its axes once you have run the query there."));
    body.appendChild(dest);

    var go = el("button", "dss-btn dss-btn-primary", "Create in Insights →");
    go.addEventListener("click", function () { self.createInsightsQuery(); });
    body.appendChild(go);

    // Its own class, not a second .dss-sqlnote: Step 1 already has one, and a
    // refusal landing in "the other element with the same class" is unreadable
    // to anyone debugging it later.
    if (this.state.vizError) {
      body.appendChild(el("div", "dss-sqlnote dss-vizerror", this.state.vizError));
    }

    var result = this.buildInsightsResult();
    if (result) body.appendChild(result);

    card.appendChild(body);
    return card;
  };

  // One editable field with its Guessed/Confirmed marker.
  //
  // The marker is flipped IN PLACE on input rather than by re-rendering: a
  // re-render on every keystroke replaces the input mid-type and the caret and
  // the rest of the word go with it. That fault has already been fixed twice in
  // this app; do not reintroduce it here.
  App.prototype.vizField = function (key, label, value, hint, sent, missingHint) {
    var self = this;
    var wrap = el("div", "dss-field");
    var row = el("div", "dss-guessrow");
    row.appendChild(el("label", "dss-field-label", label));
    var confirmed = (this.state.vizConfirmed || {})[key];
    var state = core.axisState(value, confirmed);
    var TAGS = { confirmed: "Confirmed", guessed: "Guessed", missing: "Not detected" };
    var tag = el("span", "dss-guesstag is-" + state, TAGS[state]);
    row.appendChild(tag);
    if (sent) row.appendChild(el("span", "dss-senttag", "sent"));
    wrap.appendChild(row);

    var input = el("input", "dss-input");
    input.type = "text";
    input.value = value || "";
    // The native placeholder, not a disabled box: nothing was detected, but the
    // person can still type what they know.
    if (state === "missing" && missingHint) input.placeholder = missingHint;
    input.setAttribute("aria-label", label);
    input.addEventListener("input", function () {
      self.state.vizFields[key] = input.value;
      var now = core.axisState(input.value, true);
      self.state.vizConfirmed[key] = now !== "missing";
      // Flipped in place, never by re-rendering: a re-render per keystroke
      // replaces the input mid-type and takes the caret with it.
      tag.textContent = TAGS[now];
      tag.className = "dss-guesstag is-" + now;
    });
    // The preview reads these values at build time, so it goes stale the moment
    // anything is typed — the axes line kept saying "not detected" after an axis
    // had been filled in. Repaint on `change` (blur), when the caret is already
    // gone, so this cannot eat characters mid-type.
    //
    // Repaints ONLY the preview, never the whole step. A full render() here
    // rebuilt the DOM during blur, so clicking Create in Insights straight from
    // a focused field destroyed the button between mousedown and mouseup and the
    // click never fired — the same suppression already fixed on the map canvas.
    input.addEventListener("change", function () { self.repaintVizPreview(); });
    wrap.appendChild(input);
    var shown = state === "missing" && missingHint ? missingHint : hint;
    if (shown) {
      wrap.appendChild(el("p", "dss-hint" + (state === "missing" ? " dss-hint-missing" : ""),
        shown));
    }
    return wrap;
  };

  // A shape, NOT data. Studio never runs the query, so there are no numbers to
  // draw and inventing some would be the mock-data-on-a-real-site fault this
  // app has already shipped once. Bars carry no values and the caption says why.
  App.prototype.vizPreview = function (fields) {
    var card = el("div", "dss-vizpreview");
    card.appendChild(el("div", "dss-vizpreview-title", fields.title || "Untitled"));
    card.appendChild(el("div", "dss-vizpreview-sub",
      "Shape only — Studio does not run the query. The real numbers appear in Insights."));
    var area = el("div", "dss-vizpreview-area is-" + (fields.chart_type || "bar"));
    if (fields.chart_type === "number") {
      area.appendChild(el("div", "dss-vizpreview-kpi", "—"));
    } else if (fields.chart_type === "donut") {
      area.appendChild(el("div", "dss-vizpreview-donut"));
    } else if (fields.chart_type === "table") {
      [0, 1, 2, 3].forEach(function () { area.appendChild(el("div", "dss-vizpreview-row")); });
    } else {
      [58, 84, 40, 70, 30].forEach(function (h) {
        var bar = el("div", "dss-vizpreview-bar");
        bar.style.height = h + "%";
        area.appendChild(bar);
      });
    }
    card.appendChild(area);
    // "x: — y: —" said nothing twice. When neither axis was detected, say what
    // that means instead; when one was, show the one there is.
    var haveX = core.axisState(fields.x_axis) !== "missing";
    var haveY = core.axisState(fields.y_axis) !== "missing";
    var axes = el("div", "dss-vizpreview-axes");
    if (!haveX && !haveY) {
      axes.classList.add("is-missing");
      axes.appendChild(el("span", null, "Axes not detected — set them in Insights."));
    } else {
      if (haveX) axes.appendChild(el("span", null, "x: " + fields.x_axis));
      if (haveY) axes.appendChild(el("span", null, "y: " + fields.y_axis));
    }
    card.appendChild(axes);
    return card;
  };

  App.prototype.repaintVizPreview = function () {
    var current = this._vizPreview;
    if (!current || !current.parentNode) return;
    var fresh = this.vizPreview(this.state.vizFields || {});
    current.parentNode.replaceChild(fresh, current);
    this._vizPreview = fresh;
  };

  App.prototype.createInsightsQuery = function () {
    var self = this;
    var sql = (this.state.vizSql || "").trim();
    var fields = this.state.vizFields || {};
    if (!sql) { this.state.vizError = "Paste a query first."; this.render(); return; }
    if (!hasFrappe()) {
      this.state.vizError = "Creating an Insights query needs the server (not available in sample mode).";
      this.render();
      return;
    }
    this.state.vizError = "Creating in Insights…";
    this.render();
    dsCall({
      method: "dashboard_studio.api.insights.create_insights_query",
      args: {
        sql: sql,
        title: fields.title || null,
        analysis: JSON.stringify(this.state.vizAnalysis || null),
      },
    }).then(function (r) {
      var made = r.message;
      if (!made || !made.name) {
        self.state.vizError = "The server reported no Insights query. Nothing was created.";
        self.render();
        return;
      }
      // Carry the axes across, so the handoff note survives the round trip.
      made.x_axis = fields.x_axis;
      made.y_axis = fields.y_axis;
      made.chart_type = fields.chart_type;
      self.state.insightsResult = made;
      self.state.vizError = "";
      self.render();
    }).catch(function (err) {
      self.state.insightsResult = null;
      self.state.vizError = refusalMessage(err, "Could not create that Insights query.");
      self.render();
    });
  };

  // The outcome of the last Insights handoff. Persistent, like the save result:
  // a toast that has already faded is not an answer to "did that work?".
  //
  // TWO links on purpose. The Desk one is derived from Frappe and is correct on
  // any install; the Insights one depends on where that install mounts its SPA,
  // which is the single thing about this handoff that could not be confirmed
  // from source. If the first link 404s the second still opens the record.
  App.prototype.buildInsightsResult = function () {
    // `self`, declared. Without it the click handler below resolved `self` to
    // window.self — a real object, so no ReferenceError, just a silent
    // "not a function" on click. Same slip this file has had before.
    var self = this;
    var made = this.state.insightsResult;
    if (!made) return null;
    var box = el("div", "dss-saveresult is-ok");
    box.appendChild(el("div", "dss-saveresult-title",
      made.reused
        ? "Already in Insights — " + made.name
        : "Created in Insights — " + made.name));
    box.appendChild(el("div", "dss-saveresult-detail",
      "“" + made.title + "”, a native query against " + made.data_source + ". " +
      (made.applied
        ? "The axes below were read from the columns the query actually returned."
        : made.reused
          ? "The same SQL was already there, so nothing new was created."
          : "Run it in Insights, then set the axes from here.")));
    // What Studio guessed. Still shown, because until the query has been RUN in
    // Insights there is nothing to apply automatically — the real column labels
    // and their types only exist after execution.
    if (made.x_axis || made.y_axis || made.chart_type) {
      var todo = el("div", "dss-handoff-todo");
      todo.appendChild(el("div", "dss-handoff-todo-head",
        made.applied ? "Set in Insights" : "Set these in Insights"));
      [["X Axis", made.x_axis], ["Y Axis", made.y_axis], ["Chart type", made.chart_type]]
        .forEach(function (pair) {
          if (!pair[1]) return;
          var row = el("div", "dss-handoff-todo-row");
          row.appendChild(el("span", "dss-handoff-todo-key", pair[0]));
          row.appendChild(el("span", "dss-handoff-todo-val", String(pair[1])));
          todo.appendChild(row);
        });
      box.appendChild(todo);
    }

    var links = el("div", "dss-insights-links");
    [["Open in Insights", made.insights_url], ["Open the record", made.desk_url]]
      .forEach(function (pair) {
        var a = el("a", "dss-link", pair[0]);
        a.href = pair[1];
        a.target = "_blank";
        a.rel = "noopener";
        links.appendChild(a);
      });
    box.appendChild(links);

    // Try it without being asked. The person's next move after creating is to go
    // and run the query, so coming back is the moment to look — and the moment
    // the columns first exist.
    //
    // Once per query per visit: the flag is set BEFORE the call, so a render
    // triggered by the call's own result cannot start another one, and a refusal
    // is not retried on every repaint. Entering the tab clears it.
    //
    // This notices that execution HAS happened. It never causes it — no result
    // yet is a refusal telling the person to press Run, which is exactly the
    // right message to show straight after creation.
    this._autoApplyTried = this._autoApplyTried || {};
    if (!made.applied && !this._autoApplyTried[made.name] && hasFrappe()) {
      this._autoApplyTried[made.name] = true;
      this.applyInsightsChart({ auto: true });
    }

    // Kept as the fallback: right after creation the automatic attempt will have
    // refused (nothing has been run yet), and this is how someone retries
    // deliberately without leaving and returning.
    if (!made.applied) {
      var apply = el("button", "dss-btn", "Set the axes in Insights");
      apply.title = "Reads the columns the query actually returned and sets them " +
        "on the chart Insights made. Run the query in Insights first.";
      apply.addEventListener("click", function () { self.applyInsightsChart(); });
      box.appendChild(apply);
    }
    if (this.state.insightsApplyError) {
      box.appendChild(el("div", "dss-vizerror", this.state.insightsApplyError));
    } else if (this.state.insightsApplyHint) {
      // Same sentence the server gives, in a quieter voice, because nobody asked
      // for this attempt. "Open it in Insights, press Run, then come back" is
      // instruction rather than failure when it appears seconds after creating.
      box.appendChild(el("p", "dss-hint", this.state.insightsApplyHint));
    }
    return box;
  };

  App.prototype.applyInsightsChart = function (options) {
    var self = this;
    var auto = !!(options && options.auto);
    var made = this.state.insightsResult || {};
    var fields = this.state.vizFields || {};
    if (!made.name || !hasFrappe()) return;
    this.state.insightsApplyHint = "";
    // No "Reading…" flicker on an attempt nobody asked for, and no render here
    // either — this one is called FROM a render.
    if (!auto) {
      this.state.insightsApplyError = "Reading the query's columns…";
      this.render();
    }
    dsCall({
      method: "dashboard_studio.api.insights.apply_insights_chart",
      args: {
        query: made.name,
        chart_type: fields.chart_type || "bar",
        // Sent only when the person confirmed them. An unconfirmed guess came
        // from parsed SQL, and the server picks better from the real columns.
        x_axis: (this.state.vizConfirmed || {}).x_axis ? fields.x_axis : null,
        y_axis: (this.state.vizConfirmed || {}).y_axis ? fields.y_axis : null,
      },
    }).then(function (r) {
      var set = r.message;
      if (!set || !set.chart) {
        self.state.insightsApplyError = "The server reported no chart. Nothing was set.";
        self.render();
        return;
      }
      // Report what the SERVER set, not what was asked for — it reads the real
      // columns and may well have picked something else.
      self.state.insightsResult = Object.assign({}, made, {
        applied: true, chart: set.chart, chart_type: set.chart_type,
        x_axis: set.x_axis, y_axis: set.y_axis,
      });
      self.state.insightsApplyError = "";
      self.state.insightsApplyHint = "";
      self.render();
    }).catch(function (err) {
      var message = refusalMessage(err, "Could not set the axes on that chart.");
      self.state.insightsApplyError = auto ? "" : message;
      self.state.insightsApplyHint = auto ? message : "";
      self.render();
    });
  };

  App.prototype.buildSqlImport = function () {
    var self = this;
    var wrap = el("div", "dss-sqlimport");

    var head = el("div", "dss-sqlimport-head");
    head.appendChild(el("div", "dss-kicker", "Import"));
    head.appendChild(el("h3", "dss-sqlimport-title", "Paste the Metabase SQL"));
    wrap.appendChild(head);

    var box = el("textarea", "dss-input");
    box.placeholder = "SELECT COUNT(*) FROM `tabStudent Applicant` WHERE …";
    box.setAttribute("aria-label", "Metabase SQL");
    box.value = this.state.sqlText || "";
    box.addEventListener("input", function () { self.state.sqlText = box.value; });
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
      // Start fresh. Same rule as the Clear canvas button — confirmed mappings
      // survive, untouched Suggested/Unmapped leftovers do not — but silent, and
      // WITHOUT dropping the analyzed-query evidence, which belongs to the save
      // rather than to the canvas.
      var swept = core.clearedCanvas(self.state.mapNodes, self.state.mappings);
      self.state.mapNodes = swept.nodes;
      self.state.mappings = swept.mappings;
      self.state.pickedSource = null;

      note.textContent = "Analyzing…";
      dsCall({
        method: "dashboard_studio.api.migration.analyze_migration_sql",
        args: { sql: sql },
      }).then(function (r) {
        var data = r.message || {};
        var analysis = data.analysis || {};
        self.applyAnalysis(analysis, data.suggested_mappings || [], sql);
        // The "Analyzing…" state had no success path — only .catch wrote to the
        // note — so a query that parsed perfectly looked exactly like a hang.
        // The full report is in the panel; this says which one to read.
        // The box stays visible and editable at all times — do NOT reintroduce
        // a collapse here. Standing instruction, 2026-07-25.
        var found = (analysis.doctypes || []).length;
        note.textContent = analysis.supported
          ? "Analyzed: " + found + " table(s) found, " +
            (data.suggested_mappings || []).length + " mapping(s) suggested — see the panel."
          : "Analyzed, but not translated — see the reasons in the panel.";
      }).catch(function (err) {
        note.textContent = refusalMessage(err, "Could not analyze that query.");
      });
    });
    // Clear canvas sits directly under Analyze SQL: they are the two things you
    // do to the canvas, and it was in the far panel.
    var clear = el("button", "dss-btn", "Clear canvas");
    clear.title = "Remove every table and mapping except the ones you confirmed";
    clear.disabled = !(this.state.mapNodes || []).length;
    clear.addEventListener("click", function () { self.clearCanvas(); });

    // No "Create in Insights" here. It lives in its own Visualize workspace: a
    // handoff to a different app, with its own two-step flow, is not a fourth
    // button under the mapping canvas.
    var actions = el("div", "dss-sqlimport-actions");
    actions.appendChild(analyze);
    actions.appendChild(clear);
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
    var before = this.state.mapNodes.length;
    this.state.mapNodes = core.mergeNodes(this.state.mapNodes, discovered);
    this.state.mappings = core.mergeMappings(this.state.mappings, suggestions);
    // What this analysis actually changed. Re-analysing a query whose tables and
    // mappings are already on the canvas is a legitimate no-op, and the panel
    // has to say so rather than looking like it ignored the query.
    this.state.lastAdded = {
      nodes: this.state.mapNodes.length - before,
      mappings: this.state.mappings.added || 0,
    };
    // Which tables THIS query named. Marked on the canvas and in the panel until
    // the next analysis replaces it, so a re-analysis that adds nothing still
    // shows what was just run. Persistent rather than a flash: a highlight you
    // blinked past is the same as no highlight, and it needs no timer.
    this.state.lastQueryTables = (analysis.doctypes || []).map(function (d) { return "tab" + d; });
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

  App.prototype.buildMetricPreview = function (pv) {
    var box = el("div", "dss-preview");
    if (pv.loading) { box.appendChild(el("div", "dss-hint", "Running…")); return box; }
    if (pv.error) {
      box.className += " is-error";
      box.appendChild(el("div", "dss-hint", pv.error));
      return box;
    }
    var rows = pv.rows || [];
    box.appendChild(el("div", "dss-preview-head",
      rows.length + " group(s) · " + (pv.status || "?") + " · " + (pv.source_doctype || "")));
    if (!rows.length) {
      box.appendChild(el("div", "dss-hint", "No rows. Worth knowing BEFORE approving it."));
      return box;
    }
    // ponytail: the first 8 groups. This is a sanity check, not a chart — the
    // chart is what Create chart makes.
    var table = el("table", "dss-preview-table");
    rows.slice(0, 8).forEach(function (r) {
      var keys = Object.keys(r);
      var valueKey = keys.indexOf("count") !== -1 ? "count" : keys[keys.length - 1];
      var dimKey = keys.filter(function (k) { return k !== valueKey; })[0];
      var tr = el("tr");
      tr.appendChild(el("td", null, r[dimKey] == null ? "(blank)" : String(r[dimKey])));
      tr.appendChild(el("td", "dss-num", String(r[valueKey])));
      table.appendChild(tr);
    });
    box.appendChild(table);
    if (rows.length > 8) {
      box.appendChild(el("div", "dss-hint", "…and " + (rows.length - 8) + " more."));
    }
    return box;
  };

  // Run an unapproved metric so approval is a decision, not a formality. Its own
  // endpoint, deliberately: list_ds_metrics stays Approved-only everywhere a
  // chart is built for real.
  App.prototype.previewMetric = function (metricName) {
    var self = this;
    if (!hasFrappe()) { toast("Previewing a metric needs the server."); return; }
    this.state.metricPreview = { metric: metricName, loading: true };
    this.renderMappingPanel();
    dsCall({
      method: "dashboard_studio.api.metrics.preview_ds_metric",
      args: { metric_name: metricName },
    }).then(function (r) {
      self.state.metricPreview = Object.assign({ metric: metricName }, r.message || {});
      self.renderMappingPanel();
    }).catch(function (err) {
      self.state.metricPreview = {
        metric: metricName,
        error: refusalMessage(err, "Could not run that metric."),
      };
      self.renderMappingPanel();
    });
  };

  // Create the chart on a chosen dashboard, then hand over to the Builder — the
  // workspace that owns charts — with it open and selected.
  App.prototype.createChartFromMetric = function (metricName, dashboard) {
    var self = this;
    if (!hasFrappe() || !dashboard) { toast("Creating a chart needs a dashboard."); return; }
    dsCall({
      method: "dashboard_studio.api.studio.create_chart",
      args: { dashboard: dashboard, chart_type: "Bar Chart", metric: metricName },
    }).then(function (r) {
      var chart = r.message || {};
      toast("Created “" + (chart.chart_title || "chart") + "” — opening the Builder");
      self.state.view = "design";
      self.state.selected = chart.name;
      // openDashboard re-reads and re-renders; the Builder then owns it.
      self.openDashboard(dashboard);
    }).catch(function (err) {
      toast(refusalMessage(err, "Could not create that chart."));
    });
  };

  // Export for Sophia — option 2 of PUBLISH_TO_SOPHIA_DESIGN.md §3. It shows
  // JSON for a person to copy. There is deliberately nothing here that writes
  // anywhere: no "apply", no target, no automation.
  App.prototype.buildExportBand = function () {
    var self = this;
    var band = el("div", "dss-band");
    var head = el("div", "dss-band-head");
    head.appendChild(el("span", "dss-band-toggle", "Export for the platform"));
    band.appendChild(head);
    band.appendChild(el("p", "dss-hint",
      "Generates the publish artefact as JSON for someone to apply by hand. " +
      "It writes nothing, here or on the receiving platform."));

    var go = el("button", "dss-btn", "Generate export");
    go.addEventListener("click", function () { self.generateExport(); });
    band.appendChild(go);

    var result = this.state.exportResult;
    if (!result) return band;

    if (!result.ok) {
      var refused = el("div", "dss-gov-blockers");
      refused.appendChild(el("div", "dss-gov-blockers-head",
        "Not exported — " + result.refusals.length + " reason(s)"));
      result.refusals.forEach(function (r) {
        var item = el("div", "dss-gov-blocker");
        item.appendChild(el("div", "dss-gov-blocker-what", r.rule.replace(/_/g, " ")));
        item.appendChild(el("div", "dss-gov-blocker-who", r.message));
        refused.appendChild(item);
      });
      band.appendChild(refused);
      return band;
    }

    // textContent, not innerHTML: the artefact is data and must stay data even
    // on the way to the clipboard.
    var box = el("textarea", "dss-input dss-exportbox");
    box.value = result.json;
    box.readOnly = true;
    box.setAttribute("aria-label", "Publish artefact JSON");
    band.appendChild(box);

    var copy = el("button", "dss-btn dss-btn-primary", "Copy JSON");
    copy.addEventListener("click", function () {
      box.select();
      if (root.navigator && root.navigator.clipboard) {
        root.navigator.clipboard.writeText(result.json).then(function () {
          toast("Artefact copied. Applying it is a manual step.");
        }).catch(function () { toast("Select the text and copy it manually."); });
      } else {
        toast("Select the text and copy it manually.");
      }
    });
    band.appendChild(copy);

    (result.artefact.unresolved || []).forEach(function (line) {
      band.appendChild(el("div", "dss-gov-warn", line));
    });
    return band;
  };

  App.prototype.generateExport = function () {
    var self = this;
    dsCall({
      method: "dashboard_studio.api.sophia_export.export_dashboard",
      args: { dashboard: this.options.dashboard },
    }).then(function (r) {
      self.state.exportResult = r.message || { ok: false, refusals: [
        { rule: "no_response", message: "The server returned no artefact and no reason." }] };
      self.renderGovernance();
    }).catch(function (err) {
      toast(refusalMessage(err, "Could not generate the export."));
    });
  };

  App.prototype.loadProjectOptions = function () {
    var self = this;
    if (this.state.projectOptions || this._projectOptionsWarming || !hasFrappe()) return;
    this._projectOptionsWarming = true;
    dsCall({ method: "dashboard_studio.api.studio.list_migration_projects" })
      .then(function (r) {
        self.state.projectOptions = r.message || { projects: [], data_sources: [] };
        if (self.state.view === "mapping") self.renderMappingPanel();
      })
      .catch(function (err) {
        // A failed READ must not block the WRITE. Listing projects and creating
        // one are separate rights, and gating the create form behind the list
        // left anyone whose list call failed with no way forward at all — the
        // panel sat on "Loading projects…" with no form and no explanation.
        self._projectOptionsWarming = false;
        self.state.projectOptions = { projects: [], data_sources: [],
          failed: refusalMessage(err, "Could not list existing migration projects.") };
        if (self.state.view === "mapping") self.renderMappingPanel();
      });
  };

  // Open a project without anyone typing a query string. The address bar is
  // corrected too, so a reload or a shared link keeps working.
  App.prototype.useProject = function (project) {
    if (!project) return;
    this.options.project = project;
    if (root.history && root.history.replaceState) {
      var url = new URL(root.location.href);
      url.searchParams.set("project", project);
      // replaceState, not frappe.set_route: this must not reload the page and
      // throw away the analysis already on the canvas.
      root.history.replaceState({}, "", url.toString());
    }
    this.state.mapNodes = null;      // reload the project's own mappings
    this.state.mappings = [];
    this.state.saveResult = null;
    this.renderMapping();
    toast("Working in migration project “" + project + "”");
  };

  App.prototype.createProject = function (name, dataSource) {
    var self = this;
    dsCall({
      method: "dashboard_studio.api.studio.create_migration_project",
      args: { project_name: name, data_source: dataSource },
    }).then(function (r) {
      var made = r.message || {};
      // A write that reports nothing is not a write that worked. Without this,
      // useProject(undefined) returned at its own guard and the whole thing ended
      // in silence — the exact shape of the fault this call had.
      if (!made.name) {
        toast("The server did not report a created project. Nothing was opened.");
        return;
      }
      self.state.projectOptions = null;   // refetched on the next empty state
      if (made.created_data_source) toast("Also created data source “" + made.data_source + "”");
      self.useProject(made.name);
    }).catch(function (err) {
      toast(refusalMessage(err, "Could not create that migration project."));
    });
  };

  // The panel block shown when the workspace has no project. A DS Migration
  // Project is not a DS Dashboard, and the copy says so — passing a dashboard
  // name in ?project= is the mistake this replaces.
  App.prototype.buildProjectPicker = function () {
    var self = this;
    var box = el("div", "dss-projectpick");
    box.appendChild(el("div", "dss-projectpick-title", "No migration project open"));
    box.appendChild(el("p", "dss-hint",
      "Mappings are saved to a DS Migration Project — a different record from a " +
      "DS Dashboard. Pick one or make one; the address bar is updated for you."));

    // Only the DROPDOWN waits for the list. The create form below renders either
    // way, so a failed or slow read never leaves the workspace with no way out.
    var options = this.state.projectOptions || { projects: [], data_sources: [] };
    if (!this.state.projectOptions) {
      box.appendChild(el("p", "dss-hint", "Loading existing projects…"));
    } else if (options.failed) {
      box.appendChild(el("p", "dss-hint", options.failed + " You can still make a new one."));
    }

    if (options.projects.length) {
      var pick = el("select", "dss-input");
      pick.setAttribute("aria-label", "Migration project to open");
      var none = el("option", null, "Choose a project…");
      none.value = "";
      pick.appendChild(none);
      options.projects.forEach(function (pr) {
        var o = el("option", null, pr.project_name + " · " + (pr.status || "Not Started"));
        o.value = pr.name;
        pick.appendChild(o);
      });
      pick.addEventListener("change", function () { self.useProject(pick.value); });
      box.appendChild(pick);
      box.appendChild(el("div", "dss-projectpick-or", "or make a new one"));
    }

    var name = el("input", "dss-input");
    name.placeholder = "New project name";
    name.setAttribute("aria-label", "New migration project name");
    box.appendChild(name);

    // Required, not optional: DS Migration Project.data_source is reqd and
    // save_migration_mapping_set refuses a project without one, so offering to
    // skip it would create a project that cannot be saved to.
    var source = el("input", "dss-input");
    source.setAttribute("list", "dss-datasource-options");
    source.placeholder = "Data source (required)";
    source.setAttribute("aria-label", "Data source for the new project");
    var dl = el("datalist");
    dl.id = "dss-datasource-options";
    (options.data_sources || []).forEach(function (ds) {
      var o = el("option");
      o.value = ds.name;
      dl.appendChild(o);
    });
    box.appendChild(dl);
    box.appendChild(source);
    box.appendChild(el("p", "dss-hint",
      "A data source names where the queries came from, e.g. Metabase. " +
      "A name that does not exist yet is created."));

    var make = el("button", "dss-btn dss-btn-primary", "Create and open");
    make.addEventListener("click", function () {
      if (!name.value.trim()) { toast("Give the project a name."); return; }
      if (!source.value.trim()) { toast("A project needs a data source."); return; }
      self.createProject(name.value.trim(), source.value.trim());
    });
    box.appendChild(make);
    return box;
  };

  App.prototype.clearCanvas = function () {
    var result = core.clearedCanvas(this.state.mapNodes, this.state.mappings);
    var losing = (this.state.mapNodes || []).length - result.nodes.length;
    if (!losing) { toast("Nothing to clear."); return; }
    // Native confirm: one line, and the only destructive action in this view.
    if (root.confirm && !root.confirm(
        "Remove " + losing + " table(s) and their mappings from the canvas?" +
        (result.keptConfirmed
          ? "\n\n" + result.keptConfirmed + " confirmed mapping(s) will be kept."
          : "") +
        "\n\nNothing already saved to the project is deleted — re-analyse a query to bring it back.")) {
      return;
    }
    this.state.mapNodes = result.nodes;
    this.state.mappings = result.mappings;
    this.state.lastQueryTables = [];
    this.state.lastAnalysis = null;
    this.state.lastAdded = null;
    // Evidence queries belong to the canvas that produced them; keeping them
    // would record SQL on the next save for tables that are no longer here.
    this.state.analyzedQueries = [];
    this.state.pickedSource = null;
    this.state.saveResult = null;
    this.state.generatedMetrics = [];
    this.render();   // the Clear button lives in the import block now
    toast(result.keptConfirmed
      ? "Canvas cleared — " + result.keptConfirmed + " confirmed mapping(s) kept"
      : "Canvas cleared");
  };

  App.prototype.saveMappings = function () {
    var self = this;
    var mappings = this.state.mappings;
    var canvasNodes = core.serializeCanvasNodes(this.state.mapNodes || []);
    var analyzedQueries = this.state.analyzedQueries || [];

    // Without a ?project= there is nothing to save against. This used to pass
    // silently with a toast, so a button labelled "Save mappings" appeared to
    // work and wrote nothing. Say so where the result would have gone.
    if (!this.options.project || !hasFrappe()) {
      this.state.saveResult = {
        ok: false,
        title: "Nothing was saved",
        detail: "This editor was opened without a mapping project, so there is " +
          "nowhere to save to. Open it as /app/dashboard-studio?project=<DS Migration " +
          "Project> and press Save mappings again. The analysis above is not lost — " +
          "re-analysing the same query is a no-op.",
      };
      this.state.generatedMetrics = [];
      this.renderMappingPanel();
      toast("Not saved — no mapping project. See the panel.");
      return;
    }

    dsCall({
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
      self.state.generatedMetrics = result.metrics || [];
      var saved = result.saved_mappings || 0;
      self.state.saveResult = {
        ok: true,
        title: "Saved " + saved + " mapping" + (saved === 1 ? "" : "s"),
        detail: (result.recorded_queries
            ? result.recorded_queries + " query(ies) kept as evidence. " : "") +
          "The project is now " + (result.status || "updated") + ". " +
          (result.metrics && result.metrics.length
            ? "Metrics from those queries are listed below."
            : "Confirm a mapping and save again to generate its DS Metric."),
      };
      toast(self.state.saveResult.title);
      self.renderMappingPanel();
    }).catch(function (err) {
      self.state.saveResult = {
        ok: false, title: "Not saved",
        detail: refusalMessage(err, "The server refused those mappings."),
      };
      self.renderMappingPanel();
      toast(self.state.saveResult.title);
    });
  };

  // Metrics for the picker as [{name, source_doctype}]: mock keys this session;
  // live list (already restricted to executable metrics) cached once.
  // Source DocType for a metric, for the card footer. Synchronous by design —
  // cards redraw constantly — so it warms the metric list once and repaints
  // when it lands, rather than blocking the first render on a call.
  App.prototype.metricInfo = function (metricName) {
    if (!metricName) return null;
    var self = this;
    if (!this._metricList) {
      if (!this._metricListWarming) {
        this._metricListWarming = true;
        this.availableMetrics(function () {
          if (self.state.view === "design") self.refresh();
          self.renderPanel();          // the derived fields land with the list
        });
      }
      return null;
    }
    return this._metricList.filter(function (m) { return m.name === metricName; })[0] || null;
  };

  App.prototype.metricSource = function (metricName) {
    return (this.metricInfo(metricName) || {}).source_doctype || null;
  };

  App.prototype.availableMetrics = function (callback) {
    if (this.state.mock || !hasFrappe()) {
      var mock = root.DSStudioMock || {};
      var sources = {};
      (mock.MOCK_FIELD_CATALOGUE || []).forEach(function (row) {
        sources[row.metric_name] = row.source_doctype;
      });
      var byName = {};
      (mock.MOCK_FIELD_CATALOGUE || []).forEach(function (row) { byName[row.metric_name] = row; });
      this._metricList = Object.keys(mock.MOCK_METRIC_RESULTS || {})
        .map(function (name) {
          var row = byName[name] || {};
          return {
            name: name, source_doctype: sources[name],
            calculation_type: row.calculation_type,
            group_by_field: row.group_by_field, value_field: row.value_field,
          };
        });
      callback(this._metricList);
      return;
    }
    var self = this;
    if (this._metricList) { callback(this._metricList); return; }
    dsCall({ method: "dashboard_studio.api.studio.list_ds_metrics" })
      .then(function (r) {
        // Kept whole: the properties panel reads calculation_type,
        // group_by_field and value_field off the same record.
        self._metricList = r.message || [];
        callback(self._metricList);
      })
      .catch(function () { callback([]); });
  };

  App.prototype.saveChart = function (chart) {
    var self = this;
    if (this.state.mock || !hasFrappe()) {
      toast("Saved “" + chart.chart_title + "” (mock — not persisted)");
      return;
    }
    dsCall({
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
    }).then(function () {
      toast("Saved " + chart.chart_title);
      // Two rules move here: the metric link, and validation currency — an edit
      // makes an earlier pass older than the chart.
      self.refreshReadiness();
    });
  };

  App.prototype.saveLayout = function () {
    var layout = core.serializeLayout(this.state.charts);
    if (this.state.mock || !hasFrappe()) {
      toast("Layout captured for " + layout.length + " charts (mock — not persisted)");
      return;
    }
    var self = this;
    Promise.all(this.state.charts.map(function (c) {
      return dsCall({
        method: "dashboard_studio.api.studio.save_chart",
        args: { chart: c.name, patch: JSON.stringify(core.clampLayout(c)) },
      });
    })).then(function () {
      toast("Saved layout for " + self.state.charts.length + " charts");
      self.markSaved("Layout saved");
    });
  };

  // Two controls on one line, as the mockup's .property-row.
  function twoUp(left, right) {
    var row = el("div", "dss-prop-row");
    row.appendChild(left);
    row.appendChild(right);
    return row;
  }

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
