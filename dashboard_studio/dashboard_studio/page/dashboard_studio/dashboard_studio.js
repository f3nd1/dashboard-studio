frappe.pages["dashboard-studio"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Dashboard Studio"),
    single_column: true,
  });

  page.set_primary_action(__("New Dashboard"), () => {
    frappe.set_route("Form", "Dashboard Definition", "new-dashboard-definition");
  });

  const $body = $(page.body);
  $body.html(`
    <div class="dashboard-studio-shell">
      <div class="dashboard-studio-status" data-health-status>
        ${__("Checking application status...")}
      </div>
      <div class="dashboard-studio-grid">
        <section class="dashboard-studio-card">
          <h3>${__("Dashboard Definitions")}</h3>
          <p>${__("Create and manage dashboard layouts and publishing status.")}</p>
          <button class="btn btn-default btn-sm" data-route="Dashboard Definition">${__("Open")}</button>
        </section>
        <section class="dashboard-studio-card">
          <h3>${__("Dataset Definitions")}</h3>
          <p>${__("Control approved DocTypes, fields, and drill-down data.")}</p>
          <button class="btn btn-default btn-sm" data-route="Dataset Definition">${__("Open")}</button>
        </section>
        <section class="dashboard-studio-card">
          <h3>${__("Metric Definitions")}</h3>
          <p>${__("Define reusable aggregations, conditions, formulas, and evidence levels.")}</p>
          <button class="btn btn-default btn-sm" data-route="Metric Definition">${__("Open")}</button>
        </section>
        <section class="dashboard-studio-card">
          <h3>${__("Migration Jobs")}</h3>
          <p>${__("Track imported dashboards, mappings, and result validation.")}</p>
          <button class="btn btn-default btn-sm" data-route="Migration Job">${__("Open")}</button>
        </section>
      </div>
    </div>
  `);

  $body.on("click", "[data-route]", function () {
    frappe.set_route("List", $(this).attr("data-route"));
  });

  frappe.call("dashboard_studio.api.health.ping")
    .then((response) => {
      const message = response.message || {};
      $body.find("[data-health-status]").text(
        message.ok
          ? __("Dashboard Studio is installed. Phase 1 runtime is not yet implemented.")
          : __("Dashboard Studio health check failed.")
      );
    })
    .catch(() => {
      $body.find("[data-health-status]").text(__("Unable to reach the Dashboard Studio backend."));
    });
};
