# Context Prompt for a New AI or Developer Chat

```text
We are building Dashboard Studio, a generic Frappe/ERPNext application for dashboard migration, visual editing, validation, and publishing.

Metabase is an import source. Sophia/UCC Intelligence Platform is one publishing destination. Neither is the core product.

The current UCC analytics system uses one large Custom HTML Block and seven large Criterion-specific Python Server Scripts. The project aims to replace repeated code changes with managed Dataset, Metric, Dashboard, and Component definitions plus a shared safe analytics runtime.

The repository contains:
- a Frappe app scaffold;
- starter DocTypes;
- architecture and implementation documents;
- interactive prototypes;
- legacy source files under reference/;
- Metabase SQL samples;
- safe validation and query-plan starter code.

Important rules:
- work on staging only;
- do not modify legacy reference files unless explicitly requested;
- do not execute arbitrary SQL;
- AI may propose structured configuration but cannot publish;
- implement one vertical slice first: Student Applicants grouped by Academic Year;
- compare every migrated result against the Metabase or legacy baseline;
- keep current dashboards operational during migration.

First inspect CLAUDE.md and docs/. Do not build the entire application at once. Propose the minimum next implementation step with measurable verification criteria.
```
