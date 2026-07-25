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

    doc.status = to_status
    if to_status == PUBLISHED:
        doc.published_on = frappe.utils.now()
    doc.save()
    return {"dashboard": dashboard, "status": doc.status, "applied": label}


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
