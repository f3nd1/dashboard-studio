/*
 * SQL → Insights converter — the whole front end.
 *
 * What is left of a much larger SPA. The dashboard builder, source mapping,
 * catalogue, validation and governance workspaces went to
 * archive/studio_app_full.js when the product narrowed to one job; the
 * Metabase card-id route went the same way later, leaving one front door:
 * paste the query, get Insights operations.
 *
 * Dependency-free vanilla JS, no bundler. Mounted by the Desk page via
 * frappe.require; DSStudioApp.mount stays the entry point it always was.
 */
(function (root) {
  "use strict";

  // ---------------------------------------------------------------- helpers

  // Pure logic lives in studio_core.js so it can be checked under Node.
  var core = root.DSStudioCore || {};

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
  // server's own text, which core.refusalMessage already knows how to read.
  //
  // A missing `message` is NOT an error: get_migration_project returns null for
  // an empty project. Only an explicit refusal marker counts.

  function toast(msg) {
    if (hasFrappe() && root.frappe.show_alert) root.frappe.show_alert({ message: msg, indicator: "blue" });
    else if (root.console) root.console.log("[Dashboard Studio] " + msg);
  }

  // EVERY server call goes through here. Frappe RESOLVES this promise when the
  // server refused: the ajax .always path hands back the error payload instead
  // of rejecting, so `.then(r => r.message)` sees undefined and cannot tell
  // "worked, returned nothing" from "threw". That is how creating a migration
  // project failed in total silence — request sent, refusal returned, .then ran,
  // nothing said. Normalise it once, here, into a real rejection carrying the
  // server's own text, which core.refusalMessage already knows how to read.
  //
  // A missing `message` is NOT an error: get_migration_project returns null for
  // an empty project. Only an explicit refusal marker counts.
  function dsCall(opts) {
    return root.frappe.call(opts).then(function (r) {
      r = r || {};
      if (r.exc_type || r.exc || r.exception || r._server_messages || r.errors) {
        // Empty message on purpose: core.refusalMessage prefers err.message, so
        // a class name like "ValidationError" here would hide the server's own
        // sentence. Only fall back to the class when there is none.
        var e = new Error(
          r._server_messages || r.exception || r.exc ? "" : (r.exc_type || ""));
        // The WHOLE payload, not three hand-picked fields. Which key carries the
        // message depends on the site's settings and API version, and dropping
        // the others is what turned a specific refusal into "Could not convert
        // that card."
        e.responseJSON = r;
        throw e;
      }
      return r;
    });
  }

  // ------------------------------------------------------------------- app
  function App(mount, options) {
    this.mount = mount;
    this.state = {
      // Everything the converter needs. The old app carried a dashboard, its
      // charts, sections, metrics and mock fallbacks; none of that has a job now.
      vizWorkbook: (options || {}).workbook || "",
      vizWorkbooks: null,
      conversion: null,
    };
  }

  App.prototype.render = function () {
    this.mount.innerHTML = "";
    var wrap = el("div", "dss-wrap");

    // No heading and no preamble. frappe.ui.make_app_page already renders the
    // page title from the Desk page's own `title`; everything else that used to
    // sit here was explanation, and the controls are the explanation.
    var card = el("section", "dss-vizstep");
    var body = el("div", "dss-vizstep-body");
    body.appendChild(this.buildSqlInput());
    body.appendChild(this.buildTitleField());
    body.appendChild(this.buildWorkbookPicker());
    var result = this.buildConversionResult();
    if (result) body.appendChild(result);
    card.appendChild(body);
    wrap.appendChild(card);

    this.mount.appendChild(wrap);
  };

  // What the query is called in Insights.
  //
  // Set BEFORE it is created, not renamed afterwards: the auto-generated name
  // is the table plus the word "query", which is the same string for every
  // report built on that table.
  //
  // State is updated on input WITHOUT re-rendering. A re-render on every
  // keystroke replaces the input mid-type and takes the caret with it — a fault
  // already fixed twice in this app; do not reintroduce it.
  App.prototype.buildTitleField = function () {
    var self = this;
    var wrap = el("div", "dss-field dss-titlefield");
    wrap.appendChild(el("label", "dss-field-label", "Title in Insights"));
    var input = el("input", "dss-input");
    input.setAttribute("aria-label", "Title in Insights");
    input.placeholder = "Left blank: named after the table";
    input.value = this.state.vizTitle || "";
    input.addEventListener("input", function () { self.state.vizTitle = input.value; });
    wrap.appendChild(input);
    return wrap;
  };

  // Which Insights workbook the query lands in.
  //
  // Fetched once per visit and cached in state: the list rarely changes and this
  // is rebuilt on every keystroke elsewhere in the panel. A failed fetch is not
  // an error — it leaves the default, which is what happened before there was a
  // picker at all.
  App.prototype.buildWorkbookPicker = function () {
    var self = this;
    var wrap = el("div", "dss-field dss-workbookpick");
    wrap.appendChild(el("label", "dss-field-label", "Insights workbook"));

    var books = this.state.vizWorkbooks;
    if (!books) {
      wrap.appendChild(el("p", "dss-hint", "Loading workbooks…"));
      this.loadWorkbooks();
      return wrap;
    }

    var select = el("select", "dss-input");
    select.setAttribute("aria-label", "Insights workbook");
    // The empty value is the default workbook, created on first use. Named as
    // such rather than left blank, so "no choice" reads as a choice.
    var fallback = el("option", null, "Dashboard Studio (default)");
    fallback.value = "";
    select.appendChild(fallback);
    books.forEach(function (book) {
      // Skip a workbook whose title IS the default — it is the same record the
      // empty option already points at, and two rows meaning one place is the
      // kind of thing someone debugs at 3am.
      if (book.title === "Dashboard Studio") return;
      var option = el("option", null, book.title + " (" + book.name + ")");
      option.value = book.name;
      select.appendChild(option);
    });
    select.value = this.state.vizWorkbook || "";
    select.addEventListener("change", function () {
      self.state.vizWorkbook = select.value;
    });
    wrap.appendChild(select);
    wrap.appendChild(el("p", "dss-hint", books.length
      ? "The query is created here. A workbook groups related queries in Insights."
      : "No workbooks found — one named Dashboard Studio will be created."));
    return wrap;
  };

  App.prototype.loadWorkbooks = function () {
    var self = this;
    if (this._workbooksLoading || !hasFrappe()) {
      // No backend: settle on the empty list so the picker stops saying
      // "Loading…" forever and the default still works.
      if (!hasFrappe()) this.state.vizWorkbooks = [];
      return;
    }
    this._workbooksLoading = true;
    dsCall({
      method: "dashboard_studio.api.insights.list_insights_workbooks",
    }).then(function (r) {
      self.state.vizWorkbooks = (r.message || {}).workbooks || [];
      self._workbooksLoading = false;
      self.render();
    }).catch(function () {
      // A refusal here (no Insights role, Insights not installed) is already
      // reported by Create; it must not also block the panel from rendering.
      self.state.vizWorkbooks = [];
      self._workbooksLoading = false;
      self.render();
    });
  };

  // The query to convert. One box, one button — this is the whole front door.
  App.prototype.buildSqlInput = function () {
    var self = this;
    var wrap = el("div", "dss-vizimport");
    var box = el("textarea", "dss-input dss-sqlbox");
    box.placeholder =
      "SELECT `academic_year`, COUNT(*) FROM `tabStudent Applicant` GROUP BY `academic_year`";
    box.setAttribute("aria-label", "SQL to convert");
    box.value = this.state.vizSql || "";
    box.addEventListener("input", function () { self.state.vizSql = box.value; });
    wrap.appendChild(box);

    var row = el("div", "dss-vizimport-row");
    var go = el("button", "dss-btn dss-btn-primary", "Convert SQL →");
    go.title = "Parses the query into Insights operations, including a Join " +
      "Table step when the ON clause is a single a.column = b.column. Both " +
      "column names are checked against the DocType.";
    row.appendChild(go);
    wrap.appendChild(row);

    // Also the surface every refusal is written into, so the server's own
    // sentence lands next to the box it is about.
    var note = el("div", "dss-vizimport-note",
      "One table, or two joined on a single a.column = b.column.");
    wrap.appendChild(note);

    go.addEventListener("click", function () {
      var sql = (box.value || "").trim();
      if (!sql) { note.textContent = "Paste a query first."; return; }
      if (!hasFrappe()) { note.textContent = "Converting needs the server."; return; }
      note.textContent = "Translating that query…";
      go.disabled = true;
      var done = function () { go.disabled = false; };
      self.convertSql(sql, note).then(done, done);
    });
    return wrap;
  };

  App.prototype.convertSql = function (sql, note) {
    var self = this;
    return dsCall({
      method: "dashboard_studio.api.convert.convert_sql",
      args: { sql: sql, title: (this.state.vizTitle || "").trim() || null,
              workbook: this.state.vizWorkbook || null },
    }).then(function (r) {
      var made = r.message;
      if (!made || !made.name) {
        note.textContent = "The server reported no query. Nothing was created.";
        return null;
      }
      self.state.conversion = made;
      self.render();
      return made;
    }).catch(function (err) {
      note.textContent = core.refusalMessage(err, "Could not convert that query.");
    });
  };

  // What was created, and the operations it was created from.
  //
  // The operations list stays. It was never part of the number check — it is
  // how somebody reads back what the translation decided and spots a wrong one
  // before running it, which is the only review step left (ADR-008).
  App.prototype.buildConversionResult = function () {
    var made = this.state.conversion;
    if (!made) return null;
    var box = el("div", "dss-saveresult is-ok");
    box.appendChild(el("div", "dss-saveresult-title", "Converted — " + made.name));
    box.appendChild(el("div", "dss-saveresult-detail", "“" + made.title + "”"));

    var steps = el("div", "dss-handoff-todo");
    steps.appendChild(el("div", "dss-handoff-todo-head", "Operations created"));
    (made.operations || []).forEach(function (op, i) {
      var row = el("div", "dss-handoff-todo-row");
      row.appendChild(el("span", "dss-handoff-todo-key", String(i + 1) + ". " + op.type));
      row.appendChild(el("span", "dss-handoff-todo-val", core.describeOperation(op)));
      steps.appendChild(row);
    });
    box.appendChild(steps);

    var links = el("div", "dss-insights-links");
    var open = el("a", "dss-link", "Open in Insights");
    open.href = made.insights_url;
    open.target = "_blank";
    open.rel = "noopener";
    links.appendChild(open);
    box.appendChild(links);
    return box;
  };


  root.DSStudioApp = {
    mount: function (mount, options) {
      var app = new App(mount, options);
      app.render();
      return app;
    },
  };
})(typeof window !== "undefined" ? window : this);
