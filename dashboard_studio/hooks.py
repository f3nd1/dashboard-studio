app_name = "dashboard_studio"
app_title = "Dashboard Studio"
app_publisher = "United Ceres College Pte. Ltd."
app_description = "Visual dashboard migration, validation, design, and publishing"
app_email = "replace-me@example.invalid"
app_license = "Proprietary"

# Ship the two-level DS roles so they exist on install/migrate. Two levels only
# (edit / view) — NOT the five-role model in SECURITY_AND_GOVERNANCE.md yet.
fixtures = [
    {"dt": "Role", "filters": [["role_name", "in", ["Dashboard Studio Editor", "Dashboard Studio Viewer"]]]}
]
