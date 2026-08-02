# Implementation Plan

## Phase 0 — Environment and baseline

Actions:

- Confirm Frappe and ERPNext versions.
- Install the scaffold on staging.
- Record current legacy dashboard outputs.
- Add representative non-sensitive test data.

Verification:

- App installs and migrates without error.
- Desk Page and core DocTypes load.
- Existing dashboards are unchanged.

## Phase 1 — Safe metadata runtime

Actions:

- Finalise Dataset and Metric schemas.
- Implement field allowlists and operator validation.
- Implement single-DocType count, sum, average, min, and max.
- Implement group-by for one dimension.
- Add runtime-filter validation.

Verification:

- Applicants by academic year matches Metabase.
- Restricted fields are rejected.
- Invalid operators and aggregations are rejected.

## Phase 2 — Basic visual editor

Actions:

- Dataset and field browser.
- Chart type selection.
- Component title and layout editing.
- Data preview.
- Save and reload draft dashboard.

Verification:

- A non-developer can create and edit one chart without code.

## Phase 3 — Viewer publishing

Actions:

- Publish approved definition.
- Add viewer adapter.
- Support draft versus published versions.
- Add rollback.

Verification:

- A published change appears without replacing a large JS or Python file.

## Phase 4 — AI proposal assistant

Actions:

- Server-side AI provider abstraction.
- Metadata-limited prompts.
- Structured JSON response schema.
- Proposal preview and human confirmation.

Verification:

- "Show admitted students by year" creates a valid reviewable proposal.
- The AI cannot select restricted fields or publish directly.

## Phase 5 — Manual Metabase migration

Actions:

- Paste SQL.
- Detect tables, fields, filters, grouping, and aggregation.
- Map `tab...` tables to DocTypes.
- Create draft Dataset and Metric definitions.
- Compare source CSV with Frappe result.

Verification:

- A simple count/group-by card is imported and validated.

## Phase 6 — Direct Metabase connector

Actions:

- Server-side authentication.
- Dashboard and card inventory.
- Saved-question dependency resolution.
- Background jobs and progress reporting.

Verification:

- A complete simple dashboard can be inventoried and staged for review.

## Phase 7 — Legacy migration

Migrate incrementally:

1. Admission Intelligence.
2. Performance Outcomes.
3. Agent analytics.
4. Academic analytics.
5. Remaining areas.

Never retire legacy calculations before parity is documented.
