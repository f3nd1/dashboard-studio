frappe.pages["dashboard-studio"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Dashboard Studio"),
    single_column: true,
  });

  let app = null;
  // Creates a real DS Dashboard and opens it in the editor. Deliberately not
  // frappe.new_doc() — that navigates away to the standard form and leaves the
  // studio behind.
  page.set_primary_action(__("New Dashboard"), () => {
    if (app) app.newDashboard();
  });

  const mount = document.createElement("div");
  // page.body is a jQuery object in Frappe's page API, not a raw DOM node —
  // use .append() (which accepts the raw element), never .appendChild().
  page.body.append(mount);
  mount.textContent = __("Loading the visual editor…");

  // Load the framework-free editor assets on demand (no bundler required), then
  // mount the SPA. Without a `dashboard` route param the app lists real
  // DS Dashboards and opens the most recent one; sample data is only used when
  // the server cannot be reached, or when the user asks for it explicitly.
  frappe.require(
    [
      "/assets/dashboard_studio/css/studio.css",
      "/assets/dashboard_studio/js/studio_core.js",
      "/assets/dashboard_studio/js/studio_charts.js",
      "/assets/dashboard_studio/js/studio_mock.js",
      "/assets/dashboard_studio/js/studio_app.js",
    ],
    () => {
      mount.textContent = "";
      const dashboard = frappe.get_route()[1] || null; // /app/dashboard-studio/<DS Dashboard name>
      // The route segment is already the dashboard, so a migration project
      // arrives as a query param: /app/dashboard-studio?project=<name>
      const project = new URLSearchParams(window.location.search).get("project");
      app = window.DSStudioApp.mount(mount, { dashboard, project });
    }
  );
};
