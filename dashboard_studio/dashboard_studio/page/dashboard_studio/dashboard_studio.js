frappe.pages["dashboard-studio"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Metabase → Insights"),
    single_column: true,
  });

  const mount = document.createElement("div");
  // page.body is a jQuery object in Frappe's page API, not a raw DOM node —
  // use .append() (which accepts the raw element), never .appendChild().
  page.body.append(mount);
  mount.textContent = __("Loading the converter…");

  // Framework-free assets loaded on demand, no bundler. studio_charts.js and
  // studio_mock.js are gone with the dashboard builder they served.
  frappe.require(
    [
      "/assets/dashboard_studio/css/studio.css",
      "/assets/dashboard_studio/js/studio_core.js",
      "/assets/dashboard_studio/js/studio_app.js",
    ],
    () => {
      mount.textContent = "";
      // ?workbook=<name> preselects an Insights workbook; without it the
      // converter offers the default and lets the picker decide.
      const workbook = new URLSearchParams(window.location.search).get("workbook");
      window.DSStudioApp.mount(mount, { workbook });
    }
  );
};
