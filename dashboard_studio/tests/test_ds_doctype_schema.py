"""Schema-shape tests for the 11 DS-prefixed DocTypes.

These check that each DocType JSON on disk matches the agreed spec: valid JSON,
correct module/istable, every expected field present with the exact fieldtype /
Select options / reqd / unique / default, and every Link/Table target resolving
to one of these 11 DocTypes or a core Frappe doctype (DocType, User).

The EXPECTED values below are typed independently from the spec so this is a real
cross-check of the generated JSON, not a re-read of the generator.

NOT VERIFIED HERE: live installability. `bench migrate` has not been run — no
staging/Bench access in this session. Confirming the DocTypes actually install
and migrate on a real Frappe site is a separate follow-up task.
"""

import json
import os
import unittest

from dashboard_studio.edutrust import SUBCRITERIA

DOCTYPE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "dashboard_studio", "doctype"
)
CORE_DOCTYPES = {"DocType", "User"}

# name -> (istable, autoname_or_None, title_field_or_None, {fieldname: expected})
# expected: {"fieldtype", optional "options", "reqd", "unique", "default", "depends_on"}
FILTER_FIELDS = {
    "fieldname": {"fieldtype": "Data", "reqd": 1},
    "operator": {"fieldtype": "Select", "options": "=\n!=\n>\n<\n>=\n<=\nin\nnot in\nlike\nbetween"},
    "value": {"fieldtype": "Data"},
    "filter_type": {"fieldtype": "Select", "options": "Static\nDynamic", "default": "Static"},
}

