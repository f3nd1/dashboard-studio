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
    return op.type || "";
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
    refusalMessage: refusalMessage };
  if (typeof module !== "undefined" && module.exports) module.exports = root.DSStudioCore;
})(typeof window !== "undefined" ? window : this);
