"""Demo/seed data for Dashboard Studio.

Two datasets, deliberately different:

* **Path A — complete.** Migration project -> Confirmed mapping -> Approved
  metric -> chart -> a Match validation comparison -> a dashboard that reaches
  **Published through the real gate**. The last hop calls
  ``governance.advance_status``, so if ``publish_readiness`` would refuse, the
  seed fails loudly rather than writing a Published record the gate disagrees
  with. That is the whole point of seeding it: it proves the gate passes.

* **Path B — deliberately incomplete.** Draft metric, one chart with no metric
  at all, no validation. Its readiness chip reports two real, current blockers.

Safety rules, all four enforced here:

1. **Only DocTypes this app owns.** Every write is to a ``DS *`` DocType. The
   demo metric's ``source_doctype`` points at an existing DocType so the metric
   actually executes, but that is a Link value and a read — nothing outside
   ``DS *`` is created, modified or deleted.
2. **Everything is demo-marked** with the ``DEMO `` prefix, on a real field
   (see ``_DEMO_MARK``), never on a comment or a convention.
3. **Idempotent.** Every record is matched on its identifying fields and
   updated in place, so running twice produces the same eight-record set.
4. **Removal refuses anything not demo-marked.** ``remove_demo_data`` selects
   only marked records and re-checks each one immediately before deleting it.

How to run — no Bench needed for the second form:

    bench --site ucc.local execute dashboard_studio.demo.seed_demo_data
    bench --site ucc.local execute dashboard_studio.demo.remove_demo_data

    # or, from the browser, /app/system-console as System Manager:
    from dashboard_studio import demo; demo.seed_demo_data()
    from dashboard_studio import demo; demo.remove_demo_data()
    from dashboard_studio import demo; demo.remove_demo_data(dry_run=True)
"""

import frappe

from dashboard_studio.api import governance

DEMO_PREFIX = "DEMO "

# doctype -> the field that must start with DEMO_PREFIX for a record to count as
# demo data. Deletion order too: children before the records they point at.
_DEMO_MARK = {
    "DS Validation Comparison": "migration_project",
    "DS Chart": "chart_title",
    "DS Dashboard Section": "dashboard",
    "DS Dashboard": "dashboard_title",
    "DS Metric": "metric_name",
    "DS Data Mapping": "data_source",
    "DS Migration Project": "project_name",
    "DS Data Source": "source_name",
}

# The metric has to COUNT something real, or Path A cannot be walked end to end.
# First DocType present wins; User exists on every Frappe site, so the seed never
# depends on another app being installed.
_SOURCE_CANDIDATES = (("Student Applicant", "status"), ("User", "enabled"))


def _source_doctype():
    for doctype, field in _SOURCE_CANDIDATES:
        if frappe.db.exists("DocType", doctype):
            return doctype, field
    raise RuntimeError("No usable source DocType found for the demo metric.")


def _upsert(doctype, match, values, log):
    """Create or update one record, matched on ``match``. Returns its name."""
    existing = frappe.get_all(doctype, filters=match, fields=["name"])
    payload = dict(match)
    payload.update(values)
    if existing:
        doc = frappe.get_doc(doctype, existing[0]["name"])
        for key, value in payload.items():
            doc.set(key, value)
        doc.save()
        log.append(("updated", doctype, doc.name))
        return doc.name
    payload["doctype"] = doctype
    doc = frappe.get_doc(payload).insert()
    log.append(("created", doctype, doc.name))
    return doc.name


