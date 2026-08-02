"""Governance & Publish: move a dashboard through its approval stages.

Four-stage workflow, Draft -> Technical Review -> QA Approval -> Published,
with Archived retained for superseded dashboards.

The point of the QA Approver role is SEPARATION OF DUTIES: an Editor can build a
dashboard and move it up to QA Approval, but cannot publish their own work. Only
a QA Approver (or System Manager) publishes.

Version history is NOT reimplemented here — Frappe's native Version records,
already enabled via track_changes on the DS DocTypes, are surfaced instead.
"""

import frappe

from dashboard_studio.api.studio import DS_READ_ROLES
from dashboard_studio.edutrust import SUBCRITERIA

QA_ROLE = "Dashboard Studio QA Approver"
EDITOR_ROLE = "Dashboard Studio Editor"
SUPERUSER = "System Manager"

DRAFT = "Draft"
TECHNICAL_REVIEW = "Technical Review"
QA_APPROVAL = "QA Approval"
PUBLISHED = "Published"
ARCHIVED = "Archived"

STAGES = (DRAFT, TECHNICAL_REVIEW, QA_APPROVAL, PUBLISHED)

# to_status -> (label, roles allowed to make this move)
# Publishing is the only transition an Editor cannot make on their own work.
_TRANSITIONS = {
    TECHNICAL_REVIEW: ("Submit for technical review", (EDITOR_ROLE, SUPERUSER)),
    QA_APPROVAL: ("Pass technical review", (EDITOR_ROLE, SUPERUSER)),
    PUBLISHED: ("Approve and publish", (QA_ROLE, SUPERUSER)),
    DRAFT: ("Return for correction", (EDITOR_ROLE, QA_ROLE, SUPERUSER)),
    ARCHIVED: ("Archive", (EDITOR_ROLE, SUPERUSER)),
}

# Which stages each status may move to.
_ALLOWED_FROM = {
    DRAFT: (TECHNICAL_REVIEW,),
    TECHNICAL_REVIEW: (QA_APPROVAL, DRAFT),
    QA_APPROVAL: (PUBLISHED, DRAFT),
    PUBLISHED: (ARCHIVED, DRAFT),
    ARCHIVED: (DRAFT,),
}


@frappe.whitelist()
def get_governance(dashboard: str):
    """Stage, the moves available to *this* user, impact and version history."""
    frappe.only_for(DS_READ_ROLES)
    doc = frappe.get_doc("DS Dashboard", dashboard)
    status = doc.status or DRAFT

    return {
        "dashboard": dashboard,
        "dashboard_title": doc.dashboard_title,
        "status": status,
        "stages": list(STAGES),
        "transitions": _available_transitions(status),
        "impact": get_change_impact(dashboard),
        "versions": get_version_history(dashboard),
        "published_on": doc.get("published_on"),
        "reviewer": doc.get("reviewer"),
    }


def _available_transitions(status):
    """Every legal next stage, each marked with whether this user may take it.

    Moves the user cannot make are still returned, so the UI can show them
    disabled with a reason rather than hiding the workflow.
    """
    roles = set(frappe.get_roles())
    out = []
    for target in _ALLOWED_FROM.get(status, ()):
        label, allowed = _TRANSITIONS[target]
        out.append(
            {
                "to": target,
                "label": label,
                "allowed": bool(roles & set(allowed)),
                "requires": list(allowed),
            }
        )
    return out


@frappe.whitelist()
def advance_status(dashboard: str, to_status: str):
    """Move a dashboard to another stage, enforcing the transition's role."""
    frappe.only_for(DS_READ_ROLES)  # any DS user may attempt; the move itself is gated below
    doc = frappe.get_doc("DS Dashboard", dashboard)
    current = doc.status or DRAFT

    if to_status not in _ALLOWED_FROM.get(current, ()):
        frappe.throw(f"Cannot move from {current} to {to_status}.")

    label, allowed = _TRANSITIONS[to_status]
    if not (set(frappe.get_roles()) & set(allowed)):
        frappe.throw(
            f"'{label}' requires one of: {', '.join(allowed)}. "
            "Publishing is separated from editing on purpose."
        )

    if to_status == PUBLISHED:
        blockers = publish_readiness(dashboard)["blockers"]
        if blockers:
            frappe.throw(" ".join(b["message"] for b in blockers))

    doc.status = to_status
    if to_status == PUBLISHED:
        doc.published_on = frappe.utils.now()
    doc.save()
    return {"dashboard": dashboard, "status": doc.status, "applied": label}


#: Comparison outcomes that count as a chart having been checked. Discrepancy and
#: Flagged do not — Flagged especially, since it means a value could not be
#: compared at all, and unknown is not the same as agreed.
_PASSING_COMPARISONS = ("Match", "Accepted")


def _plural(count, noun):
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


