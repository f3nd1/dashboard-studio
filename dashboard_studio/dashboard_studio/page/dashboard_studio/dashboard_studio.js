frappe.pages["dashboard-studio"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Dashboard Studio"),
    single_column: true,
  });

  page.set_primary_action(__("New Dashboard"), () => {
    frappe.new_doc("DS Dashboard");
  });

  const mount = document.createElement("div");
  page.body.appendChild(mount);
  mount.textContent = __("Loading the visual editor…");

  // Load the framework-free editor assets on demand (no bundler required), then
  // mount the SPA. Without a `dashboard` route param the app falls back to MOCK
  // data — see studio_mock.js — so it renders even before real records exist.
  frappe.require(
    [
      "/assets/dashboard_studio/css/studio.css",
      "/assets/dashboard_studio/js/studio_core.js",
      "/assets/dashboard_studio/js/studio_mock.js",
      "/assets/dashboard_studio/js/studio_app.js",
    ],
    () => {
      mount.textContent = "";
      const dashboard = frappe.get_route()[1] || null; // /app/dashboard-studio/<DS Dashboard name>
      window.DSStudioApp.mount(mount, { dashboard });
    }
  );
};
