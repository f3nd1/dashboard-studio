import frappe


@frappe.whitelist()
def ping():
    return {
        "ok": True,
        "app": "dashboard_studio",
        "status": "scaffold",
        "message": "Dashboard Studio scaffold is installed",
    }
