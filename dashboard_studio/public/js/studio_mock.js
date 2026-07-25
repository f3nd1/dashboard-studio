/*
 * Dashboard Studio — MOCK data for the visual editor.
 *
 * ⚠️  THIS IS MOCK / FIXTURE DATA, NOT REAL RECORDS.
 * Used only when the editor cannot reach a live Frappe backend (e.g. no site
 * connection, or the DS Dashboard/DS Chart records don't exist yet). Every value
 * here is invented for UI development. Nothing here is a real UCC dashboard.
 */
(function (root) {
  "use strict";

  var MOCK_DASHBOARD = {
    __mock__: true,
    name: "Admission Overview (MOCK)",
    dashboard_title: "Admission Overview (MOCK)",
    status: "Draft",
    charts: [
      {
        name: "chart-mock-1", chart_title: "Total Applicants",
        chart_type: "KPI Card", metric: "Total Applicants (MOCK)",
        source_doctype: "Student Applicant",
        pos_x: 0, pos_y: 0, width: 3, height: 2, description: "",
      },
      {
        name: "chart-mock-2", chart_title: "Applicants by Year",
        chart_type: "Line Chart", metric: "Applicants by Year (MOCK)",
        source_doctype: "Student Applicant",
        pos_x: 3, pos_y: 0, width: 6, height: 4, description: "",
        // One editable Static filter + one Dynamic row that the editor must
        // show read-only ("not yet supported") and preserve on save.
        chart_filters: [
          { fieldname: "application_status", operator: "=", value: "Admitted", filter_type: "Static" },
          { fieldname: "intake", operator: "=", value: "{{session_intake}}", filter_type: "Dynamic" },
        ],
      },
      {
        name: "chart-mock-3", chart_title: "Applicants by Programme",
        chart_type: "Bar Chart", metric: "Applicants by Programme (MOCK)",
        source_doctype: "Student Applicant",
        pos_x: 0, pos_y: 2, width: 3, height: 3, description: "",
      },
    ],
  };

  // ⚠️ MOCK metric results — invented numbers, keyed by the mock metric names
  // above. Shape matches run_ds_metric's real output: [{<dimension>: v, count: n}].
  var MOCK_METRIC_RESULTS = {
    "Total Applicants (MOCK)": [
      { academic_year: "2022", count: 2 },
      { academic_year: "2023", count: 3 },
      { academic_year: "2024", count: 1 },
    ],
    "Applicants by Year (MOCK)": [
      { academic_year: "2022", count: 2 },
      { academic_year: "2023", count: 3 },
      { academic_year: "2024", count: 1 },
    ],
    "Applicants by Programme (MOCK)": [
      { program: "Business (MOCK)", count: 3 },
      { program: "Computing (MOCK)", count: 2 },
      { program: "Design (MOCK)", count: 1 },
    ],
  };

  // ⚠️ MOCK Metabase analysis — shaped exactly like analyze_sql's real output,
  // values invented. Feeds the Mapping view when no live import exists.
  var MOCK_ANALYSIS = {
    __mock__: true,
    supported: true,
    reasons: [],
    doctypes: ["Student Applicant", "Student Admission UCC"],
    aggregations: [{ function: "COUNT", argument: "*" }],
    filters: [{ field: "application_status", operator: "=", value: "Admitted" }],
    group_by: ["academic_year"],
    join: { doctype: "Student Admission UCC", on: "`tabStudent Applicant`.`name` = `tabStudent Admission UCC`.`applicant`" },
  };

  // ⚠️ MOCK candidate target DocTypes (live version would query real DocTypes).
  var MOCK_TARGET_DOCTYPES = ["Student Applicant", "Student Admission UCC", "Program (MOCK)"];

  // ⚠️ MOCK catalogue — record counts are invented. The relationship edges
  // mirror the real DS schema (the live endpoint derives them from the shipped
  // DocType files), so the shape shown here matches production.
  var MOCK_CATALOGUE = {
    __mock__: true,
    doctypes: [
      { doctype: "DS Dashboard", count: 2, recent: ["Admission Overview (MOCK)"],
        statuses: { Published: 1, Draft: 1 } },
      { doctype: "DS Dashboard Section", count: 3, recent: ["Intake (MOCK)"], statuses: {} },
      { doctype: "DS Chart", count: 9, recent: ["Applicants by Year (MOCK)"], statuses: {} },
      { doctype: "DS Metric", count: 3, recent: ["Applicants by Year (MOCK)"],
        statuses: { Approved: 2, Draft: 1 } },
      { doctype: "DS Data Source", count: 1, recent: ["Metabase (MOCK)"], statuses: {} },
      { doctype: "DS Data Mapping", count: 2, recent: [], statuses: {} },
      { doctype: "DS Migration Project", count: 1, recent: ["Admissions (MOCK)"],
        statuses: { Mapping: 1 } },
      { doctype: "DS Validation Comparison", count: 3, recent: [],
        statuses: { Match: 1, Discrepancy: 1, Flagged: 1 } },
    ],
    relationships: [
      { source: "DS Chart", target: "DS Dashboard", fieldname: "dashboard", kind: "link" },
      { source: "DS Chart", target: "DS Dashboard Section", fieldname: "section", kind: "link" },
      { source: "DS Chart", target: "DS Metric", fieldname: "metric", kind: "link" },
      { source: "DS Chart", target: "DS Chart Filter", fieldname: "chart_filters", kind: "child" },
      { source: "DS Dashboard Section", target: "DS Dashboard", fieldname: "dashboard", kind: "link" },
      { source: "DS Metric", target: "DS Metric", fieldname: "numerator_metric", kind: "link",
        self_reference: true },
      { source: "DS Metric", target: "DS Metric Filter", fieldname: "metric_filters", kind: "child" },
      { source: "DS Data Mapping", target: "DS Data Source", fieldname: "data_source", kind: "link" },
      { source: "DS Migration Project", target: "DS Data Source", fieldname: "data_source", kind: "link" },
      { source: "DS Migration Project", target: "DS Canvas Node", fieldname: "canvas_nodes", kind: "child" },
      { source: "DS Validation Comparison", target: "DS Chart", fieldname: "chart", kind: "link" },
    ],
  };

  // ⚠️ MOCK field catalogue — the allowlist concept is real; these values are not.
  var MOCK_FIELD_CATALOGUE = [
    { metric: "M1", metric_name: "Applicants by Year (MOCK)", status: "Approved",
      source_doctype: "Student Applicant", fields: ["academic_year", "application_status"],
      executable: true },
    { metric: "M2", metric_name: "By Nationality (MOCK)", status: "Approved",
      source_doctype: "Student Applicant", fields: ["nationality"], executable: true },
    { metric: "M3", metric_name: "Unconfigured metric (MOCK)", status: "Draft",
      source_doctype: "Student Applicant", fields: [], executable: false },
  ];

  // ⚠️ MOCK comparisons — shaped exactly like DS Validation Comparison records.
  var MOCK_COMPARISONS = [
    { name: "V1", chart: "Applicants by Year (MOCK)", comparison_date: "2026-07-25",
      original_value: "62", new_value: "62", difference_pct: 0, status: "Match",
      accepted_reason: "", reviewed_by: "" },
    { name: "V2", chart: "Applicants by Programme (MOCK)", comparison_date: "2026-07-25",
      original_value: "60", new_value: "57", difference_pct: -5, status: "Discrepancy",
      accepted_reason: "", reviewed_by: "" },
    { name: "V3", chart: "Admission Funnel (MOCK)", comparison_date: "2026-07-25",
      original_value: "21", new_value: "", difference_pct: null, status: "Flagged",
      accepted_reason: "", reviewed_by: "" },
    { name: "V4", chart: "Nationality Spread (MOCK)", comparison_date: "2026-07-24",
      original_value: "9", new_value: "8", difference_pct: -11.1, status: "Accepted",
      accepted_reason: "Legacy counted withdrawn applicants (MOCK)",
      reviewed_by: "reviewer@example.invalid" },
  ];

  var api = {
    MOCK_DASHBOARD: MOCK_DASHBOARD,
    MOCK_CATALOGUE: MOCK_CATALOGUE,
    MOCK_FIELD_CATALOGUE: MOCK_FIELD_CATALOGUE,
    MOCK_COMPARISONS: MOCK_COMPARISONS,
    MOCK_METRIC_RESULTS: MOCK_METRIC_RESULTS,
    MOCK_ANALYSIS: MOCK_ANALYSIS,
    MOCK_TARGET_DOCTYPES: MOCK_TARGET_DOCTYPES,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.DSStudioMock = api;
})(typeof window !== "undefined" ? window : globalThis);
