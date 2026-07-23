import frappe


@frappe.whitelist()
def get_dashboard(name: str):
    frappe.only_for("System Manager")
    document = frappe.get_doc("Dashboard Definition", name)
    return document.as_dict()
