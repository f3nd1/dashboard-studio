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
      verifyValues: {},
      verifyError: "",
    };
  }

  App.prototype.render = function () {
    this.mount.innerHTML = "";
    var wrap = el("div", "dss-wrap");

    // No title here. frappe.ui.make_app_page already renders the page header
    // from the Desk page's own `title`, and adding an <h1> put "Metabase →
    // Insights" on screen twice, stacked. The Desk page owns the title; this
    // app owns everything below it.
    var hero = el("div", "dss-hero");
    hero.appendChild(el("div", "dss-kicker", "Converter"));
    hero.appendChild(el("h3", "dss-hero-title", "Rebuild a query in Insights"));
    hero.appendChild(el("p", "dss-hero-blurb",
      "Paste the SQL and it writes the same question into Insights as clickable " +
      "operations rather than a block of text. Nothing is trusted until you have " +
      "compared its number against the original. Covers one table, or two joined " +
      "on a single a.column = b.column; subqueries and anything the join cannot " +
      "be read out of are refused rather than guessed at."));
    wrap.appendChild(hero);

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
    // Said here because the title comes back different from what was typed, and
    // an unexplained prefix reads like a bug rather than the gate working.
    wrap.appendChild(el("p", "dss-hint",
      "Created as “[UNVERIFIED] …” until you confirm the number below."));
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

  // A converted query, and the check that has to happen before anyone trusts it.
  //
  // Deliberately not styled as a success. A conversion that LOOKS done is the
  // failure this whole gate exists to prevent: the translation may be right,
  // and nothing here can tell — only a person comparing the two numbers can.
  App.prototype.buildConversionResult = function () {
    var self = this;
    var made = this.state.conversion;
    if (!made) return null;
    var verified = !!made.verified;
    var box = el("div", "dss-saveresult " + (verified ? "is-ok" : "is-unverified"));
    box.appendChild(el("div", "dss-saveresult-title", verified
      ? "Verified — " + made.name
      : "Converted, NOT yet verified — " + made.name));
    box.appendChild(el("div", "dss-saveresult-detail", verified
      ? "“" + made.title + "” — you confirmed its number matches the original."
      : "“" + made.title + "” — nothing has checked that it counts the same rows."));

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

    if (verified) return box;

    // One line: two small numbers and a button. The gate is unchanged — a
    // person still has to type both and the server still refuses a mismatch —
    // but a form with two labelled fields and a paragraph read like paperwork,
    // and paperwork gets skipped. Labels are aria-label + placeholder rather
    // than <label> elements so it stays one row without losing the screen
    // reader.
    var check = el("div", "dss-verify");
    check.appendChild(el("span", "dss-verify-head", "Same number?"));
    var inputs = {};
    [["metabase", "Number in Metabase", "Metabase"],
     ["insights", "Number in Insights", "Insights"]].forEach(function (spec, i) {
      if (i) check.appendChild(el("span", "dss-verify-eq", "="));
      var field = el("input", "dss-input dss-verify-num");
      field.setAttribute("aria-label", spec[1]);
      field.placeholder = spec[2];
      field.value = (self.state.verifyValues || {})[spec[0]] || "";
      field.addEventListener("input", function () {
        var values = self.state.verifyValues || (self.state.verifyValues = {});
        values[spec[0]] = field.value;
      });
      inputs[spec[0]] = field;
      check.appendChild(field);
    });

    var mark = el("button", "dss-btn dss-verify-go", "Confirm");
    mark.title = "Records that you compared the two numbers. A mismatch is " +
      "refused — the query stays marked unverified.";
    mark.addEventListener("click", function () {
      self.verifyConversion(made.name, inputs.metabase.value, inputs.insights.value);
    });
    check.appendChild(mark);
    box.appendChild(check);
    if (this.state.verifyError) {
      box.appendChild(el("div", "dss-verify-error", this.state.verifyError));
    }
    return box;
  };

  App.prototype.verifyConversion = function (query, metabaseValue, insightsValue) {
    var self = this;
    if (!hasFrappe()) return;
    this.state.verifyError = "Checking…";
    this.render();
    dsCall({
      method: "dashboard_studio.api.convert.verify_converted_query",
      args: { query: query, metabase_value: metabaseValue, insights_value: insightsValue },
    }).then(function (r) {
      var done = r.message || {};
      self.state.conversion = Object.assign({}, self.state.conversion,
        { verified: true, title: done.title });
      self.state.verifyError = "";
      self.render();
    }).catch(function (err) {
      // The server refuses a mismatch. Shown in full: "Metabase says 1234,
      // Insights says 1200" is the useful part, not a generic failure.
      self.state.verifyError = core.refusalMessage(err, "Could not verify that.");
      self.render();
    });
  };


  root.DSStudioApp = {
    mount: function (mount, options) {
      var app = new App(mount, options);
      app.render();
      return app;
    },
  };
})(typeof window !== "undefined" ? window : this);
