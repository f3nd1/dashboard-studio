# Dashboard Studio

Dashboard Studio is a Frappe/ERPNext application for importing, mapping, validating, editing, and publishing analytics dashboards.

It is intentionally generic. Metabase is an import source. Sophia/UCC Intelligence Platform is one publishing destination. The core product is the controlled dashboard definition, migration, validation, and design environment between them.

## Current status

This repository is a **Phase 1 starter scaffold**, not a completed production application.

Included now:

- Project architecture and implementation documents
- Claude Code instructions
- Core Frappe app structure
- Starter DocType definitions
- Safe metric-definition validation utilities
- A non-executing query-plan builder
- Basic Desk Page shell
- Current prototypes
- Legacy dashboard and Server Script references
- Metabase SQL samples and pilot packages
- Repository validation script and GitHub workflow

Not implemented yet:

- Production query execution
- Full drag-and-drop designer
- Live AI provider integration
- Direct Metabase API import
- Automated dashboard publishing
- Production permissions and background jobs

## Recommended first milestone

Prove the metadata architecture with one metric:

> Count Student Applicant records grouped by academic year and display the result as a line chart.

Do not begin by migrating all seven legacy Criterion scripts or implementing the complete AI and Metabase features.

## Repository map

```text
.
├── CLAUDE.md
├── docs/
├── prototypes/
├── reference/
├── scripts/
├── dashboard_studio/          # Frappe Python package
├── pyproject.toml
└── package.json
```

See:

- `docs/MASTER_PROJECT_HANDOVER.md`
- `docs/DEVELOPMENT_SETUP.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `CLAUDE.md`

## Basic local validation

```bash
python scripts/validate_repository.py
```

## Frappe installation outline

From a Bench that matches the target ERPNext/Frappe version:

```bash
bench get-app dashboard_studio <YOUR_PRIVATE_GITHUB_REPOSITORY_URL>
bench --site <STAGING_SITE> install-app dashboard_studio
bench build --app dashboard_studio
bench --site <STAGING_SITE> migrate
```

Always install and test on staging before production.