SPEC = {
    "DS Dashboard": (0, "field:dashboard_title", "dashboard_title", {
        "dashboard_title": {"fieldtype": "Data", "reqd": 1, "unique": 1},
        # Four-stage governance workflow, plus Archived for superseded dashboards.
        "status": {"fieldtype": "Select",
                   "options": "Draft\nTechnical Review\nQA Approval\nPublished\nArchived",
                   "default": "Draft"},
        "description": {"fieldtype": "Small Text"},
        # Codes only, never labels: a Select stores the chosen option verbatim,
        # so a label in the option would copy Sophia's title into every record.
        # Pinned to edutrust.SUBCRITERIA so the two can never drift apart.
        "subcriterion": {"fieldtype": "Select",
                         "options": "\n".join([""] + sorted(SUBCRITERIA))},
        "publish_target": {"fieldtype": "Select", "options": "UCC Intelligence Platform\nSophia\nOther"},
        "reviewer": {"fieldtype": "Link", "options": "User"},
        "review_comments": {"fieldtype": "Small Text"},
        "published_on": {"fieldtype": "Datetime", "read_only": 1},
        "is_active": {"fieldtype": "Check", "default": "1"},
    }),
    "DS Dashboard Section": (0, None, "section_title", {
        "dashboard": {"fieldtype": "Link", "options": "DS Dashboard", "reqd": 1},
        "section_title": {"fieldtype": "Data", "reqd": 1},
        "sort_order": {"fieldtype": "Int", "default": "0"},
        "is_collapsed_default": {"fieldtype": "Check"},
    }),
    "DS Chart": (0, None, "chart_title", {
        "chart_title": {"fieldtype": "Data", "reqd": 1},
        "dashboard": {"fieldtype": "Link", "options": "DS Dashboard", "reqd": 1},
        "section": {"fieldtype": "Link", "options": "DS Dashboard Section"},
        "chart_type": {"fieldtype": "Select", "options": "\n".join([
            "KPI Card", "Bar Chart", "Line Chart", "Donut Chart", "Table",
            "Trend Chart", "Gauge", "Funnel", "Lifecycle", "Flow", "Matrix",
            "Radar", "Decision Diagram", "Network Diagram",
            "Reconciliation Diagram", "Maturity Ladder", "Risk Matrix",
        ])},
        "metric": {"fieldtype": "Link", "options": "DS Metric", "reqd": 1},
        "pos_x": {"fieldtype": "Int"},
        "pos_y": {"fieldtype": "Int"},
        "width": {"fieldtype": "Int", "default": "4"},
        "height": {"fieldtype": "Int", "default": "3"},
        "description": {"fieldtype": "Small Text"},
        "drill_down_enabled": {"fieldtype": "Check"},
        # Display order for this chart's rows. "Ascending" is what the engine has
        # always produced, so it is the default and existing charts are unchanged.
        "sort_order": {"fieldtype": "Select", "default": "Ascending",
                       "options": "\n".join(["Ascending", "Descending", "Highest first"])},
        "chart_filters": {"fieldtype": "Table", "options": "DS Chart Filter"},
    }),
    "DS Chart Filter": (1, None, None, FILTER_FIELDS),
    "DS Metric": (0, "field:metric_name", "metric_name", {
        "metric_name": {"fieldtype": "Data", "reqd": 1, "unique": 1},
        "status": {"fieldtype": "Select", "options": "Draft\nApproved\nDeprecated", "default": "Draft"},
        "source_doctype": {"fieldtype": "Link", "options": "DocType", "reqd": 1},
        "calculation_type": {"fieldtype": "Select", "options": "Count\nSum\nAverage\nPercentage\nCustom"},
        "value_field": {"fieldtype": "Data"},
        "group_by_field": {"fieldtype": "Data"},
        "allowed_fields": {"fieldtype": "Small Text"},
        "numerator_metric": {"fieldtype": "Link", "options": "DS Metric"},
        "denominator_metric": {"fieldtype": "Link", "options": "DS Metric"},
        "metric_filters": {"fieldtype": "Table", "options": "DS Metric Filter"},
        "description": {"fieldtype": "Small Text"},
        "refresh_frequency": {"fieldtype": "Select", "options": "Real-time\nHourly\nDaily\nWeekly"},
        "known_limitations": {"fieldtype": "Small Text"},
        "evidence_level": {"fieldtype": "Select", "options": "\n".join([
            "Direct Evidence", "Calculated Evidence", "Proxy Indicator",
            "Data Completeness", "Unsupported",
        ])},
    }),
    "DS Metric Filter": (1, None, None, FILTER_FIELDS),
    "DS Data Source": (0, "field:source_name", "source_name", {
        "source_name": {"fieldtype": "Data", "reqd": 1, "unique": 1},
        "source_type": {"fieldtype": "Select", "options": "Metabase\nCSV\nOther"},
        "connection_notes": {"fieldtype": "Small Text"},
        "is_active": {"fieldtype": "Check", "default": "1"},
    }),
    "DS Data Mapping": (0, None, None, {
        "data_source": {"fieldtype": "Link", "options": "DS Data Source", "reqd": 1},
        "external_table": {"fieldtype": "Data", "reqd": 1},
        "external_field": {"fieldtype": "Data"},
        "target_doctype": {"fieldtype": "Link", "options": "DocType"},
        "target_field": {"fieldtype": "Data"},
        "mapping_status": {"fieldtype": "Select", "options": "Suggested\nConfirmed\nRejected\nMissing", "default": "Suggested"},
        "confidence_score": {"fieldtype": "Percent"},
        "notes": {"fieldtype": "Small Text"},
    }),
    "DS Migration Project": (0, "field:project_name", "project_name", {
        "project_name": {"fieldtype": "Data", "reqd": 1, "unique": 1},
        "data_source": {"fieldtype": "Link", "options": "DS Data Source", "reqd": 1},
        "status": {"fieldtype": "Select", "options": "Not Started\nMapping\nValidating\nReady to Publish\nPublished", "default": "Not Started"},
        "target_dashboard": {"fieldtype": "Link", "options": "DS Dashboard"},
        "notes": {"fieldtype": "Small Text"},
        "canvas_nodes": {"fieldtype": "Table", "options": "DS Canvas Node"},
        "source_queries": {"fieldtype": "Table", "options": "DS Migration Source Query"},
    }),
    "DS Migration Source Query": (1, None, None, {
        "source_sql": {"fieldtype": "Code", "reqd": 1},
        "supported": {"fieldtype": "Check"},
        "reasons": {"fieldtype": "Small Text"},
    }),
    "DS Canvas Node": (1, None, None, {
        "node_id": {"fieldtype": "Data", "reqd": 1},
        "node_type": {"fieldtype": "Select", "options": "Source Table\nTarget DocType", "reqd": 1},
        "pos_x": {"fieldtype": "Int"},
        "pos_y": {"fieldtype": "Int"},
    }),
    "DS Validation Comparison": (0, None, None, {
        "migration_project": {"fieldtype": "Link", "options": "DS Migration Project"},
        "chart": {"fieldtype": "Link", "options": "DS Chart"},
        "comparison_date": {"fieldtype": "Date", "default": "Today"},
        "original_value": {"fieldtype": "Data"},
        "new_value": {"fieldtype": "Data"},
        "difference_pct": {"fieldtype": "Percent"},
        "status": {"fieldtype": "Select", "options": "Match\nDiscrepancy\nAccepted\nFlagged", "default": "Match"},
        "accepted_reason": {"fieldtype": "Small Text", "depends_on": "eval:doc.status=='Accepted'"},
        "evidence": {"fieldtype": "Attach"},
        "reviewed_by": {"fieldtype": "Link", "options": "User"},
        "comparison_rows": {"fieldtype": "Table", "options": "DS Validation Row"},
    }),
    "DS Validation Row": (1, None, None, {
        "group_label": {"fieldtype": "Data", "reqd": 1},
        "original_value": {"fieldtype": "Data"},
        "new_value": {"fieldtype": "Data"},
        # Data, not Float/Percent: an incomparable group has NO difference, and a
        # numeric field would store 0 — the coercion comparison.py exists to avoid.
        "difference": {"fieldtype": "Data"},
        "difference_pct": {"fieldtype": "Data"},
        # No "Accepted": acceptance is recorded once per run, on the parent.
        "status": {"fieldtype": "Select", "options": "Match\nDiscrepancy\nFlagged"},
        "reason": {"fieldtype": "Small Text"},
    }),
}

