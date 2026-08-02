app_name = "dashboard_studio"
app_title = "Metabase → Insights Converter"
app_publisher = "United Ceres College Pte. Ltd."
app_description = "Convert Metabase questions into Frappe Insights queries"
app_email = "replace-me@example.invalid"
app_license = "Proprietary"

# Ship the DS roles so they exist on install/migrate: Editor and Viewer, plus
# QA Approver, which exists to separate duties — an Editor can move a dashboard
# up to QA Approval but cannot publish its own work.
fixtures = [
    {"dt": "Role", "filters": [["role_name", "in", ["Dashboard Studio Editor", "Dashboard Studio Viewer", "Dashboard Studio QA Approver"]]]}
]
