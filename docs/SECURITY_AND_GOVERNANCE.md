# Security and Governance

## Data security

- Use Frappe permissions and explicit field allowlists. On the DS path this is
  DS Metric's `allowed_fields`, which is **block-by-default**: a metric with no
  allowlist refuses to run. There is no "restricted fields" denylist, because an
  allowlist is the stricter control.
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

**Implemented.** A DS Dashboard moves through four stages, with `Archived` for
superseded dashboards:

```text
Draft → Technical Review → QA Approval → Published
                                            ↓
                                        Archived
```

Any review stage may be returned to `Draft` for correction. Stages cannot be
skipped — a Draft dashboard cannot jump to Published.

| Transition | Who may make it |
|---|---|
| Draft → Technical Review | Editor |
| Technical Review → QA Approval | Editor |
| **QA Approval → Published** | **QA Approver only** |
| any review stage → Draft (return for correction) | Editor or QA Approver |
| Published → Archived | Editor |

System Manager may make any transition, as superuser.

### Separation of duties

**An Editor cannot publish their own work.** That single rule is why the QA
Approver role exists: whoever builds a dashboard moves it as far as QA Approval,
and a different person approves and publishes it. The API enforces this, and the
UI shows unavailable transitions as disabled with the required role named, rather
than hiding them.

## Roles

Three Dashboard Studio roles, plus Frappe's System Manager as superuser:

| Role | Read | Edit | Publish |
|---|---|---|---|
| Dashboard Studio Viewer | ✅ | — | — |
| Dashboard Studio Editor | ✅ | ✅ | — |
| Dashboard Studio QA Approver | ✅ | — | ✅ |
| System Manager | ✅ | ✅ | ✅ |

QA Approver has read access everywhere — approving what you cannot see is
meaningless — but is deliberately excluded from the write set. It approves; it
does not edit.

Roles ship as a fixture, so they exist on install/migrate.

### Not adopted

The six-role model in the Sophia prototype (Designer, Data Mapper, Metric Owner,
Administrator as separate roles) is **not** implemented. Editor covers designing
and mapping, and System Manager is the administrator. Only the approval role was
split out, because that is the one separation with a real control purpose.

## Change impact and version history

Before a change, the governance view reports what a dashboard contains and which
of its metrics are shared with other charts — a shared metric is flagged, because
changing it affects every chart using it. These counts come from real Link
fields, not estimates.

Change history uses Frappe's native `Version` records, enabled by `track_changes`
on the DS DocTypes. No bespoke versioning system exists, deliberately.

## Result validation

Migrated results are compared against their source before publication. Three
rules are enforced in both the arithmetic and the UI:

- **Accepted is never computed.** A difference becomes Accepted only when a
  person accepts it, always with a reason, and the reviewer is recorded.
- **Flagged is not Discrepancy.** A value that could not be compared is treated
  as more serious than one that compared unequal, because its true state is
  unknown, and it is styled distinctly.
- **Unknown is never coerced to zero.** A missing or unparsable value stays
  blank through storage and display; it is never shown or stored as `0`.
