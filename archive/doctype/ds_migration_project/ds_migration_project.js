frappe.ui.form.on("DS Migration Project", {
  refresh(frm) {
    if (frm.is_new()) return;

    // Entry point into the Mapping view — no separate project selector needed.
    frm.add_custom_button(__("Open Mapping View"), () => {
      window.location.href =
        "/app/dashboard-studio?project=" + encodeURIComponent(frm.doc.name);
    });

    // The one manual transition in scope. Later states (Ready to Publish,
    // Published) belong to the validation/publishing features, not here.
    if (frm.doc.status === "Mapping") {
      frm.add_custom_button(__("Mark Mapping Complete"), () => {
        frm.set_value("status", "Validating");
        frm.save();
      });
    }
  },
});
