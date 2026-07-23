# Project Status

## Current state

- Product concept: defined
- Interactive prototype: available
- Generic Frappe application scaffold: included
- Core DocType schemas: starter versions included
- Safe definition validator: starter implementation included
- Query-plan builder: starter implementation included
- Production query execution: not implemented
- Metabase API connector: not implemented
- AI provider connector: not implemented
- Visual drag-and-drop editor: prototype only
- Production deployment: not started

## Immediate next action

Install the scaffold on a staging Bench that matches the target Frappe/ERPNext version. Confirm the generated DocTypes and Desk Page load correctly before writing the runtime.

## Important limitation

This repository is an implementation starting point. The included Python modules intentionally do not execute analytics queries yet. This prevents the scaffold from implying unsafe or unverified production behaviour.