FLAG_KEYS = ("reqd", "unique", "read_only", "default", "depends_on", "options")


def _scrub(name):
    return name.lower().replace(" ", "_")


def _load(name):
    slug = _scrub(name)
    with open(os.path.join(DOCTYPE_DIR, slug, slug + ".json")) as fh:
        return json.load(fh)


class TestDSDoctypeSchema(unittest.TestCase):
    def test_every_spec_doctype_matches_json(self):
        known = set(SPEC) | CORE_DOCTYPES
        for name, (istable, autoname, title_field, fields) in SPEC.items():
            doc = _load(name)
            self.assertEqual(doc["name"], name)
            self.assertEqual(doc["module"], "Dashboard Studio")
            self.assertEqual(doc["istable"], istable, f"{name} istable")
            self.assertEqual(doc.get("autoname"), autoname, f"{name} autoname")
            self.assertEqual(doc.get("title_field"), title_field, f"{name} title_field")

            by_name = {f["fieldname"]: f for f in doc["fields"]}
            # Exact field set — no missing, no extras.
            self.assertEqual(set(by_name), set(fields), f"{name} field set")
            self.assertEqual(doc["field_order"], list(by_name), f"{name} field_order")

            for fieldname, expected in fields.items():
                actual = by_name[fieldname]
                self.assertEqual(actual["fieldtype"], expected["fieldtype"], f"{name}.{fieldname} type")
                for key in FLAG_KEYS:
                    if key in expected:
                        self.assertEqual(actual.get(key), expected[key], f"{name}.{fieldname} {key}")
                    else:
                        self.assertNotIn(key, actual, f"{name}.{fieldname} unexpected {key}")
                # Link/Table targets must resolve.
                if actual["fieldtype"] in ("Link", "Table"):
                    self.assertIn(actual["options"], known, f"{name}.{fieldname} -> {actual['options']}")

    def test_permissions_are_editor_viewer_and_qa_approver(self):
        # Editor has full CRUD; Viewer and QA Approver are read-only. QA Approver
        # must be able to READ what it approves, but must never gain write —
        # separating approval from editing is the reason the role exists.
        for name in SPEC:
            perms = {p["role"]: p for p in _load(name)["permissions"]}
            self.assertEqual(
                set(perms),
                {
                    "Dashboard Studio Editor",
                    "Dashboard Studio Viewer",
                    "Dashboard Studio QA Approver",
                },
                f"{name} roles",
            )
            editor = perms["Dashboard Studio Editor"]
            for flag in ("read", "write", "create", "delete"):
                self.assertEqual(editor.get(flag), 1, f"{name} editor {flag}")
            for read_only in ("Dashboard Studio Viewer", "Dashboard Studio QA Approver"):
                block = perms[read_only]
                self.assertEqual(block.get("read"), 1, f"{name} {read_only} read")
                for flag in ("write", "create", "delete"):
                    self.assertNotEqual(block.get(flag), 1, f"{name} {read_only} must not {flag}")


if __name__ == "__main__":
    unittest.main()
