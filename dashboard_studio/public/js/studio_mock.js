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
      },
      {
        name: "chart-mock-3", chart_title: "Applicants by Programme",
        chart_type: "Bar Chart", metric: "Applicants by Programme (MOCK)",
        source_doctype: "Student Applicant",
        pos_x: 0, pos_y: 2, width: 3, height: 3, description: "",
      },
    ],
  };

  var api = { MOCK_DASHBOARD: MOCK_DASHBOARD };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.DSStudioMock = api;
})(typeof window !== "undefined" ? window : globalThis);
