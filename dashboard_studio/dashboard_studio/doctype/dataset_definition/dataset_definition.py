import json

import frappe
from frappe.model.document import Document


class DatasetDefinition(Document):
    def validate(self):
        for fieldname in (
            "allowed_fields_json",
            "restricted_fields_json",
            "default_conditions_json",
            "drilldown_fields_json",
        ):
            value = self.get(fieldname)
            if value:
                try:
                    json.loads(value)
                except json.JSONDecodeError as exc:
                    frappe.throw(f"{self.meta.get_label(fieldname)} contains invalid JSON: {exc}")
