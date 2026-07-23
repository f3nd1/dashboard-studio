import frappe


@frappe.whitelist()
def supported_features():
    frappe.only_for("System Manager")
    return {
        "implemented": [],
        "planned": [
            "paste_sql",
            "metabase_dashboard_inventory",
            "saved_question_resolution",
            "source_mapping",
            "result_comparison",
        ],
        "status": "scaffold",
    }
