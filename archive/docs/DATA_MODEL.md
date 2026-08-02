# Data Model

## Dashboard Definition

Represents one dashboard and its lifecycle.

Key fields:

- Dashboard Name
- Description
- Classification and Subclassification
- Status
- Version
- Layout JSON
- Default Filters JSON
- Dashboard Components
- Published By and Published On

## Dashboard Component

Child table containing the visual cards in a dashboard.

Key fields:

- Component ID
- Title
- Chart Type
- Metric
- Position X and Y
- Width and Height
- Display Settings JSON

## Dataset Definition

Controls which data source and fields may be used.

Key fields:

- Dataset Name
- Source DocType
- Child DocType, when applicable
- Parent Field
- Allowed Fields JSON
- Restricted Fields JSON
- Default Conditions JSON
- Drilldown Fields JSON
- Status

## Metric Definition

Defines a reusable calculation.

Key fields:

- Metric Name
- Dataset
- Dimension Field
- Measure Field
- Aggregation
- Conditions JSON
- Formula JSON
- Unit
- Decimal Places
- Evidence Level
- Classification and Subclassification
- Status

## Migration Job

Tracks one import attempt from Metabase, pasted SQL, or another source.

Key fields:

- Migration Name
- Source Platform
- Source Dashboard ID
- Status
- Imported Definition JSON
- Validation Summary JSON
- Migration Mappings

## Migration Mapping

Child table containing source-to-Frappe mappings and validation status.

Key fields:

- Source Card ID and Title
- Source Table and Field
- Target DocType and Field
- Confidence
- Mapping Status
- Validation Status

## Future records

Only introduce these after the first vertical slice:

- Published Dashboard Snapshot
- Approved Relationship Definition
- Formula Definition
- Validation Result
- Connector Configuration
- AI Proposal Log
