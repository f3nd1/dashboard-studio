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

  // A button that makes a server round-trip.
  //
  // The busy state lives in `state`, NOT on the DOM node, because every one of
  // these handlers ends in a render() that throws the node away. Setting
  // `button.disabled` and a label directly looked right in isolation and was
  // gone a moment later — "Build the query" removed its own confirm box first,
  // so the screen went completely static while the request ran, which is
  // indistinguishable from a hung page.
  //
  // Any in-flight request disables ALL of them: there is one output region, so
  // a second request started underneath the first would replace the answer to
  // a question nobody can see was asked.
  function actionButton(app, key, label, busyLabel, onClick) {
    var busy = app.state.busy === key;
    var button = el("button", "dss-btn dss-btn-primary" + (busy ? " is-busy" : ""));
    button.type = "button";
    button.disabled = !!app.state.busy;
    if (busy) {
      button.appendChild(el("span", "dss-spinner"));
      button.setAttribute("aria-busy", "true");
    }
    button.appendChild(el("span", null, busy ? busyLabel : label));
    button.addEventListener("click", function () {
      if (app.state.busy) return;
      onClick();
    });
    return button;
  }

  // Start / finish a round-trip. Paired: `finish` runs on success AND failure,
  // so a refusal never leaves a button spinning forever.
  function begin(app, key) {
    app.state.busy = key;
    app.render();
  }

  function finish(app) {
    app.state.busy = null;
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
      // Which input is showing. Switching it never touches the output — a
      // result stays put until something replaces it.
      tab: "ask",
      // Whatever the last action produced, when it is not a proposal or a
      // created query: a refusal, or "working on it". ONE output region means
      // one place this can be shown.
      notice: "",
      // The API key, if the site has none and the user pasted one.
      //
      // A plain property on this object, which lives as long as the page does.
      // NOT localStorage, NOT sessionStorage, NOT a cookie, NOT a record — a
      // refresh loses it, and the label says so. It is sent with the propose
      // request and nowhere else.
      apiKey: "",
      // Same rules as the key: state only, gone on refresh, blank = default.
      model: "",
      siteHasKey: null,
      // WHICH TABLES the question is about. The model used to decide this
      // silently, which is how a question about recruitment agents was answered
      // from ERPNext's sales-commission tables — every column real, every type
      // right, nothing to object to. `tableMode` is the user's choice of who
      // decides; `tables` is what they settled on, awaiting confirmation.
      tableMode: "auto",
      tables: "",
      confirming: false,
      // The sidecar loaded beside an exported .sql — the source card's
      // `series_settings` and `display`. State only, like the API key: it
      // belongs to the query in the box and nothing else. Null means the
      // ordinary paste, and the chart is left at Insights' default.
      vizCard: null,
      vizCardName: "",
      // The server-side export search. `exports` is the last reply — null means
      // "not asked yet", and an unavailable one carries the folder problem so
      // the box explains itself instead of looking empty.
      exportSearch: "",
      exports: null,
      exportsLoading: false,
      // Which round-trip is in flight, or null. Read by `actionButton`.
      busy: null,
      // Which corrected attempt is running (0 = the first, ordinary one).
      // Drives the build button's busy label so a retry is never invisible.
      retrying: 0,
      // The provider's model list, once asked for. Null means "not asked".
      // Session state like the key: never saved, gone on refresh.
      models: null,
      modelSearch: "",
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

    // Two panes: the input on the left, the ONE output region on the right.
    //
    // Side by side, the two inputs each grew their own result surface — a SQL
    // refusal appeared above its textarea while the shared panel below showed
    // the other path's state, and neither was tied to the button just pressed.
    // Tabs mean one input is visible at a time and there is one place to look.
    var paths = el("div", "dss-paths");

    var left = el("div", "dss-path");
    var tabs = el("div", "dss-tabs");
    var self = this;
    if (this.state.siteHasKey === null) this.loadKeyState();
    // The key gets its OWN tab, and only when the site has no key of its own —
    // a configured site sees two tabs and no mention of a key anywhere.
    var pairs = [["ask", "Ask a question"], ["sql", "Paste SQL"]];
    if (this.state.siteHasKey === false) pairs.push(["key", "API key"]);
    // If the site turns out to have one while that tab is open, fall back
    // rather than leaving a selected tab that no longer exists.
    if (this.state.tab === "key" && this.state.siteHasKey !== false) {
      this.state.tab = "ask";
    }
    pairs.forEach(function (pair) {
      var tab = el("button", "dss-tab" + (self.state.tab === pair[0] ? " is-on" : ""),
                   pair[1]);
      tab.type = "button";
      tab.setAttribute("aria-selected", self.state.tab === pair[0] ? "true" : "false");
      tab.addEventListener("click", function () {
        // Only the input changes. The output is left exactly as it was.
        self.state.tab = pair[0];
        self.render();
      });
      tabs.appendChild(tab);
    });
    left.appendChild(tabs);
    left.appendChild(this.state.tab === "key" ? this.buildKeyField()
      : this.state.tab === "sql" ? this.buildSqlInput()
        : this.buildQuestionBox());
    paths.appendChild(left);

    // The one output region. Every result from either tab lands here and
    // nowhere else, with the fields that describe it underneath.
    var out = el("div", "dss-output");
    // Dismiss. Clears the RESULT and nothing else — not the question, the SQL,
    // the key, the title or the workbook. Somebody who clears a refusal is
    // usually about to try again with the same inputs, and wiping those would
    // make this a reset button wearing an X.
    if (this.state.proposal || this.state.conversion || this.state.notice
        || this.state.confirming) {
      var clear = el("button", "dss-dismiss", "\u00d7");
      clear.type = "button";
      clear.title = "Clear this result";
      clear.setAttribute("aria-label", "Clear this result");
      clear.addEventListener("click", function () {
        self.state.proposal = null;
        self.state.conversion = null;
        self.state.notice = "";
        self.state.confirming = false;
        self.render();
      });
      out.appendChild(clear);
    }
    if (this.state.notice) {
      // Wrapped in -detail so a refusal is set in the same type as every other
      // result. Rendered bare it came out at body size and read as a different
      // kind of thing from the refusals inside a proposal card.
      var notice = el("div", "dss-saveresult is-bad");
      notice.appendChild(el("div", "dss-saveresult-detail", this.state.notice));
      out.appendChild(notice);
    }
    var confirm = this.buildTableConfirm();
    if (confirm) out.appendChild(confirm);
    var proposal = this.buildProposal();
    if (proposal) out.appendChild(proposal);
    var result = this.buildConversionResult();
    if (result) out.appendChild(result);
    var fields = el("div", "dss-output-fields");
    fields.appendChild(this.buildTitleField());
    fields.appendChild(this.buildWorkbookPicker());
    out.appendChild(fields);
    paths.appendChild(out);
    body.appendChild(paths);

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

    // Load an exported report FROM THE SERVER.
    //
    // This was a native `<input type=file>` and could never have worked: a file
    // input opens the CLIENT's filesystem, so clicking it showed the user their
    // own Mac's Downloads while the exports sat on the bench at
    // sites/metabase_sql. That is a browser security boundary, not a path to
    // configure. The list has to come from the server, so it does — and
    // searching it also answers the original complaint, which was browsing
    // ~1775 files by raw filename.
    var load = el("div", "dss-vizimport-load");
    var search = el("input", "dss-input dss-searchbox");
    search.type = "search";
    search.placeholder = "Find an exported report — type part of its name";
    search.setAttribute("aria-label", "Search exported Metabase reports");
    search.value = this.state.exportSearch || "";
    var results = el("div", "dss-searchresults");
    results.id = "dss-search-results";
    var status = el("div", "dss-hint dss-searchstatus");
    status.id = "dss-search-status";
    load.appendChild(search);
    load.appendChild(status);
    load.appendChild(results);
    wrap.appendChild(load);

    // Looked up from the LIVE document every time, never captured.
    //
    // These nodes are painted again when the server replies, and any other
    // async state change — the workbook list arriving — re-renders the page in
    // between and detaches them. Holding the references painted a correct list
    // into nodes that were no longer on screen: the state said four reports,
    // the page still said "Looking…". Found by screenshotting it; the
    // assertions on state were all green.
    var paint = function () {
      var results = document.getElementById("dss-search-results");
      var status = document.getElementById("dss-search-status");
      if (!results || !status) return;
      results.innerHTML = "";
      var found = self.state.exports;
      if (!found) {
        status.textContent = self.state.exportsLoading
          ? "Looking…"
          : "Optional. Without an exported report the query still converts; " +
            "only the chart is left at Insights' default.";
        return;
      }
      if (!found.available) {
        // Say WHICH folder and why, rather than showing an empty box that
        // reads as "nothing matched".
        status.textContent = found.problem || "No exports could be read.";
        return;
      }
      var list = found.reports || [];
      if (!list.length) {
        status.textContent = "Nothing matching that in " + found.directory + ".";
        return;
      }
      status.textContent = found.total > found.shown
        ? "Showing " + found.shown + " of " + found.total + " — keep typing to narrow it."
        : found.total + (found.total === 1 ? " report" : " reports") + " in " + found.directory;
      list.forEach(function (item) {
        var row = el("button", "dss-searchresult");
        row.type = "button";
        row.appendChild(el("span", "dss-searchresult-name", item.report));
        // Whether it will produce a chart is the thing worth knowing BEFORE
        // clicking, since that is what the sidecar is for.
        row.appendChild(el("span",
          "dss-searchresult-tag" + (item.has_sidecar ? " is-ok" : ""),
          item.has_sidecar ? "chart settings" : "SQL only"));
        row.addEventListener("click", function () { self.loadExport(item.stem); });
        results.appendChild(row);
      });
    };
    paint();

    var timer = null;
    search.addEventListener("input", function () {
      self.state.exportSearch = search.value;
      // Debounced: this hits the server on every keystroke otherwise, and the
      // folder has ~1775 files in it.
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        self.searchExports(search.value, paint);
      }, 200);
    });
    // One call on first paint so the folder problem (missing, empty, not
    // configured) is on screen before anybody types into a box that cannot work.
    if (this.state.exports === null && !this.state.exportsLoading) {
      this.searchExports(this.state.exportSearch || "", paint);
    }

    var row = el("div", "dss-vizimport-row");
    var go = actionButton(this, "convert", "Convert SQL →",
                          "Converting the query…", function () {
      var sql = (box.value || "").trim();
      // Every one of these lands in the OUTPUT region. The helper line above
      // the textarea used to double as the refusal surface, which put a long
      // refusal in a narrow column where it read as cropped, next to a shared
      // panel showing the other tab's state.
      if (!sql) { self.state.notice = "Paste a query first."; self.render(); return; }
      if (!hasFrappe()) {
        self.state.notice = "Converting needs the server."; self.render(); return;
      }
      self.state.proposal = null;
      self.state.conversion = null;
      self.state.notice = "";
      begin(self, "convert");
      var done = function () { finish(self); self.render(); };
      self.convertSql(sql).then(done, done);
    });
    go.title = "Parses the query into Insights operations, including a Join " +
      "Table step when the ON clause is a single a.column = b.column. Both " +
      "column names are checked against the DocType.";
    row.appendChild(go);
    wrap.appendChild(row);
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
    // Short enough not to clip in the tab pane, which is narrower than the
    // column this used to sit in. The chips below it are the examples.
    box.placeholder = "Ask in plain English…";
    box.value = this.state.question || "";
    box.setAttribute("aria-label", "Ask a question");
    // Updated WITHOUT re-rendering — a re-render per keystroke replaces the
    // input mid-type and takes the caret with it. Fixed twice already here.
    box.addEventListener("input", function () { self.state.question = box.value; });
    wrap.appendChild(box);

    // Automatic or manual, before anything is built. Neither hides the choice:
    // automatic still shows what the model picked and waits.
    var modes = el("div", "dss-modes");
    [["auto", "Let the model suggest tables"],
     ["manual", "I'll name the tables"]].forEach(function (pair) {
      var id = "dss-mode-" + pair[0];
      var label = el("label", "dss-mode");
      var radio = el("input");
      radio.type = "radio";
      radio.name = "dss-tablemode";
      radio.id = id;
      radio.checked = self.state.tableMode === pair[0];
      radio.addEventListener("change", function () {
        self.state.tableMode = pair[0];
        self.render();
      });
      label.appendChild(radio);
      label.appendChild(document.createTextNode(" " + pair[1]));
      modes.appendChild(label);
    });
    wrap.appendChild(modes);

    if (this.state.tableMode === "manual") {
      var tables = el("input", "dss-input");
      tables.type = "text";
      tables.placeholder = "DocTypes, comma separated — e.g. Agent";
      tables.setAttribute("aria-label", "DocTypes to build the query over");
      tables.value = this.state.tables || "";
      tables.addEventListener("input", function () { self.state.tables = tables.value; });
      wrap.appendChild(tables);
      wrap.appendChild(el("p", "dss-hint",
        "The query is built over these and nothing else. A question they cannot " +
        "answer is refused rather than widened to another table."));
    }

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

    var go = actionButton(this, "propose", "Propose a setup",
                          "Reading your question…", function () {
      var question = (self.state.question || "").trim();
      if (!question) { toast("Type a question first."); return; }
      begin(self, "propose");
      var done = function () { finish(self); self.render(); };
      // Manual: the tables are already settled, so go straight to the query.
      // Automatic: ask which tables FIRST and stop, so the answer can be read
      // and changed before a query exists to rubber-stamp.
      (self.state.tableMode === "manual"
        ? self.propose(question)
        : self.proposeTables(question)).then(done, done);
    });
    go.title = "Asks the model for a query and checks it. Creates nothing.";
    wrap.appendChild(go);
    return wrap;
  };

  // The API key, when the SITE has none.
  //
  // It lives in `this.state.apiKey` — a property of a JS object, for as long as
  // the page is open. It is NOT written to localStorage, sessionStorage, a
  // cookie, a record or a file by any path, and a refresh loses it. The label
  // says exactly that, because a password box that silently persisted would be
  // the worst version of this.
  //
  // Only ever reached from its own tab, which only exists when the site has no
  // key of its own — so there is no hidden state to keep here.
  App.prototype.buildKeyField = function () {
    var self = this;
    var wrap = el("div", "dss-keyfield");
    wrap.appendChild(el("label", "dss-field-label", "API key (this session only)"));
    var input = el("input", "dss-input");
    input.type = "password";
    input.autocomplete = "off";
    input.placeholder = "Paste a key to use the question box";
    input.setAttribute("aria-label", "API key, kept for this browser session only");
    input.value = this.state.apiKey || "";
    // No re-render on input: it would replace the box mid-type and take the
    // caret with it, which this app has fixed twice already.
    input.addEventListener("input", function () { self.state.apiKey = input.value; });
    wrap.appendChild(input);
    wrap.appendChild(el("p", "dss-hint",
      "Kept in this page only — never saved, and gone when you refresh. " +
      "Set `llm_api_key` in site_config.json to stop being asked."));

    // Free TEXT with an optional browse, not a dropdown: model names change,
    // and a hardcoded list goes stale silently. The browse asks the provider
    // what THIS key can see, so it cannot be out of date. Blank still means the
    // default, so leaving it alone behaves exactly as before there was a field.
    // Held in state like the key — never localStorage, a cookie or a record.
    wrap.appendChild(el("label", "dss-field-label", "Model (optional)"));
    var model = el("input", "dss-input dss-modelinput");
    model.type = "text";
    model.autocomplete = "off";
    model.placeholder = "Leave blank for the default";
    model.setAttribute("aria-label", "Model, kept for this browser session only");
    model.value = this.state.model || "";
    model.addEventListener("input", function () { self.state.model = model.value; });
    wrap.appendChild(model);

    var browse = el("div", "dss-modelbrowse");
    var found = this.state.models;
    browse.appendChild(actionButton(this, "models", "Browse models",
                                    "Asking the provider…", function () {
      begin(self, "models");
      self.listModels().then(function () { finish(self); self.render(); });
    }));
    if (found && !found.available) {
      // Says WHY — no key yet, a 401, a network failure — rather than an empty
      // list that reads as "this key has no models".
      browse.appendChild(el("div", "dss-hint dss-modelproblem", found.problem));
    }
    if (found && found.available) {
      var filter = el("input", "dss-input dss-modelfilter");
      filter.type = "search";
      filter.placeholder = "Filter " + found.models.length + " models";
      filter.setAttribute("aria-label", "Filter the model list");
      filter.value = this.state.modelSearch || "";
      var list = el("div", "dss-searchresults");
      var paint = function () {
        list.innerHTML = "";
        var want = (self.state.modelSearch || "").toLowerCase();
        found.models.filter(function (id) {
          return id.toLowerCase().indexOf(want) !== -1;
        }).forEach(function (id) {
          var row = el("button", "dss-searchresult");
          row.type = "button";
          row.appendChild(el("span", "dss-searchresult-name", id));
          if (id === found.default) {
            // Which one a blank field would pick, so choosing it explicitly is
            // visibly the same thing rather than a guess.
            row.appendChild(el("span", "dss-searchresult-tag is-ok", "default"));
          }
          row.addEventListener("click", function () {
            self.state.model = id;
            self.render();
          });
          list.appendChild(row);
        });
        if (!list.childNodes.length) {
          list.appendChild(el("div", "dss-hint", "Nothing matching that."));
        }
      };
      filter.addEventListener("input", function () {
        self.state.modelSearch = filter.value;
        paint();
      });
      paint();
      browse.appendChild(filter);
      browse.appendChild(list);
    }
    wrap.appendChild(browse);
    return wrap;
  };

  // Ask the provider which models this key can see. The key goes with the
  // request and nowhere else, exactly as it does for a proposal.
  App.prototype.listModels = function () {
    var self = this;
    if (!hasFrappe()) {
      this.state.models = { available: false,
                            problem: "Browsing the models needs the server." };
      return Promise.resolve();
    }
    return dsCall({
      method: "dashboard_studio.api.propose.list_models",
      args: { api_key: this.state.apiKey || null },
    }).then(function (r) {
      self.state.models = r.message || { available: false,
        problem: "The server returned no model list." };
    }).catch(function (err) {
      // Never stuck and never silent — the same rule the busy states follow.
      self.state.models = { available: false,
        problem: core.refusalMessage(err, "The models could not be listed.") };
    });
  };

  App.prototype.loadKeyState = function () {
    var self = this;
    if (this._keyLoading || !hasFrappe()) { return; }
    this._keyLoading = true;
    dsCall({ method: "dashboard_studio.api.propose.llm_key_is_configured" })
      .then(function (r) {
        self.state.siteHasKey = !!((r.message || {}).configured);
        self._keyLoading = false;
        self.render();
      }).catch(function () {
        // Cannot tell: show the field. Offering it needlessly is a smaller
        // fault than hiding the only way to use the tab.
        self.state.siteHasKey = false;
        self._keyLoading = false;
        self.render();
      });
  };

  App.prototype.proposeTables = function (question) {
    var self = this;
    self.state.proposal = null;
    self.state.conversion = null;
    self.state.notice = "";
    return dsCall({
      method: "dashboard_studio.api.propose.propose_tables",
      args: { question: question, api_key: this.state.apiKey || null,
              model: this.state.model || null },
    }).then(function (r) {
      var names = (r.message || {}).doctypes || [];
      self.state.tables = names.join(", ");
      self.state.confirming = true;
      if (!names.length) {
        self.state.confirming = false;
        self.state.notice = "No table on this site looks like it answers that. " +
          "Name the record type yourself with \u201cI'll name the tables\u201d.";
      }
      self.render();
    }).catch(function (err) {
      self.state.notice = core.refusalMessage(err, "Could not suggest any tables.");
      self.render();
    });
  };

  // The confirm step. It sits in the output pane, BEFORE any query exists —
  // a table confirmed underneath a finished-looking result gets rubber-stamped,
  // which is the failure this whole step is for.
  App.prototype.buildTableConfirm = function () {
    if (!this.state.confirming) return null;
    var self = this;
    var box = el("div", "dss-saveresult");
    var head = el("div", "dss-saveresult-title", "Tables to build over");
    head.appendChild(el("span", "dss-badge", "Confirm first"));
    box.appendChild(head);
    box.appendChild(el("div", "dss-saveresult-detail",
      "The model suggests these. Check them — this is the one choice nothing " +
      "downstream can verify: a query over the wrong table returns real " +
      "numbers about the wrong thing."));
    var input = el("input", "dss-input");
    input.type = "text";
    input.setAttribute("aria-label", "DocTypes to build the query over");
    input.value = this.state.tables || "";
    input.addEventListener("input", function () { self.state.tables = input.value; });
    box.appendChild(input);

    var actions = el("div", "dss-insights-links");
    // `confirming` stays TRUE while this runs, so the confirm box — and this
    // button, spinning — stay on screen. Clearing it first removed the only
    // thing on the page that could show anything was happening.
    // The busy label is computed at render time so a retry is VISIBLE: each
    // retry sets `state.retrying` and re-renders, and this button is the one
    // thing on screen saying what the wait is for (ADR-028).
    var buildBusyLabel = this.state.retrying
      ? "Refused — correcting the SQL (attempt "
        + (this.state.retrying + 1) + " of " + (PROPOSE_RETRIES + 1) + ")…"
      : "Building the query…";
    var build = actionButton(this, "build", "Build the query",
                             buildBusyLabel, function () {
      begin(self, "build");
      var done = function () {
        finish(self);
        self.state.confirming = false;
        self.render();
      };
      self.propose((self.state.question || "").trim()).then(done, done);
    });
    actions.appendChild(build);
    var cancel = el("button", "dss-btn", "Cancel");
    cancel.type = "button";
    cancel.addEventListener("click", function () {
      self.state.confirming = false;
      self.render();
    });
    actions.appendChild(cancel);
    box.appendChild(actions);
    return box;
  };

  // How many CORRECTED attempts follow a refused one. Bounded and small: each
  // retry is a full round through the same validation, so the only cost of a
  // hopeless retry is tokens — and the only cost of stopping is the person
  // rewording the question themselves, which is where this started.
  var PROPOSE_RETRIES = 2;

  App.prototype.propose = function (question, attempt, correction) {
    var self = this;
    attempt = attempt || 0;
    var args = { question: question, doctypes: this.state.tables || "",
                 // Sent with this request and used for this request. The server
                 // passes it to the outbound call and lets it go out of scope.
                 api_key: this.state.apiKey || null,
                 model: this.state.model || null };
    if (correction) {
      // The refusal goes back to the model in the converter's own words — the
      // reply passes through the same validation as any first attempt.
      args.previous_sql = correction.sql;
      args.refusal = (correction.reasons || []).join("\n");
    }
    return dsCall({
      method: "dashboard_studio.api.propose.propose_from_question",
      args: args,
    }).then(function (r) {
      var proposal = r.message || null;
      // Retry only a refusal OUR validator produced over SQL the model wrote
      // (`sql` present — a CANNOT or an empty reply has nothing to correct),
      // only for reasons a rewrite can fix, and only within the budget.
      if (proposal && !proposal.supported && proposal.sql
          && attempt < PROPOSE_RETRIES
          && core.retryableRefusal(proposal.reasons)) {
        self.state.retrying = attempt + 1;
        self.render();
        return self.propose(question, attempt + 1,
                            { sql: proposal.sql, reasons: proposal.reasons });
      }
      // Exhausted retries show the LAST refusal: this response replaces
      // everything, and it is the one the model could not get past.
      self.state.retrying = 0;
      self.state.notice = "";
      self.state.proposal = proposal;
      self.state.conversion = null;
      self.render();
    }).catch(function (err) {
      self.state.retrying = 0;
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
    var create = actionButton(this, "create", "Create in Insights",
                              "Creating it in Insights…", function () {
      begin(self, "create");
      var done = function () { finish(self); self.render(); };
      self.convertSql(proposal.sql).then(done, done);
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

  // Always reports through state, so there is exactly one place a result can
  // appear. The refusal TEXT is the server's own, unchanged — only where it
  // renders has moved.
  // Ask the server which exported reports match. Read-only; it returns names,
  // never file contents.
  App.prototype.searchExports = function (text, paint) {
    var self = this;
    if (!hasFrappe()) {
      this.state.exports = { available: false,
        problem: "Listing the exports needs the server." };
      paint();
      return;
    }
    this.state.exportsLoading = true;
    return dsCall({
      method: "dashboard_studio.api.exports.list_exported_reports",
      args: { search: text || "" },
    }).then(function (r) {
      self.state.exportsLoading = false;
      self.state.exports = r.message || { available: false,
        problem: "The server returned no export list." };
      paint();
    }).catch(function (err) {
      self.state.exportsLoading = false;
      // The server's own sentence — a missing folder or an unset config key
      // says which, and that is the whole point of showing it here.
      self.state.exports = { available: false,
        problem: core.refusalMessage(err, "The exports could not be listed.") };
      paint();
    });
  };

  // One chosen report -> the SQL in the box and its sidecar in state. The same
  // pairing the file picker did, except the pairing happened on the server,
  // where both files actually are.
  App.prototype.loadExport = function (stem) {
    var self = this;
    return dsCall({
      method: "dashboard_studio.api.exports.read_exported_report",
      args: { stem: stem },
    }).then(function (r) {
      var got = r.message || {};
      self.state.vizSql = got.sql || "";
      self.state.vizCard = got.card || null;
      self.state.vizCardName = got.sidecar || "";
      self.state.vizTitle = self.state.vizTitle || got.report || "";
      // An unreadable sidecar is not a chart to guess at, and saying so beats
      // a chart silently left at the default.
      self.state.notice = got.card_problem || "";
      self.state.proposal = null;
      self.state.conversion = null;
      self.render();
    }).catch(function (err) {
      self.state.notice = core.refusalMessage(err, "That report could not be read.");
      self.render();
    });
  };

  App.prototype.convertSql = function (sql) {
    var self = this;
    return dsCall({
      method: "dashboard_studio.api.convert.convert_sql",
      args: { sql: sql, title: (this.state.vizTitle || "").trim() || null,
              workbook: this.state.vizWorkbook || null,
              // The sidecar loaded beside this exact .sql, or nothing at all.
              card: this.state.vizCard ? JSON.stringify(this.state.vizCard) : null },
    }).then(function (r) {
      var made = r.message;
      if (!made || !made.name) {
        self.state.notice = "The server reported no query. Nothing was created.";
        self.render();
        return null;
      }
      self.state.notice = "";
      self.state.proposal = null;
      self.state.conversion = made;
      self.render();
      return made;
    }).catch(function (err) {
      self.state.notice = core.refusalMessage(err, "Could not convert that query.");
      self.render();
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
    // `self`, declared. Without it the regroup handler below reached
    // `window.self` — a real object, so no ReferenceError, just
    // "Cannot set properties of undefined". Found by clicking the button.
    var self = this;
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

    // Multiple measures — a prompt to check the chart display, not a claim
    // that a combo was detected. See `chartDisplayNote` for why the converter
    // cannot know that.
    var display = core.chartDisplayNote(made.operations);
    if (display) box.appendChild(el("div", "dss-validation is-warn", display));

    // Grouped by a date NUMBER, so the query is right and the chart cannot be
    // drawn. The one-click fix removes the retyping, NOT the decision: it only
    // fires on a click, after the person has read why, and its result goes back
    // through the whole converter like any other conversion. Month-of-year is a
    // genuinely different question from a year-over-year trend, so nothing here
    // decides which one was meant.
    var part = core.datePartGrouping(made.operations);
    if (part && made.sql) {
      var warn = el("div", "dss-validation is-warn");
      warn.appendChild(el("div", "dss-validation-line",
        "Grouped by " + part.part + "-of-" + (part.part === "day" ? "month" : "year") +
        " (" + part.column + "), which is a number — Insights can only put a " +
        "date on a chart's X axis, so this converted correctly but cannot be " +
        "charted as it stands."));
      if (part.entangled) {
        // NO button. The substitution rewrites every MONTH( in the SQL, and
        // this query also feeds the part into a label expression — a
        // `case(month(d) == 1, '01-Jan', …)` regrouped to year compares 2024
        // against 1..12 and labels every row NULL. A chart that renders with
        // empty labels and no error is exactly the class this project refuses,
        // so a substitution that cannot be applied whole is not offered.
        warn.appendChild(el("div", "dss-hint",
          "No one-click fix here: this report also computes labels from " +
          part.part.toUpperCase() + "(" + part.column + "), and regrouping " +
          "by year would turn those labels into nothing. If a year trend is " +
          "what you want, edit the SQL by hand — the labels need rewriting " +
          "too, and only you know what they should become."));
      } else {
        warn.appendChild(actionButton(this, "regroup", "Try grouping by year instead",
                                      "Rebuilding by year…", function () {
          var retry = core.regroupByYear(made.sql, part.part);
          self.state.vizSql = retry;
          self.state.conversion = null;
          self.state.notice = "";
          begin(self, "regroup");
          var done = function () { finish(self); self.render(); };
          self.convertSql(retry).then(done, done);
        }));
        warn.appendChild(el("div", "dss-hint",
          "Substitutes " + part.part.toUpperCase() + "( for YEAR( and converts " +
          "again. If " + part.part + "-of-" +
          (part.part === "day" ? "month" : "year") +
          " was the question you meant, ignore this — " +
          "it is a different question, not a mistake."));
      }
      box.appendChild(warn);
    }

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
