frappe.ui.form.on("DS Dashboard", {
  refresh(frm) {
    if (frm.is_new()) return;

    // Entry point into the visual editor, so a saved dashboard can be opened
    // without hand-typing its name into the URL. Same pattern as DS Migration
    // Project's "Open Mapping View": the route carries the record name.
    // add_custom_button keeps this secondary — Save stays the primary action.
    frm.add_custom_button(__("Open in Studio"), () => {
      frappe.set_route("dashboard-studio", frm.doc.name);
    });
  },
});
