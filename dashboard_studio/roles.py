"""The two role tuples every endpoint checks against.

Extracted from api/studio.py during the scope cut. They lived there when
`studio.py` was the app's main endpoint module; keeping the converter pointed at
that file would have kept governance.py, edutrust.py and metric_builder.py alive
with it, for two constants.

The roles themselves are created by `fixtures/role.json`, wired up in hooks.py —
without that fixture every `frappe.only_for` below refuses on a fresh site.
"""

# Reading is the wider set on purpose: a Viewer can look at what a conversion
# would do, and a QA Approver is reviewing rather than building.
DS_READ_ROLES = (
    "Dashboard Studio Editor",
    "Dashboard Studio Viewer",
    "Dashboard Studio QA Approver",
    "System Manager",
)
DS_WRITE_ROLES = ("Dashboard Studio Editor", "System Manager")
