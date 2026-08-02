# Architecture

## Logical components

```text
Frappe Desk Page / Viewer
        ↓
Whitelisted API layer
        ↓
Definition and permission validation
        ↓
Analytics runtime
        ↓
Frappe ORM / approved database access
```

Additional integrations:

```text
Metabase API → importer → parser → mapper → validation
AI provider → structured proposal → server validation → user approval
Publisher → approved definition → viewer adapter
```

## Trust boundaries

### Browser

The browser may edit draft definitions and request previews. It must not hold database credentials, AI provider secrets, or unrestricted query logic.

### Server

The server resolves permissions, allowed fields, relationships, formulas, runtime filters, and publication status.

### External services

Metabase and AI integrations must use server-side credentials. Imported data and AI prompts must be minimised and logged according to policy.

## Source modules

- `dashboard_studio/api/`: whitelisted application endpoints.
- `dashboard_studio/analytics/`: validation, planning, execution, and formatting.
- `dashboard_studio/integrations/metabase/`: import connector.
- `dashboard_studio/integrations/ai/`: AI provider abstraction.
- `dashboard_studio/dashboard_studio/doctype/`: managed definitions.
- `dashboard_studio/dashboard_studio/page/`: Desk application page.
- `dashboard_studio/public/`: shared browser assets.

## Runtime principle

The builder creates a structured definition. The server validates it and creates a safe query plan. Only the runtime translates the plan into approved database operations.

The first implementation should support a single source DocType and simple grouped aggregations. Joins, child tables, duration calculations, and advanced formulas should be added only after the base path is tested.

## Compatibility

Legacy Criterion APIs and the current Sophia viewer should remain available during migration. Adapters may merge legacy results with configured results until each area is validated.
