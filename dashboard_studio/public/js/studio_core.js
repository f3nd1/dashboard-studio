/*
 * Pure logic for the Metabase → Insights converter. No DOM, no Frappe, no
 * dependencies, so it runs in the browser AND under Node (see
 * studio_core.test.js).
 *
 * What is left of a much larger module — grid maths, chart-type rules, filter
 * validation, mapping nodes and the rest went to archive/studio_core_full.js
 * with the workspaces they served.
 */
(function (root) {
  "use strict";

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
    if (op.type === "cast") {
      return "cast " + ((op.column || {}).column_name || "?") + " to " +
        (op.data_type || "?");
    }
    if (op.type === "mutate") {
      // A month-of-year, quarter-of-year or day-of-month value is a NUMBER, and
      // Insights' chart X axis only offers date-compatible columns — so this
      // grouping is correct and cannot be charted. Said out loud here so nobody
      // reads an unchartable result as a converter fault. A YEAR grouping does
      // not appear as a mutate at all: it is the date column with a
      // granularity, which stays chartable.
      //
      // Otherwise the expression is a plain text math string over the measure
      // names the summarize just defined, so it reads back as itself.
      var text = (op.expression || {}).expression || "?";
      return (op.new_name || "?") + " = " + text +
        (/^(month|quarter|day)\(/.test(text)
          ? " — a number, not a date, so it cannot be a chart's X axis in Insights"
          : "");
    }
    if (op.type === "summarize") {
      var by = (op.dimensions || []).map(function (d) { return d.column_name; });
      return (op.measures || []).map(function (m) {
        // coerced_from is set when the SQL cast a non-numeric column to a
        // number to aggregate it (Metabase's `col * 1`). Said out loud because
        // nothing else shows that the source field is text, and every row that
        // is not a number casts to 0 and is averaged in as zero.
        return m.aggregation + "(" + m.column_name + ")" +
          (m.coerced_from ? " — " + m.coerced_from + " cast to a number" : "");
      }).join(", ") + (by.length ? " by " + by.join(", ") : "");
    }
    if (op.type === "filter_group") {
      var joiner = " " + String(op.logical_operator || "Or").toLowerCase() + " ";
      return (op.filters || []).map(function (f) {
        return ((f.column || {}).column_name || "?") + " " + (f.operator || "?") +
          " " + JSON.stringify(f.value);
      }).join(joiner);
    }
    if (op.type === "order_by") {
      return ((op.column || {}).column_name || "?") + ", " +
        (op.direction === "desc" ? "highest first" : "lowest first");
    }
    if (op.type === "limit") return "first " + op.limit + " rows";
    return op.type || "";
  }

  // Is this query's X axis a date NUMBER rather than a date?
  //
  // Mirrors `chart_config.date_part_grouping` on the server, which the corpus
  // scan uses. `year` is absent on purpose: ADR-024 emits it as a granularity
  // on the date column, which stays chartable, so it never becomes a mutate.
  var UNCHARTABLE_PARTS = ["month", "quarter", "day"];

  function datePartGrouping(operations) {
    operations = operations || [];
    var grouped = {};
    operations.forEach(function (op) {
      if (op && op.type === "summarize") {
        (op.dimensions || []).forEach(function (d) { grouped[d.column_name] = true; });
      }
    });
    for (var i = 0; i < operations.length; i++) {
      var op = operations[i] || {};
      if (op.type !== "mutate" || !grouped[op.new_name]) continue;
      var text = (op.expression || {}).expression || "";
      for (var j = 0; j < UNCHARTABLE_PARTS.length; j++) {
        var part = UNCHARTABLE_PARTS[j];
        if (text.indexOf(part + "(") === 0) {
          return { part: part, dimension: op.new_name,
                   column: text.slice(part.length + 1).replace(/\)+$/, "").trim(),
                   entangled: datePartEntangled(operations, part) };
        }
      }
    }
    return null;
  }

  // Does anything BESIDES a bare `part(col)` grouping consume this date part?
  //
  // The regroup substitution rewrites every `MONTH(` in the SQL, and stepping
  // over quoted literals is not enough when the part feeds a label expression:
  // a `case(month(d) == 1, '01-Jan', ...)` regrouped to year compares 2024
  // against 1..12 and labels every row NULL — correct-looking chart, wrong
  // everything, no error. Found live. So a part that appears inside any
  // expression larger than the bare call marks the whole query entangled, and
  // the one-click regroup is not offered at all: a substitution that cannot be
  // applied whole is not applied.
  function datePartEntangled(operations, part) {
    var pure = new RegExp("^" + part + "\\(\\w+\\)$");
    for (var i = 0; i < (operations || []).length; i++) {
      var op = operations[i] || {};
      if (op.type !== "mutate") continue;
      var text = (op.expression || {}).expression || "";
      if (text.indexOf(part + "(") !== -1 && !pure.test(text)) return true;
    }
    return false;
  }

  // `MONTH(` -> `YEAR(`, everywhere it appears OUTSIDE a string literal.
  //
  // Same three places every time this pattern occurs — the SELECT list, the
  // GROUP BY and the ORDER BY — so a plain textual substitution is the whole
  // job. Quoted literals are stepped over rather than rewritten: a
  // `WHERE label = 'MONTH(x)'` would otherwise be edited into a filter for a
  // value nobody typed, and that converts cleanly and returns different rows,
  // which is the one failure this project will not ship. Backtick-quoted
  // identifiers are stepped over for the same reason.
  //
  // The result is NOT applied silently — it goes back through the whole
  // converter and is shown like any other conversion.
  function regroupByYear(sql, part) {
    sql = String(sql || "");
    var want = String(part || "month").toUpperCase();
    var out = "", quote = null, i = 0;
    while (i < sql.length) {
      var ch = sql.charAt(i);
      if (quote) {
        // A doubled quote inside a literal is an escaped one, not the end.
        if (ch === quote && sql.charAt(i + 1) === quote) { out += ch + ch; i += 2; continue; }
        if (ch === "\\" && quote !== "`") { out += ch + sql.charAt(i + 1); i += 2; continue; }
        if (ch === quote) quote = null;
        out += ch; i += 1; continue;
      }
      if (ch === "'" || ch === '"' || ch === "`") { quote = ch; out += ch; i += 1; continue; }
      var ahead = sql.slice(i);
      var match = new RegExp("^" + want + "(\\s*\\()", "i").exec(ahead);
      // A word boundary before it, so `DAYCOUNT(` and `x.DAY(` are left alone.
      var before = i ? sql.charAt(i - 1) : " ";
      if (match && !/[\w.]/.test(before)) {
        out += "YEAR" + match[1]; i += match[0].length; continue;
      }
      out += ch; i += 1;
    }
    return out;
  }

  // The plain label beside each operation. The user reads these to judge
  // whether the proposal understood the question, so they say what the step
  // DOES rather than naming Insights' internals.
  var LABELS = {
    source: "Source", join: "Join", filter: "Filter", filter_group: "Filter",
    cast: "Convert", mutate: "Calculate", summarize: "Summarise",
    order_by: "Sort", limit: "Limit",
  };

  function labelForOperation(op) {
    return LABELS[(op || {}).type] || (op || {}).type || "";
  }

  // ONE sentence describing what the query will do, composed HERE from the
  // operations that will actually run.
  //
  // This is the safety argument for the question box, so read the next bit
  // before changing it. The server never returns the model's own words. If the
  // model wrote this sentence, it would describe what it MEANT while the
  // operations did something else, and a person reading it would be checking
  // the model's intention rather than the query — which is no check at all.
  // Composed from the operations, a mismatch between the question asked and the
  // query built is visible in the one line somebody actually reads.
  function describeProposal(operations) {
    operations = operations || [];
    var find = function (type) {
      for (var i = 0; i < operations.length; i++) {
        if (operations[i].type === type) return operations[i];
      }
      return null;
    };
    var summarize = find("summarize");
    if (!summarize) return "";
    var measures = (summarize.measures || []).map(function (m) {
      return m.aggregation ? m.aggregation + " of " + m.column_name : m.measure_name;
    });
    var by = (summarize.dimensions || []).map(function (d) { return d.column_name; });
    var sentence = measures.join(" and ") || "a count";
    if (by.length) sentence += " for each " + by.join(" and ");
    var source = find("source");
    if (source) sentence += ", from " + ((source.table || {}).table_name || "?");
    var filters = operations.filter(function (op) {
      return op.type === "filter" || op.type === "filter_group";
    });
    if (filters.length) {
      sentence += ", where " + filters.map(describeOperation).join(" and ");
    }
    var order = find("order_by");
    if (order) {
      sentence += ", " + (order.direction === "desc" ? "highest" : "lowest") +
        " " + ((order.column || {}).column_name || "?") + " first";
    }
    var limit = find("limit");
    if (limit) sentence += ", top " + limit.limit;
    return sentence;
  }

  // Numeric measure result types — the same two `sql_ops.MEASURE_DATA_TYPES`
  // holds. A `count` is Integer, everything else that survives is Decimal or
  // the column's own numeric type.
  var NUMERIC = ["Integer", "Decimal"];

  // "Does this report probably want a bar+line combo?" — a PROMPT, never a
  // verdict.
  //
  // Read the investigation notes before making this say more than it does.
  // Metabase stores per-series display types only when somebody overrode them;
  // a genuine combo can store nothing at all, and for a `display: "combo"` card
  // the split is computed from array POSITION (line first, bar second) rather
  // than saved. So the converter has no reliable signal that a combo was
  // intended, and nothing here may claim one was detected — that would be a
  // guess wearing a finding's clothes.
  //
  // What IS knowable is the shape most likely to want one: more than one
  // numeric measure sharing an X axis. That is a reason for a person to look,
  // and it is phrased as exactly that.
  function chartDisplayNote(operations) {
    var measures = [];
    (operations || []).forEach(function (op) {
      if (op && op.type === "summarize") {
        (op.measures || []).forEach(function (m) {
          if (m && NUMERIC.indexOf(m.data_type) !== -1) measures.push(m);
        });
      }
    });
    if (measures.length < 2) return "";
    return "This report has multiple measures — check whether it needs a " +
      "bar+line combo chart. Insights defaults every series to Bar on the " +
      "left axis, and the chart display could not be determined automatically.";
  }

  // What the user is told when the server refuses.
  //
  // Frappe puts a thrown message in one of SEVERAL places, and which one depends
  // on the site's settings and API version — response.py sets `_server_messages`
  // only `if frappe.local.message_log`, and `exc` only `if
  // is_traceback_allowed()`. Reading two of them and falling back to a generic
  // string is how "aggregation '*' is a compound or custom expression" became
  // "Could not convert that card.", which defeats the entire point of writing
  // specific refusals.
  //
  // So this tries every shape, most faithful first, and only gives up when the
  // payload genuinely carries no sentence.
  function refusalMessage(err, fallback) {
    var sources = [];
    var body = (err && (err.responseJSON || err.response)) || {};
    function push(value) { if (value) sources.push(value); }

    push(err && err.message);
    push(err && err._server_messages);
    push(body._server_messages);
    push(err && err._error_message);
    push(body._error_message);
    // API v2: {errors: [{type, exception}]}
    var errors = body.errors || (err && err.errors);
    if (errors && errors.length) {
      push(errors[0].exception);
      push(errors[0].message);
    }
    push(err && err.exception);
    push(body.exception);
    push(err && err.exc);
    push(body.exc);

    for (var i = 0; i < sources.length; i++) {
      var text = readOne(sources[i]);
      if (text) return text;
    }
    return fallback;
  }

  // One candidate -> a sentence, or "" if it holds none.
  function readOne(raw) {
    if (typeof raw !== "string") return "";
    raw = raw.trim();
    if (!raw) return "";

    // _server_messages / exc: a JSON array of JSON strings, or of tracebacks.
    if (raw.charAt(0) === "[") {
      var parsed;
      try { parsed = JSON.parse(raw); } catch (e) { return clean(raw); }
      if (!parsed || !parsed.length) return "";
      for (var i = 0; i < parsed.length; i++) {
        var entry = parsed[i];
        if (typeof entry === "string") {
          try { entry = JSON.parse(entry); } catch (e) { /* a raw traceback */ }
        }
        var text = typeof entry === "string" ? lastLine(entry)
          : clean(entry && (entry.message || entry.title));
        if (text) return text;
      }
      return "";
    }
    // "frappe.exceptions.ValidationError: the actual sentence"
    return lastLine(raw);
  }

  // A traceback's final line is the one carrying the message; the class prefix
  // in front of it ("frappe.exceptions.ValidationError: ") is noise to a reader.
  function lastLine(text) {
    var lines = String(text).split("\n");
    for (var i = lines.length - 1; i >= 0; i--) {
      var line = clean(lines[i]);
      if (!line) continue;
      var match = /^[\w.]*(?:Error|Exception)\s*:\s*(.+)$/.exec(line);
      return match ? match[1].trim() : line;
    }
    return "";
  }

  function clean(text) {
    if (typeof text !== "string") return "";
    return text.replace(/<[^>]*>/g, "").trim();
  }

  root.DSStudioCore = { describeOperation: describeOperation,
    labelForOperation: labelForOperation, describeProposal: describeProposal,
    chartDisplayNote: chartDisplayNote, datePartGrouping: datePartGrouping,
    regroupByYear: regroupByYear, refusalMessage: refusalMessage };
  if (typeof module !== "undefined" && module.exports) module.exports = root.DSStudioCore;
})(typeof window !== "undefined" ? window : this);