def seed_demo_data():
    """Write both demo paths. Safe to run repeatedly."""
    log = []
    today = frappe.utils.today()
    source_doctype, group_field = _source_doctype()

    data_source = _upsert(
        "DS Data Source",
        {"source_name": DEMO_PREFIX + "Metabase Export"},
        {"source_type": "Metabase", "is_active": 1,
         "connection_notes": "Demo data. Remove with dashboard_studio.demo.remove_demo_data."},
        log,
    )

    # ---------------------------------------------------------------- Path A
    project_a = _upsert(
        "DS Migration Project",
        {"project_name": DEMO_PREFIX + "Path A - Admissions Intake"},
        {"data_source": data_source, "status": "Ready to Publish",
         "notes": "Demo: complete migration, published through the real gate."},
        log,
    )
    _upsert(
        "DS Data Mapping",
        {"data_source": data_source, "external_table": "metabase_admissions_v"},
        {"external_field": "applicant_status", "target_doctype": source_doctype,
         "target_field": group_field, "mapping_status": "Confirmed", "confidence_score": 100},
        log,
    )
    metric_a = _upsert(
        "DS Metric",
        {"metric_name": DEMO_PREFIX + "Applicants by status"},
        {"status": "Approved", "source_doctype": source_doctype, "calculation_type": "Count",
         "value_field": "name", "group_by_field": group_field,
         # Block-by-default: only the two fields this metric actually names.
         "allowed_fields": group_field + "\nname",
         "evidence_level": "Direct Evidence", "refresh_frequency": "Daily",
         "description": "Demo metric. Counts " + source_doctype + " by " + group_field + "."},
        log,
    )
    dashboard_a = _upsert(
        "DS Dashboard",
        {"dashboard_title": DEMO_PREFIX + "Path A - Admissions Intake"},
        {"subcriterion": "4.1.1", "publish_target": "UCC Intelligence Platform", "is_active": 1,
         "description": "Demo dashboard, complete and publishable."},
        log,
    )
    chart_a = _upsert(
        "DS Chart",
        {"chart_title": DEMO_PREFIX + "Applicants by status", "dashboard": dashboard_a},
        {"chart_type": "Bar Chart", "metric": metric_a,
         "pos_x": 0, "pos_y": 0, "width": 6, "height": 4, "sort_order": "Highest first"},
        log,
    )

    # The comparison must be dated on or after the chart's last edit, or the gate
    # treats it as stale — which is correct, and why this is written last.
    comparison = _upsert(
        "DS Validation Comparison",
        {"migration_project": project_a, "chart": chart_a},
        {"comparison_date": today, "original_value": "1284", "new_value": "1284",
         "difference_pct": 0, "status": "Match",
         "accepted_reason": "Demo: figures agree exactly."},
        log,
    )
    _set_comparison_rows(comparison)

    # ---------------------------------------------------------------- Path B
    # Its OWN data source, not Path A's. DS Data Mapping belongs to a data
    # source, not to a project, so two projects sharing one source see each
    # other's mappings — Path A's canvas would show Path B's unconfirmed row and
    # read as unfinished. Real behaviour, documented in MIGRATION_PROJECT_
    # LIFECYCLE.md; the demo must not walk into it.
    source_b = _upsert(
        "DS Data Source",
        {"source_name": DEMO_PREFIX + "Survey Export"},
        {"source_type": "CSV", "is_active": 1,
         "connection_notes": "Demo data. Remove with dashboard_studio.demo.remove_demo_data."},
        log,
    )
    _upsert(
        "DS Migration Project",
        {"project_name": DEMO_PREFIX + "Path B - Student Satisfaction"},
        {"data_source": source_b, "status": "Mapping",
         "notes": "Demo: deliberately unfinished, so readiness has something to report."},
        log,
    )
    _upsert(
        "DS Data Mapping",
        {"data_source": source_b, "external_table": "metabase_survey_v"},
        {"external_field": "response_score", "target_doctype": source_doctype,
         "target_field": group_field, "mapping_status": "Suggested", "confidence_score": 60},
        log,
    )
    metric_b = _upsert(
        "DS Metric",
        {"metric_name": DEMO_PREFIX + "Survey responses"},
        {"status": "Draft", "source_doctype": source_doctype, "calculation_type": "Count",
         "value_field": "name", "group_by_field": group_field,
         "allowed_fields": group_field + "\nname",
         "description": "Demo metric, still Draft on purpose — it has not been approved."},
        log,
    )
    dashboard_b = _upsert(
        "DS Dashboard",
        {"dashboard_title": DEMO_PREFIX + "Path B - Student Satisfaction"},
        {"subcriterion": "2.4.2", "publish_target": "UCC Intelligence Platform", "status": "Draft",
         "is_active": 1,
         "description": "Demo dashboard, deliberately not ready to publish."},
        log,
    )
    _upsert(
        "DS Chart",
        {"chart_title": DEMO_PREFIX + "Survey responses", "dashboard": dashboard_b},
        {"chart_type": "Donut Chart", "metric": metric_b,
         "pos_x": 0, "pos_y": 0, "width": 6, "height": 4},
        log,
    )
    # No metric at all: the second blocker the readiness chip reports.
    _upsert(
        "DS Chart",
        {"chart_title": DEMO_PREFIX + "Placeholder, no metric yet", "dashboard": dashboard_b},
        {"chart_type": "KPI Card", "metric": None, "pos_x": 6, "pos_y": 0, "width": 3, "height": 3},
        log,
    )
    # Path B gets NO validation comparison on purpose.

    published = _publish_path_a(dashboard_a, log)
    frappe.db.commit()
    return {
        "records": [{"action": a, "doctype": d, "name": n} for a, d, n in log],
        "path_a_dashboard": dashboard_a,
        "path_a_status": published,
        "path_b_dashboard": dashboard_b,
        "path_b_blockers": [b["summary"] for b in governance.publish_readiness(dashboard_b)["blockers"]],
        "source_doctype": source_doctype,
    }


