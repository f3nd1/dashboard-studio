# Metabase Migration

## Migration pipeline

```text
Import dashboard or SQL
→ inventory cards and filters
→ resolve saved questions
→ discover physical tables and fields
→ map to Frappe DocTypes
→ translate supported logic
→ preview
→ compare results
→ technical review
→ publish
```

## Automatically supported first

- Record count.
- Conditional count.
- Sum and average.
- Single-dimension group-by.
- Sorting.
- Simple percentages.
- Simple bar, line, KPI, donut, and table visuals.

## Review required

- Multiple joins.
- Child-table joins.
- Date duration calculations.
- Nested saved questions.
- Complex CASE logic.
- Null and duplicate rules.
- Database-specific functions.
- Window functions.

## Validation requirement

Every migrated metric must retain:

- Source query or question reference.
- Source result extract.
- Target definition.
- Target result.
- Difference.
- Reviewer decision.

## Mapping example

```text
Metabase table: tabStudent Applicant
Frappe DocType: Student Applicant

Metabase field: academic_year
Frappe field: academic_year

Aggregation: COUNT(*)
Dashboard definition: count of name grouped by academic_year
```

## Unsupported logic

Unsupported SQL must not be silently approximated. It should be preserved as source evidence and marked for technical review.
