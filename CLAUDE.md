# Claude Code Instructions — Dashboard Studio

## Purpose

Build Dashboard Studio as a proper Frappe application installed inside an existing Frappe/ERPNext site.

The product must support two connected use cases:

1. Import and migrate dashboards from systems such as Metabase into controlled Frappe analytics definitions.
2. Visually create and edit dashboards and diagrams that can be published to viewers such as Sophia/UCC Intelligence Platform.

The product name is generic. Do not make Metabase, Sophia, UCC, EduTrust, or any single dashboard viewer the core architecture.

## Read first

Before modifying code, read:

1. `docs/MASTER_PROJECT_HANDOVER.md`
2. `docs/ARCHITECTURE.md`
3. `docs/DATA_MODEL.md`
4. `docs/IMPLEMENTATION_PLAN.md`
5. `docs/SECURITY_AND_GOVERNANCE.md`
6. `docs/CURRENT_SYSTEM_INVENTORY.md`

## Architecture rules

1. Build a proper Frappe app named `dashboard_studio`.
2. Do not build the final product as one large Server Script or one large Custom HTML Block.
3. Store dashboard logic as managed records and structured JSON, not chart-specific Python.
4. Keep legacy files under `reference/` unchanged unless explicitly asked.
5. Treat existing prototypes as UX references, not production code.
6. Use a shared permission-aware analytics runtime.
7. Never execute arbitrary user- or AI-generated SQL.
8. AI may propose structured configurations. The server validates them. A user approves them.
9. Metabase migration must include source mapping and result comparison before publishing.
10. Preserve current dashboard APIs during migration through adapters or wrappers.
11. Work on staging only. Do not connect to or modify production.
12. Make small, reviewable commits with specific verification evidence.

## Phase 1 scope

Implement only:

- Dashboard Definition
- Dashboard Component child table
- Dataset Definition
- Metric Definition
- Safe configuration validator
- Safe query-plan builder
- Basic Studio Desk Page
- Count, sum, average, minimum, maximum, and percentage definition support
- KPI, line, bar, donut, and table component definitions
- Draft and Published lifecycle fields

Do not implement the complete AI Copilot or direct Metabase API importer until the core runtime is proven.

## First vertical slice

Create this end-to-end flow:

1. Configure a Dataset Definition for `Student Applicant`.
2. Configure a Metric Definition for count grouped by `academic_year`.
3. Build and validate a safe query plan.
4. Execute the result through a permission-aware backend implementation.
5. Display it on the Studio page as a line chart.
6. Save, reload, and version the dashboard definition.
7. Compare the result with the supplied Metabase SQL sample.

## Required working method

For each task:

1. Inspect the relevant files and current Frappe version.
2. State material assumptions.
3. Define observable success criteria.
4. Make the smallest coherent change.
5. Run focused checks.
6. Report files changed and checks run.

## Commands

Repository-only checks:

```bash
python scripts/validate_repository.py
```

Frappe checks must be adapted to the local Bench and site name. Never invent a production site name.

## Security boundaries

- No unrestricted SQL editor for ordinary users.
- No API credentials in source control.
- No personal student data in fixtures or tests.
- No AI provider keys in browser code.
- No publishing without explicit approval.
- No field outside a Dataset Definition allowlist.
- No join outside an approved relationship definition.
- No silent formula or denominator changes.

## Legacy references

`reference/legacy/` contains the existing Custom Block and seven Criterion Server Scripts. They are production references and must not be reformatted or rewritten as part of app scaffolding.

## Definition of done for Phase 1

A trained user can configure and save a simple grouped metric without editing Python or JavaScript, and the result matches the legacy or Metabase baseline.
