# UCC Criterion 1 to 7 Server Script Standardisation

The seven scripts remain separate ERPNext Server Scripts. No custom app, shared module or new runtime dependency is required.

## Shared contract applied

- Protected JSON payload parsing
- Filter dictionary validation
- Standard actions: summary, source_status, policy_registry, requirement_registry, question_registry and drilldown
- Criterion 3 retains question_catalogue as a backward-compatible alias
- Shared API contract version 2.1.0
- Standard response arrays and summaries
- Shared readiness object
- Shared source-mapping structure
- Shared question drill-down metadata
- Query failures distinguished from valid zero results
- Truncation detected by retrieving row_limit + 1

## Criterion-specific correction

Criterion 4 no longer queries Course Adjustment Request Form or custom_course_adjustment. The 12 affected movement, late-admission and refund metrics are returned as unsupported until a verified replacement mapping is supplied.

## Deployment

Replace each existing Criterion Server Script with its matching Standardised file. Keep each existing API method unchanged. Allow Guest must remain disabled.
