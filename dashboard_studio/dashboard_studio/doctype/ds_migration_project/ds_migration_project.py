import frappe
from frappe.model.document import Document

# Once mapping is declared complete, the project's mappings are resolved through
# its data_source; repointing it would silently orphan every one of them.
_DATA_SOURCE_LOCKED_STATES = ("Validating", "Ready to Publish", "Published")


class DSMigrationProject(Document):
	def validate(self):
		if self.status not in _DATA_SOURCE_LOCKED_STATES:
			return
		before = self.get_doc_before_save()
		if before and before.data_source and before.data_source != self.data_source:
			frappe.throw(
				f"Data Source cannot be changed once the project reaches {self.status}. "
				"Its mappings are resolved through the original source."
			)
