/*
 * Metabase → Insights converter — the whole front end.
 *
 * What is left of a much larger SPA. The dashboard builder, source mapping,
 * catalogue, validation and governance workspaces went to
 * archive/studio_app_full.js when the product narrowed to one job: turn a
 * GUI-built Metabase card into an Insights Query Builder query.
 *
 * The converter code below is lifted from that file unchanged. This was a move,
 * not a rewrite — the flow and its verification gate are the thing that works,
 * and the point of the cut was to stop carrying everything around it.
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
    hero.appendChild(el("h3", "dss-hero-title", "Rebuild a Metabase question in Insights"));
    hero.appendChild(el("p", "dss-hero-blurb",
      "Give it a Metabase card id, or paste SQL, and it writes the same question " +
      "into Insights as clickable operations rather than a block of text. " +
      "Nothing is trusted until you have compared its number against the " +
      "original. Pasted SQL covers a single table with WHERE and GROUP BY; " +
      "joins and subqueries are refused rather than guessed at."));
    wrap.appendChild(hero);

    var card = el("section", "dss-vizstep");
    var body = el("div", "dss-vizstep-body");
    body.appendChild(this.buildMetabaseImport());
    body.appendChild(this.buildWorkbookPicker());
    var result = this.buildConversionResult();
    if (result) body.appendChild(result);
    card.appendChild(body);
    wrap.appendChild(card);

    this.mount.appendChild(wrap);
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

  // One editable field with its Guessed/Confirmed marker.
  //
  // The marker is flipped IN PLACE on input rather than by re-rendering: a
  // re-render on every keystroke replaces the input mid-type and the caret and
  // the rest of the word go with it. That fault has already been fixed twice in
  // this app; do not reintroduce it here.

  // Read a Metabase card instead of copying its SQL out by hand.
  //
  // The card already knows its title, its chart type and its axes; guessing
  // those back out of pasted SQL text is where every bug in this flow has come
  // from. Read-only — one GET, and Metabase is never written to.
  // The card to convert. One input, one button — this is the whole front door.
  App.prototype.buildMetabaseImport = function () {
    var self = this;
    var wrap = el("div", "dss-vizimport");
    var row = el("div", "dss-vizimport-row");
    var input = el("input", "dss-input dss-vizcardid");
    input.type = "number";
    input.min = "1";
    input.placeholder = "Metabase card id, e.g. 1474";
    input.setAttribute("aria-label", "Metabase card id");
    input.value = this.state.vizCardId || "";
    input.addEventListener("input", function () { self.state.vizCardId = input.value; });
    var convert = el("button", "dss-btn dss-btn-primary", "Convert card →");
    convert.title = "Turns a drag-and-drop Metabase question into Insights " +
      "operations. The result is marked unverified until you check its number.";
    row.appendChild(input);
    row.appendChild(convert);
    wrap.appendChild(row);

    var note = el("div", "dss-vizimport-note",
      "Read-only: the card is read, nothing is ever written to Metabase.");
    wrap.appendChild(note);

    // The other way in: SQL somebody already has, with no card behind it. Same
    // destination and the same gate — it produces operations, not a raw SQL
    // query, so the result stays clickable in Insights either way.
    wrap.appendChild(el("div", "dss-vizimport-or", "or paste the SQL"));
    var box = el("textarea", "dss-input dss-sqlbox");
    box.placeholder =
      "SELECT `academic_year`, COUNT(*) FROM `tabStudent Applicant` GROUP BY `academic_year`";
    box.setAttribute("aria-label", "SQL to convert");
    box.value = this.state.vizSql || "";
    box.addEventListener("input", function () { self.state.vizSql = box.value; });
    wrap.appendChild(box);

    var sqlRow = el("div", "dss-vizimport-row");
    var sqlGo = el("button", "dss-btn", "Convert SQL →");
    sqlGo.title = "Parses the query into the same Insights operations a card " +
      "converts to. Single table with WHERE and GROUP BY; joins are refused.";
    sqlRow.appendChild(sqlGo);
    wrap.appendChild(sqlRow);

    sqlGo.addEventListener("click", function () {
      var sql = (box.value || "").trim();
      if (!sql) { note.textContent = "Paste a query first."; return; }
      if (!hasFrappe()) { note.textContent = "Converting needs the server."; return; }
      note.textContent = "Translating that query…";
      sqlGo.disabled = true;
      var done = function () { sqlGo.disabled = false; };
      self.convertSql(sql, note).then(done, done);
    });

    convert.addEventListener("click", function () {
      var id = (input.value || "").trim();
      if (!id) { note.textContent = "Enter the card's id first."; return; }
      if (!hasFrappe()) {
        note.textContent = "Converting needs the server.";
        return;
      }
      note.textContent = "Translating card " + id + "…";
      convert.disabled = true;
      var done = function () { convert.disabled = false; };
      self.convertMetabaseCard(id, note).then(done, done);
    });
    return wrap;
  };

  App.prototype.convertMetabaseCard = function (cardId, note) {
    var self = this;
    return dsCall({
      method: "dashboard_studio.api.convert.convert_metabase_card",
      args: { card_id: cardId, workbook: this.state.vizWorkbook || null },
    }).then(function (r) {
      var made = r.message;
      if (!made || !made.name) {
        note.textContent = "The server reported no query. Nothing was created.";
        return null;
      }
      self.state.conversion = made;
      self.state.vizError = "";
      self.render();
      return made;
    }).catch(function (err) {
      note.textContent = core.refusalMessage(err, "Could not convert that card.");
    });
  };

  // A converted query, and the check that has to happen before anyone trusts it.
  //
  // Deliberately not styled as a success. A conversion that LOOKS done is the
  // failure this whole gate exists to prevent: the translation may be right,
  // and nothing here can tell — only a person comparing the two numbers can.
  // Same flow as convertMetabaseCard, different source. Kept as its own method
  // rather than a flag on that one: they take different arguments and refuse for
  // different reasons, and a shared function with a mode is how those messages
  // end up generic.
  App.prototype.convertSql = function (sql, note) {
    var self = this;
    return dsCall({
      method: "dashboard_studio.api.convert.convert_sql",
      args: { sql: sql, workbook: this.state.vizWorkbook || null },
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
      ? "“" + made.title + "”. You confirmed its number matches Metabase card "
        + made.card_id + "."
      : "“" + made.title + "”, built as Insights operations from Metabase card "
        + made.card_id + ". Studio translated this; nothing has checked that it "
        + "counts the same rows. Run it in Insights, compare the number with the "
        + "card, and record both below."));

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

    var check = el("div", "dss-verify");
    check.appendChild(el("div", "dss-verify-head", "Check the number before trusting this"));
    var pair = el("div", "dss-verify-pair");
    var inputs = {};
    [["metabase", "Number in Metabase"], ["insights", "Number in Insights"]]
      .forEach(function (spec) {
        var field = el("div", "dss-field");
        field.appendChild(el("label", "dss-field-label", spec[1]));
        var box2 = el("input", "dss-input");
        box2.setAttribute("aria-label", spec[1]);
        box2.value = (self.state.verifyValues || {})[spec[0]] || "";
        box2.addEventListener("input", function () {
          var values = self.state.verifyValues || (self.state.verifyValues = {});
          values[spec[0]] = box2.value;
        });
        inputs[spec[0]] = box2;
        field.appendChild(box2);
        pair.appendChild(field);
      });
    check.appendChild(pair);

    var mark = el("button", "dss-btn dss-btn-primary", "They match — mark verified");
    mark.addEventListener("click", function () {
      self.verifyConversion(made.name, inputs.metabase.value, inputs.insights.value);
    });
    check.appendChild(mark);
    if (this.state.verifyError) {
      check.appendChild(el("div", "dss-sqlnote dss-vizerror", this.state.verifyError));
    }
    box.appendChild(check);
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
