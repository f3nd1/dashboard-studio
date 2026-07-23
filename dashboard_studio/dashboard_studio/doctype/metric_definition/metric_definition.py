import json

import frappe
from frappe.model.document import Document


class MetricDefinition(Document):
    def validate(self):
        for fieldname in ("conditions_json", "formula_json"):
            value = self.get(fieldname)
            if value:
                try:
                    json.loads(value)
                except json.JSONDecodeError as exc:
                    frappe.throw(f"{self.meta.get_label(fieldname)} contains invalid JSON: {exc}")
