UCC EMPLOYEE SATISFACTION INDEX - CRITERION 7 PACKAGE

Placement
- EduTrust Criterion 7
- Subcriterion 7.1.1 Measurement of Outcomes
- Outcome domain: People Development Outcomes

Files
1. 01_SERVER_SCRIPT_PYTHON/UCC Analytics - Criterion 7 - Employee Satisfaction.py
   Paste only into the ERPNext Server Script named UCC Analytics - Criterion 7.
   Keep Script Type = API and API Method = ucc_analytics_criterion_7.

2. 02_CUSTOM_BLOCK_JAVASCRIPT/JS - Admission Intelligence + Employee Satisfaction.js
   Paste only into the Custom HTML Block JavaScript field.
   This file retains the earlier Admission Intelligence frontend changes.

No CSS or HTML replacement is required for these two charts.

Implemented charts
- Employee Satisfaction Index per Year
  Parent: Quality Performance Outcomes
  Parent record: Employee Satisfaction Index
  Child DocType: Quality Performance Outcomes Performance Childtable
  Fields: year, value

- Employee Satisfaction Index per Metric
  Parent: Quality Performance Outcomes
  Parent record: Employee Satisfaction Index
  Child DocType: Quality Performance Actual Value Parameter Childtable
  Fields: metric, year, actual_value
  Calculation: average actual_value for each metric and year

Important SQL correction
The supplied Metabase 'per Metric' query joined both child tables to the same parent even though the output used only the Actual Value Parameter child table. That creates unnecessary row multiplication. The ERPNext implementation reads each child table separately through the Employee Satisfaction Index parent record.

Behaviour
- Duplicate rows for the same year are averaged and record_count is disclosed.
- Duplicate rows for the same metric and year are averaged and record_count is disclosed.
- Review Year filter is applied to both datasets.
- Missing child-table mapping is shown as partial/unavailable, not zero.
- The backend first confirms that the signed-in user can read the Employee Satisfaction Index parent record.

Deployment order
1. Back up the existing Criterion 7 Server Script.
2. Replace it with the Python file in folder 01.
3. Save and test action=summary for subcriterion 7.1.1.
4. Back up the current Custom HTML Block JavaScript.
5. Replace it with the JavaScript file in folder 02.
6. Open Criterion 7 > 7.1.1 Measurement of Outcomes.
7. Confirm both Employee Satisfaction charts appear at the top of the visual section.
8. Test the Review Year filter.

Verification completed before packaging
- Python syntax check passed.
- JavaScript syntax check passed.
- Mock ERPNext execution confirmed per-year, per-metric and latest-index outputs.

Live verification still required
- Exact parent Table field mapping on the UCC ERPNext site.
- Actual stored values and year formats.
- Current-user permissions.
- Chart rendering inside the deployed Custom HTML Block.
