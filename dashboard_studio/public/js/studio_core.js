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
    if (op.type === "summarize") {
      var by = (op.dimensions || []).map(function (d) { return d.column_name; });
      return (op.measures || []).map(function (m) {
        return m.aggregation + "(" + m.column_name + ")";
      }).join(", ") + (by.length ? " by " + by.join(", ") : "");
    }
    return op.type || "";
  }

  root.DSStudioCore = { describeOperation: describeOperation };
  if (typeof module !== "undefined" && module.exports) module.exports = root.DSStudioCore;
})(typeof window !== "undefined" ? window : this);