@frappe.whitelist()
def publish_readiness(dashboard: str):
    """Everything standing between this dashboard and Published, as facts.

    ONE DEFINITION, TWO PRESENTATIONS. ``advance_status`` throws on the blockers
    this returns; ``get_studio_dashboard`` displays them. **Do not add a second,
    cheaper computation for the display path.** A readiness indicator that
    disagrees with the gate would show "ready" and then refuse — worse than
    either failure on its own, because it teaches people to distrust the
    indicator rather than fix the dashboard. It is also exactly the fault
    recorded in ``docs/SOPHIA_FAULT_PATTERN.md``: the same question answered by
    two code paths, agreeing only until one of them is edited.

    Three queries regardless of chart count. Every refusal names the records
    responsible, because "not ready" without the list is another dead end.
    """
    frappe.only_for(DS_READ_ROLES)
    doc = frappe.get_doc("DS Dashboard", dashboard)
    blockers = []

    # Scope is optional while authoring and required to publish: an unscoped
    # dashboard has nowhere to go on the Sophia side, and a code Sophia does not
    # know does not fail there — it falls back to the criterion's default section
    # and renders the wrong subcriterion's data under the right heading.
    scope = (doc.get("subcriterion") or "").strip()
    if not scope:
        blockers.append({
            "rule": "scope",
            # `summary` is the short form the toolbar chip shows; `message` is the
            # full sentence the gate throws and Governance lists. Same facts.
            "summary": "no subcriterion set",
            "charts": [],
            "message": (
                "This dashboard has no EduTrust subcriterion, so it cannot be "
                "published — there is no section for it on the receiving platform."
            ),
        })
    elif scope not in SUBCRITERIA:
        blockers.append({
            "rule": "scope_unknown",
            "summary": f"subcriterion \u201c{scope}\u201d not recognised",
            "charts": [],
            "message": (
                f"Unknown EduTrust subcriterion '{scope}'. It is not one of the "
                f"{len(SUBCRITERIA)} codes the receiving platform serves, so the "
                "dashboard would be routed to the wrong section without any error."
            ),
        })

    charts = frappe.get_all(
        "DS Chart",
        filters={"dashboard": dashboard},
        fields=["name", "chart_title", "metric", "modified"],
    )

    def label(chart):
        return chart.get("chart_title") or chart.get("name")

    # Both chart rules refuse rather than exclude. Publishing with the offending
    # charts silently dropped would produce something that looks complete and is
    # not, with nobody told — worse on audit evidence than visibly refusing.
    unlinked = sorted(label(c) for c in charts if not c.get("metric"))
    if unlinked:
        blockers.append({
            "rule": "chart_without_metric",
            "summary": _plural(len(unlinked), "chart") + " with no metric",
            "charts": unlinked,
            "message": (
                "These charts have no metric, so there is nothing to publish for "
                "them: " + ", ".join(unlinked) + ". Link a metric or delete the chart."
            ),
        })

    linked = [c for c in charts if c.get("metric")]
    passing_by_chart = {}
    if linked:
        # One batched read, not one per chart: this runs on every dashboard load
        # now, not only at the moment someone presses publish.
        for row in frappe.get_all(
            "DS Validation Comparison",
            filters={"chart": ["in", [c["name"] for c in linked]]},
            fields=["chart", "status", "comparison_date"],
        ):
            if row.get("status") in _PASSING_COMPARISONS:
                passing_by_chart.setdefault(row["chart"], []).append(row)

    def is_current(chart):
        passing = passing_by_chart.get(chart["name"], [])
        if not passing:
            return False
        # A pass from before the chart was last edited proves nothing about it now.
        edited = frappe.utils.getdate(chart.get("modified"))
        return any(frappe.utils.getdate(r.get("comparison_date")) >= edited for r in passing)

    # Only charts that HAVE a metric are checked for validation — an unlinked
    # chart is already named above, and naming it twice reads as two problems.
    unchecked = sorted(label(c) for c in linked if not is_current(c))
    if unchecked:
        blockers.append({
            "rule": "chart_not_validated",
            "summary": _plural(len(unchecked), "chart") + " not validated since the last edit",
            "charts": unchecked,
            "message": (
                "These charts have no validation newer than their last edit: "
                + ", ".join(unchecked)
                + ". Run each in the Validation Centre and resolve it to Match, or "
                "accept the difference with a reason, before publishing."
            ),
        })

    return {
        "publishable": not blockers,
        "blockers": blockers,
        "charts_total": len(charts),
        "charts_ready": sum(1 for c in linked if is_current(c)),
        "scope_set": bool(scope and scope in SUBCRITERIA),
    }


@frappe.whitelist()
def get_change_impact(dashboard: str):
    """What this dashboard contains, and which metrics are shared elsewhere.

    Computed from real Link fields, so "used by N charts" is a fact rather than
    an estimate. Only genuinely derivable counts are reported.
    """
    frappe.only_for(DS_READ_ROLES)
    charts = frappe.get_all(
        "DS Chart", filters={"dashboard": dashboard}, fields=["name", "chart_title", "metric"]
    )
    sections = frappe.db.count("DS Dashboard Section", {"dashboard": dashboard})

    shared = []
    for metric in sorted({c.get("metric") for c in charts if c.get("metric")}):
        total = frappe.db.count("DS Chart", {"metric": metric})
        if total > 1:
            shared.append({"metric": metric, "used_by_charts": total})

    return {
        "charts": len(charts),
        "sections": sections,
        "metrics": len({c.get("metric") for c in charts if c.get("metric")}),
        # Metrics this dashboard shares with others — changing one affects all.
        "shared_metrics": shared,
    }


@frappe.whitelist()
def get_version_history(dashboard: str, limit: int = 10):
    """Frappe's native Version records for this dashboard.

    track_changes is already enabled on the DS DocTypes, so change history exists
    without a bespoke versioning system — this surfaces it rather than rebuilding it.
    """
    frappe.only_for(DS_READ_ROLES)
    return frappe.get_all(
        "Version",
        filters={"ref_doctype": "DS Dashboard", "docname": dashboard},
        fields=["name", "owner", "creation"],
        order_by="creation desc",
        limit=limit,
    )
