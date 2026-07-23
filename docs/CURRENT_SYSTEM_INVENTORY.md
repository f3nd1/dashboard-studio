# Current System Inventory

## Existing frontend

- One Custom HTML Block.
- Approximately 57 HTML lines.
- Approximately 2,919 JavaScript lines.
- Approximately 1,996 CSS lines.
- Shared dashboard renderer.
- Central configuration for seven criteria.
- Chart plugin registry.

Known chart types include:

- bar
- donut
- funnel
- lifecycle
- flow
- matrix
- radar
- trend
- gauge
- decision
- network
- reconciliation
- ladder
- risk-matrix

## Existing backend

Seven separate Python Server Scripts:

- `ucc_analytics_criterion_1`
- `ucc_analytics_criterion_2`
- `ucc_analytics_criterion_3`
- `ucc_analytics_criterion_4`
- `ucc_analytics_criterion_5`
- `ucc_analytics_criterion_6`
- `ucc_analytics_criterion_7`

Approximate total: 16,633 Python lines.

Repeated helpers exist across the scripts for source resolution, safe fields, row fetching, comparisons, text cleaning, field resolution, response standardisation, and number conversion.

## Migration constraint

The existing dashboards must remain operational while Dashboard Studio is built. The legacy code under `reference/legacy/` is a baseline and compatibility reference.
