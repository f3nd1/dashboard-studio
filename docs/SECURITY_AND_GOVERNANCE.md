# Security and Governance

## Data security

- Use Frappe permissions and explicit Dataset allowlists.
- Do not expose NRIC, FIN, passport, personal contact, or sensitive notes by default.
- Use masked or synthetic data for development where practical.
- Store connector credentials in server-side configuration, never JavaScript or Git.

## Query security

- Do not provide unrestricted SQL execution to normal users.
- Allow only approved aggregations and operators.
- Enforce maximum rows and timeouts.
- Validate filters against approved fields.
- Require approved relationships for joins.

## AI safety

AI receives only the metadata necessary for the request. It returns a proposal, not executable code.

Required control flow:

```text
AI proposal → server validation → user review → save as draft
```

AI must not publish, deploy, or execute arbitrary SQL.

## Governance workflow

Suggested states:

- Draft
- Technical Review
- QA Approval
- Published
- Archived

## Roles

- Dashboard Studio Viewer
- Dashboard Studio Designer
- Dashboard Studio Data Mapper
- Dashboard Studio Approver
- Dashboard Studio Administrator

The starter scaffold grants only System Manager access until these roles are designed and tested.
