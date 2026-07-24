import json

import frappe

# Two-level access model (System Manager always allowed as superuser).
DS_READ_ROLES = ("Dashboard Studio Editor", "Dashboard Studio Viewer", "System Manager")
DS_WRITE_ROLES = ("Dashboard Studio Editor", "System Manager")

# Fields the visual editor is allowed to write back to a DS Chart. Layout plus
# the handful of display properties the diagram editor exposes — never metric
# logic or links, which belong to the metric layer.
_EDITABLE_CHART_FIELDS = {
    "chart_title",
    "chart_type",
    "description",
    "pos_x",
    "pos_y",
    "width",
    "height",
    "drill_down_enabled",
}


@frappe.whitelist()
def get_studio_dashboard(dashboard: str):
    """Return a DS Dashboard and its DS Chart records for the visual editor."""
    frappe.only_for(DS_READ_ROLES)
    doc = frappe.get_doc("DS Dashboard", dashboard)
    charts = frappe.get_all(
        "DS Chart",
        filters={"dashboard": dashboard},
        fields=[
            "name", "chart_title", "chart_type", "metric", "section",
            "pos_x", "pos_y", "width", "height", "description", "drill_down_enabled",
        ],
        order_by="pos_y asc, pos_x asc",
    )
    return {"dashboard": doc.as_dict(), "charts": charts}


@frappe.whitelist()
def save_chart(chart: str, patch):
    """Persist an editor patch to one DS Chart. Only allowlisted fields are written.

    ``patch`` is a JSON object (string or dict) of field -> value. Unknown fields
    are ignored rather than trusted.
    """
    frappe.only_for(DS_WRITE_ROLES)
    if isinstance(patch, str):
        patch = json.loads(patch)
    if not isinstance(patch, dict):
        frappe.throw("patch must be a JSON object")

    doc = frappe.get_doc("DS Chart", chart)
    for key, value in patch.items():
        if key in _EDITABLE_CHART_FIELDS:
            doc.set(key, value)
    doc.save()
    return doc.as_dict()
