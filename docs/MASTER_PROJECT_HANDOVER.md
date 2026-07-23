# Dashboard Studio — Master Project Handover

## 1. Executive overview

Dashboard Studio is a visual analytics migration and design application for Frappe/ERPNext.

It solves two connected problems:

1. Existing dashboards in systems such as Metabase are difficult and slow to migrate into an ERPNext-based analytics environment.
2. Existing in-system dashboards are difficult to maintain because every chart change may require editing large Python, JavaScript, CSS, and HTML files.

Dashboard Studio sits between data sources and dashboard viewers. It imports or creates controlled dashboard definitions, validates the data, allows authorised users to edit the design, and publishes approved definitions to a viewer.

Metabase is one import connector. Sophia/UCC Intelligence Platform is one publishing connector. Neither should control the core data model.

## 2. Current pain points

### Business pain points

- Every new chart requires technical intervention.
- Simple title, filter, or visual changes may require replacing large files.
- Dashboard logic is difficult for non-developers to understand.
- Metabase SQL has to be manually reverse-engineered.
- There is no standard side-by-side validation between old and new results.
- Dashboard changes are difficult to approve, version, and roll back.
- Audit explanations and data lineage are not consistently documented.

### Technical pain points

- Seven large Criterion-specific Python Server Scripts contain repeated helper logic.
- The current frontend is a large shared Custom HTML Block.
- Chart definitions, data calculations, and rendering logic are coupled.
- Server Scripts operate under a restricted environment and are difficult to test as an application.
- Metabase-generated SQL can contain nested saved questions, joins, aliases, and redundant columns.
- There is no reusable metric registry or safe query runtime.

## 3. Product vision

An authorised user should be able to:

1. Import a Metabase dashboard or paste a query.
2. See the discovered source tables, fields, filters, calculations, and visuals.
3. Map source tables to Frappe DocTypes.
4. Convert supported calculations into safe structured definitions.
5. Compare the source result with the Frappe result.
6. Edit chart names, types, positions, filters, and display settings visually.
7. Ask an AI assistant to propose a chart configuration in plain language.
8. Submit the dashboard for review and approval.
9. Publish it to Sophia or another viewer.
10. Roll back to an earlier published version if necessary.

## 4. Core principle

> Dashboards must be managed as data, not as repeatedly rewritten code.

The normal workflow should be:

```text
Create or import definition
→ map data
→ preview
→ validate
→ approve
→ publish
```

Code generation may remain available as a compatibility export, but it is not the primary operating model.

## 5. Target architecture

```text
Sources
├── Frappe DocTypes
├── Child tables and linked DocTypes
├── Metabase dashboards and questions
└── Approved manual definitions

Dashboard Studio
├── Dataset registry
├── Metric registry
├── Visual dashboard editor
├── AI configuration assistant
├── Metabase migration assistant
├── Validation centre
├── Governance and versioning
└── Publishing connectors

Destinations
├── Sophia/UCC Intelligence Platform
├── Frappe Desk viewer
├── Exported JSON
├── Compatibility Python
└── Future dashboard viewers
```

## 6. Main user groups

- Viewer: views published dashboards.
- Designer: arranges charts and display settings.
- Data Mapper: approves DocType, field, and relationship mappings.
- Technical Reviewer: validates formulas, filters, and result comparisons.
- QA Approver: approves publication.
- Administrator: manages integrations, permissions, and system configuration.

## 7. Main modules

### 7.1 Dashboard Builder

- Drag and drop components.
- Rename and resize charts.
- Choose chart types.
- Select datasets and metrics.
- Add dashboard-level and card-level filters.
- Preview desktop, tablet, and mobile layouts.
- Display data lineage and sample records.

### 7.2 Data and Metric Registry

- Approved source DocTypes.
- Allowed and restricted fields.
- Approved parent-child and linked relationships.
- Count, sum, average, minimum, maximum, percentage, and duration definitions.
- Reusable metrics shared by multiple dashboards.

### 7.3 AI Configuration Assistant

The AI may:

- Propose a structured metric from natural language.
- Explain a formula.
- Suggest an appropriate visual.
- Suggest source mappings.
- Identify inconsistent categories or missing fields.

The AI must not:

- Execute arbitrary SQL.
- publish automatically.
- expose restricted fields.
- silently change a formula or denominator.
- create unapproved joins.

### 7.4 Metabase Migration Assistant

- Connect to Metabase or accept pasted SQL.
- Inventory dashboards and cards.
- Resolve nested saved-question dependencies.
- Identify actual database tables and fields.
- Map `tab...` tables to Frappe DocTypes.
- Translate supported queries into controlled definitions.
- Retain unsupported SQL for technical review.
- Compare source and destination results.

### 7.5 Validation Centre

For every migrated metric, show:

```text
Source result
Destination result
Difference
Match status
Calculation explanation
Source lineage
Reviewer decision
```

### 7.6 Governance and Publishing

Suggested workflow:

```text
Draft → Technical Review → QA Approval → Published → Archived
```

Required controls:

- Version history.
- Change impact warnings.
- Approval records.
- Published snapshots.
- Rollback.
- Audit log.

## 8. Initial data model

Start with four main DocTypes and two child tables:

1. Dashboard Definition
2. Dashboard Component
3. Dataset Definition
4. Metric Definition
5. Migration Job
6. Migration Mapping

Do not create many specialised DocTypes before the first vertical slice is proven.

## 9. First vertical slice

Use the Admission Intelligence sample:

- Source DocType: Student Applicant
- Dimension: academic_year
- Measure: name
- Aggregation: count
- Chart: line
- Baseline: supplied Metabase SQL

Success means:

1. The Dataset Definition stores the allowed source and fields.
2. The Metric Definition stores the grouping and aggregation.
3. The runtime produces the same annual counts as Metabase.
4. A user can change the chart title or type without modifying Python.
5. The dashboard can be saved and reloaded.

## 10. Pilot areas

### Pilot A: Admission analytics

- Total applicants.
- Approved applicants.
- Admitted students.
- Admission success rate.
- Applicants by academic year.
- Admitted students by academic year.
- Applicants by nationality.
- Applicants by programme.
- Students by agent.
- Counselling-to-admission duration.

### Pilot B: Performance outcomes

- Employee Satisfaction Index by year.
- Employee Satisfaction by metric and year.
- Other controlled performance outcome measures.

## 11. Deployment strategy

1. Preserve the current dashboards.
2. Install Dashboard Studio on a staging site.
3. Implement and validate the first metric.
4. Add the basic visual editor.
5. Connect the existing viewer to published definitions.
6. Add AI proposals.
7. Add manual SQL migration.
8. Add direct Metabase API integration.
9. Migrate one dashboard or criterion at a time.
10. Retire legacy calculations only after result parity is proven.

## 12. Non-goals for the first release

- A general unrestricted SQL workbench.
- A full replacement for every Metabase feature.
- Automatic migration of every complex query.
- Automatic publishing by AI.
- Immediate replacement of all seven legacy Python scripts.
- Storage of production credentials in the application repository.

## 13. Success criteria

- A simple chart can be created without code.
- A simple Metabase card can be imported and mapped.
- Source and destination results can be compared.
- Published definitions have approval and version history.
- Restricted fields cannot be selected.
- AI output is structured and server-validated.
- Existing dashboards continue working during migration.

## 14. Current repository status

This repository includes a safe starting scaffold. It does not yet execute production analytics or connect to Metabase or an AI provider. Those capabilities must be implemented incrementally on staging with explicit tests.
