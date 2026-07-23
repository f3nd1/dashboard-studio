import frappe


@frappe.whitelist()
def check_publishable(dashboard_name: str):
    frappe.only_for("System Manager")
    dashboard = frappe.get_doc("Dashboard Definition", dashboard_name)
    issues = []

    if not dashboard.components:
        issues.append("Dashboard has no components")
    if dashboard.status not in {"QA Approval", "Published"}:
        issues.append("Dashboard has not completed approval")

    return {"publishable": not issues, "issues": issues}
