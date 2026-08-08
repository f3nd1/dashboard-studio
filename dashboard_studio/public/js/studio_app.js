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
  // `silent` suppresses Frappe's own msgprint DIALOG while leaving
  // `_server_messages` in the payload, so the refusal still reaches
  // core.refusalMessage and is shown inline. Read from Frappe's request.js at
  // version-14 and version-15, which both guard the dialog with
  // `if (messages && !opts.silent)` — not guessed, and not a client-side hack
  // around a server that has not changed.
  //
  // Every refusal in this app belongs next to the control it is about. A
  // missing API key is a configuration state, not an interruption.
  function dsCall(opts) {
    opts.silent = true;
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
      // The question box. `proposal` holds what the server proposed and is
      // cleared the moment anything is created or the user asks again — it must
      // never sit on screen next to a query it did not produce.
      question: "",
      proposal: null,
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

    // The two ways in, side by side rather than stacked. Neither is the
    // primary one, and stacking them read as "ask, and if that fails, paste".
    var paths = el("div", "dss-paths");

    var ask = el("div", "dss-path");
    ask.appendChild(el("h2", "dss-path-head", "Ask a question"));
    ask.appendChild(this.buildQuestionBox());
    paths.appendChild(ask);

    var paste = el("div", "dss-path");
    paste.appendChild(el("h2", "dss-path-head", "Or paste the SQL"));
    paste.appendChild(this.buildSqlInput());
    paths.appendChild(paste);
    body.appendChild(paths);

    // Everything that describes the OUTPUT, below both actions that produce
    // it. Title and workbook used to sit under both buttons that consume them,
    // so the query was named after it had already been created.
    var out = el("div", "dss-output");
    var proposal = this.buildProposal();
    if (proposal) out.appendChild(proposal);
    var result = this.buildConversionResult();
    if (result) out.appendChild(result);
    var fields = el("div", "dss-output-fields");
    fields.appendChild(this.buildTitleField());
    fields.appendChild(this.buildWorkbookPicker());
    out.appendChild(fields);
    body.appendChild(out);

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
    // ABOVE the textarea: it is what you need before typing, not after
    // pressing Convert. It doubles as the surface every refusal is written
    // into, so the server's own sentence lands next to the box it is about.
    var note = el("div", "dss-vizimport-note",
      "One table, or two joined on a single a.column = b.column.");
    wrap.appendChild(note);
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

  // ------------------------------------------------------------------ ask ---
  // The examples exist to show the SHAPE of a question that works. The input
  // starts EMPTY and its placeholder is not one of them: prefilling the box
  // with an example made the first chip a no-op, and a placeholder repeating a
  // chip wastes one of the three.
  var EXAMPLES = [
    "which agent brought in the most sales income, and in which year",
    "how many invoices were raised each month last year",
    "average invoice value per customer, highest first",
  ];

  // A question, and the examples that still say something.
  App.prototype.buildQuestionBox = function () {
    var self = this;
    var wrap = el("div", "dss-field dss-questionbox");
    // No label element: the column heading above already says "Ask a question",
    // and two of them stacked was what the screenshot caught. The input keeps
    // its aria-label, so nothing is lost to a screen reader.
    var box = el("input", "dss-input");
    box.type = "text";
    box.placeholder = "Ask in plain English, or press an example below";
    box.value = this.state.question || "";
    box.setAttribute("aria-label", "Ask a question");
    // Updated WITHOUT re-rendering — a re-render per keystroke replaces the
    // input mid-type and takes the caret with it. Fixed twice already here.
    box.addEventListener("input", function () { self.state.question = box.value; });
    wrap.appendChild(box);

    var chips = el("div", "dss-chips");
    var typed = (this.state.question || "").trim();
    EXAMPLES.filter(function (text) {
      // A chip carrying exactly what is already in the box does nothing when
      // pressed, which is the same rule that kept the chart-type picker out.
      return text !== typed;
    }).forEach(function (text) {
      var chip = el("button", "dss-chip", text);
      chip.type = "button";
      chip.addEventListener("click", function () {
        self.state.question = text;
        self.render();
      });
      chips.appendChild(chip);
    });
    wrap.appendChild(chips);

    var go = el("button", "dss-btn dss-btn-primary", "Propose a setup");
    go.type = "button";
    go.title = "Asks the model for a query and checks it. Creates nothing.";
    go.addEventListener("click", function () {
      var question = (self.state.question || "").trim();
      if (!question) { toast("Type a question first."); return; }
      go.disabled = true;
      go.textContent = "Thinking…";
      self.propose(question).then(function () {
        go.disabled = false;
        go.textContent = "Propose a setup";
      });
    });
    wrap.appendChild(go);
    return wrap;
  };

  App.prototype.propose = function (question) {
    var self = this;
    return dsCall({
      method: "dashboard_studio.api.propose.propose_from_question",
      args: { question: question },
    }).then(function (r) {
      self.state.proposal = r.message || null;
      self.state.conversion = null;
      self.render();
    }).catch(function (err) {
      self.state.proposal = { supported: false, reasons: [
        core.refusalMessage(err, "Could not propose a setup for that.")] };
      self.render();
    });
  };

  // The proposed setup. NOTHING here has reached Insights.
  //
  // Read the read-back note in studio_core.js before changing the summary: it
  // is composed from the operations, never written by the model, and that is
  // the whole reason a person reading it is checking anything at all.
  App.prototype.buildProposal = function () {
    var proposal = this.state.proposal;
    if (!proposal) return null;
    var self = this;
    var box = el("div", "dss-saveresult" + (proposal.supported ? "" : " is-bad"));

    if (!proposal.supported) {
      // NO "Not created yet" badge here. That badge means "a proposal exists
      // and is waiting for you", and on a refusal there is no proposal — it
      // would promise something pending that does not exist. A refusal is an
      // empty state carrying the server's own sentence, nothing more.
      box.appendChild(el("div", "dss-saveresult-title", "No setup proposed"));
      (proposal.reasons || []).forEach(function (reason) {
        box.appendChild(el("div", "dss-saveresult-detail", reason));
      });
      box.appendChild(el("div", "dss-hint",
        "Nothing was created. Try asking differently, or paste the SQL instead."));
      return box;
    }

    var head = el("div", "dss-saveresult-title", "Proposed setup");
    head.appendChild(el("span", "dss-badge", "Not created yet"));
    box.appendChild(head);

    // The summary FIRST: it is what the user reads to judge whether the
    // proposal understood the question.
    box.appendChild(el("div", "dss-saveresult-detail",
      core.describeProposal(proposal.operations)));

    var steps = el("div", "dss-handoff-todo");
    steps.appendChild(el("div", "dss-handoff-todo-head", "Operations"));
    (proposal.operations || []).forEach(function (op) {
      var row = el("div", "dss-handoff-todo-row");
      row.appendChild(el("span", "dss-handoff-todo-key", core.labelForOperation(op)));
      row.appendChild(el("span", "dss-handoff-todo-val", core.describeOperation(op)));
      steps.appendChild(row);
    });
    box.appendChild(steps);

    // The validation strip, saying BOTH halves. A green tick that implies more
    // assurance than it gives is worse than no strip at all.
    var strip = el("div", "dss-validation is-ok");
    strip.appendChild(el("div", "dss-validation-line",
      "Checked against the live schema: " +
      (proposal.checked || []).join(", ") + " — all exist and are the right type."));
    strip.appendChild(el("div", "dss-validation-limit", proposal.not_checked));
    box.appendChild(strip);

    (proposal.multiplied || []).forEach(function (table) {
      box.appendChild(el("div", "dss-validation is-warn",
        "This joins " + table + ", a child table: each parent record gets one " +
        "row per child row, so any total counts it more than once. " +
        "Sanity-check the number before trusting it."));
    });

    // No workbook picker in here. There is already one below, `convertSql`
    // reads it either way, and two of them on screen is two controls meaning
    // one thing. (The design also called for a chart-type picker beside it;
    // this app does not create charts — that code was archived — so there is
    // nothing to pick. Better absent than a control that does nothing.)
    var actions = el("div", "dss-insights-links");
    var create = el("button", "dss-btn dss-btn-primary", "Create in Insights");
    create.type = "button";
    create.addEventListener("click", function () {
      create.disabled = true;
      var note = el("div", "dss-hint");
      box.appendChild(note);
      self.convertSql(proposal.sql, note).then(function () {
        create.disabled = false;
      });
    });
    actions.appendChild(create);

    var edit = el("button", "dss-btn", "Edit the setup");
    edit.type = "button";
    edit.title = "Puts the query in the box below, where you can change it.";
    edit.addEventListener("click", function () {
      self.state.vizSql = proposal.sql;
      self.state.proposal = null;
      self.render();
    });
    actions.appendChild(edit);

    var again = el("button", "dss-btn", "Ask differently");
    again.type = "button";
    again.addEventListener("click", function () {
      self.state.proposal = null;
      self.render();
    });
    actions.appendChild(again);
    box.appendChild(actions);
    return box;
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
