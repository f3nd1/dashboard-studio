import json

import frappe


@frappe.whitelist()
def get_active_datasets():
    frappe.only_for("System Manager")
    rows = frappe.get_all(
        "Dataset Definition",
        filters={"status": "Active"},
        fields=[
            "name",
            "dataset_name",
            "source_doctype",
            "child_doctype",
            "allowed_fields_json",
            "restricted_fields_json",
        ],
        order_by="dataset_name asc",
    )
    for row in rows:
        row["allowed_fields"] = _load_json_list(row.pop("allowed_fields_json", None))
        row["restricted_fields"] = _load_json_list(row.pop("restricted_fields_json", None))
    return rows


def _load_json_list(value):
    if not value:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        frappe.throw("Dataset field configuration must be a JSON list")
    return parsed