def _set_comparison_rows(comparison):
    """Replace the comparison's rows. Wholesale, so a re-run cannot double them."""
    doc = frappe.get_doc("DS Validation Comparison", comparison)
    doc.set("comparison_rows", [])
    for label, value in (("Accepted", "812"), ("Pending", "301"), ("Withdrawn", "171")):
        doc.append("comparison_rows", {
            "group_label": label, "original_value": value, "new_value": value,
            "difference": "0", "difference_pct": "0", "status": "Match",
        })
    doc.save()


def _publish_path_a(dashboard, log):
    """Take Path A to Published THROUGH the gate, not around it.

    Seeding sets the intermediate stages, because those carry no rules worth
    proving. The final hop is a real ``advance_status`` call, so a Path A that
    ``publish_readiness`` would refuse raises here instead of quietly writing a
    Published record the gate disagrees with.
    """
    doc = frappe.get_doc("DS Dashboard", dashboard)
    # .get, not .status: a freshly inserted record may have no status at all, and
    # Path A deliberately does not seed one so a re-run cannot demote it.
    if doc.get("status") == governance.PUBLISHED:
        return governance.PUBLISHED
    doc.status = governance.QA_APPROVAL
    doc.save()
    result = governance.advance_status(dashboard, governance.PUBLISHED)
    log.append(("published", "DS Dashboard", dashboard))
    return result["status"]


def _is_demo(doctype, row):
    field = _DEMO_MARK[doctype]
    return str(row.get(field) or "").startswith(DEMO_PREFIX)


def remove_demo_data(dry_run=False):
    """Delete every demo-marked record, and refuse to touch anything else.

    ponytail: reads each DocType in full and filters in Python rather than using
    a ``like`` filter. These tables are small and this runs by hand; the gain is
    that the mark is checked by the same code that deletes, with no query
    dialect in between. Add a filter if a site ever has thousands of DS records.
    """
    deleted, refused = [], []
    for doctype, field in _DEMO_MARK.items():
        for row in frappe.get_all(doctype, fields=["name", field]):
            if not _is_demo(doctype, row):
                continue
            # Re-read and re-check: the selection above and the delete below must
            # not be able to disagree about what is demo data.
            fresh = frappe.get_doc(doctype, row["name"])
            if not str(fresh.get(field) or "").startswith(DEMO_PREFIX):
                refused.append({"doctype": doctype, "name": row["name"],
                                "reason": f"{field} is not demo-marked"})
                continue
            if not dry_run:
                frappe.delete_doc(doctype, row["name"])
            deleted.append({"doctype": doctype, "name": row["name"]})
    if not dry_run:
        frappe.db.commit()
    return {"deleted": deleted, "refused": refused, "dry_run": bool(dry_run)}
