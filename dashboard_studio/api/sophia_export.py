"""Export a publish-ready dashboard as JSON, for a human to apply by hand.

This is option 2 of ``docs/PUBLISH_TO_SOPHIA_DESIGN.md`` §3, and deliberately the
weakest of the three: **it generates and displays, and does nothing else.** It
does not write to the Custom HTML Block, does not create a Server Script, does
not touch the Sophia repo, and has no automation behind it. Its whole value is
that it forces the contract to be concrete before anyone commits to option 1.

JSON, never JavaScript. §3 argues that emitting into ``CONFIG`` /
``LIVE_VISUAL_EXPANSION`` means emitting JS source, where one unescaped chart
title is stored XSS in every viewer's browser. Everything below is produced with
``json.dumps``, so the artefact is data at every point and the person applying it
is the one who decides how it enters a JS file.

Three refusals, all before anything is generated, all naming what is wrong:

1. the dashboard is not publish-ready — reusing ``governance.publish_readiness``,
   never a second cheaper check (see that function's docstring);
2. its subcriterion is missing or is not one of the codes ``edutrust.SUBCRITERIA``
   serves;
3. a chart's type has no Sophia plugin — because Sophia's silent bar-chart
   fallback would otherwise draw it as something it is not.
"""

import json

import frappe

from dashboard_studio import sophia
from dashboard_studio.api import governance
from dashboard_studio.api.studio import DS_READ_ROLES
from dashboard_studio.edutrust import SUBCRITERIA

# What this export cannot express, stated inside the artefact rather than only in
# a design doc — whoever pastes it is the person who needs to know.
_UNRESOLVED = [
    "Sophia binds a chart to its data BY POSITION: metricRows() gives chart i a "
    "rotating five-metric window from the Server Script's metrics[] array. The "
    "`metric` recorded against each chart below therefore CANNOT be expressed in "
    "the Sophia contract as it stands. Applying this export sets titles, types "
    "and order — it does not make any chart plot its own metric. See "
    "docs/PUBLISH_TO_SOPHIA_DESIGN.md §2.",
    "The numbers still come from the hand-maintained Server Script for this "
    "criterion. Nothing here changes, replaces or verifies them.",
]


def _safe_json(payload):
    """json.dumps, then escape the characters that let JSON escape its container.

    Plain json.dumps leaves ``</script>`` intact, so a chart titled
    ``</script><img onerror=…>`` breaks out the moment this artefact is pasted
    into JAVASCRIPT.js — the precise failure ``docs/PUBLISH_TO_SOPHIA_DESIGN.md``
    §3 raises against emitting into a JS blob. ``\\u003c`` and friends are ordinary
    JSON string escapes, so the document stays valid JSON and round-trips to the
    identical text; only its ability to terminate a script tag is removed.

    U+2028/U+2029 are included because they are legal in JSON strings and are
    line terminators in JavaScript — valid JSON that is a syntax error once
    pasted into JS.
    """
    out = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)
    for char, escaped in (
        ("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"),
        ("\u2028", "\\u2028"), ("\u2029", "\\u2029"),
    ):
        out = out.replace(char, escaped)
    return out


@frappe.whitelist()
def export_dashboard(dashboard: str):
    """The artefact, plus the refusals that stopped it being produced.

    Always returns; never throws. A refusal is a result the UI has to show, and
    a thrown exception would be a dead end for the caller with no artefact and
    no list of what to fix.
    """
    frappe.only_for(DS_READ_ROLES)
    doc = frappe.get_doc("DS Dashboard", dashboard)
    refusals = []

    # 1. The publish gate. ONE definition — the same call advance_status makes.
    readiness = governance.publish_readiness(dashboard)
    for blocker in readiness["blockers"]:
        refusals.append({"rule": blocker["rule"], "message": blocker["message"]})

    # 2. The subcriterion, checked against the live list rather than a copy.
    scope = (doc.get("subcriterion") or "").strip()
    if scope and scope not in SUBCRITERIA:
        # publish_readiness already refuses this; keep it explicit anyway so the
        # export's own contract does not depend on the gate's rule set.
        refusals.append({
            "rule": "scope_unknown",
            "message": f"'{scope}' is not one of the {len(SUBCRITERIA)} EduTrust "
                       "subcriteria the receiving platform serves.",
        })

    charts = frappe.get_all(
        "DS Chart",
        filters={"dashboard": dashboard},
        fields=["name", "chart_title", "chart_type", "metric", "section",
                "description", "pos_x", "pos_y", "width", "height", "sort_order"],
        order_by="pos_y asc, pos_x asc",
    )

    # 3. Chart types Sophia cannot draw. Refuse rather than substitute: Sophia
    #    falls back to `bar` without erroring, so a substitution here would be
    #    invisible on both sides.
    for chart in charts:
        reason = sophia.refusal_for(chart.get("chart_type"))
        if reason:
            refusals.append({
                "rule": "chart_type_unsupported",
                "message": f"“{chart.get('chart_title')}” is a "
                           f"{chart.get('chart_type')}. {reason} "
                           "See docs/CHART_TYPE_MAPPING.md.",
            })

    if refusals:
        return {"ok": False, "dashboard": dashboard, "refusals": refusals, "artefact": None}

    artefact = _build(doc, scope, charts)
    return {
        "ok": True,
        "dashboard": dashboard,
        "refusals": [],
        "artefact": artefact,
        # Pretty-printed here rather than in the browser so what is displayed and
        # what a test asserts on are the same string.
        "json": _safe_json(artefact),
    }


def _build(doc, scope, charts):
    criterion = scope.split(".")[0]
    sections = frappe.get_all(
        "DS Dashboard Section",
        filters={"dashboard": doc.name},
        fields=["name", "section_title", "sort_order"],
        order_by="sort_order asc",
    )
    metric_names = sorted({c["metric"] for c in charts if c.get("metric")})
    metrics = frappe.get_all(
        "DS Metric",
        filters={"name": ["in", metric_names]} if metric_names else {"name": ["in", [""]]},
        fields=["name", "metric_name", "status", "source_doctype", "calculation_type",
                "group_by_field", "value_field"],
    )
    by_name = {m["name"]: m for m in metrics}

    def section_of(chart):
        for section in sections:
            if section["name"] == chart.get("section"):
                return section["section_title"]
        return "default"

    visuals = []
    for index, chart in enumerate(charts):
        visuals.append({
            "id": chart["name"],
            "title": chart.get("chart_title"),
            "type": sophia.plugin_for(chart.get("chart_type")),
            "description": chart.get("description") or "",
            # `i` is the positional index Sophia binds data by. Emitted so the
            # order is at least explicit, NOT because it selects the metric.
            "i": index,
            "enabled": True,
            "section": section_of(chart),
        })

    return {
        "artefact_version": 1,
        "generated_by": "Dashboard Studio export_dashboard (manual application)",
        "generated_on": frappe.utils.now(),
        "dashboard": {
            "name": doc.name,
            "title": doc.get("dashboard_title"),
            "status": doc.get("status"),
            "description": doc.get("description") or "",
            "publish_target": doc.get("publish_target"),
        },
        "criterion": {
            "id": criterion,
            "subcriterion": scope,
            "subcriterion_title": SUBCRITERIA[scope],
        },
        # The two Sophia structures, as data. Applying them is a human step.
        "config_fragment": {
            "subcriteria": [[scope, SUBCRITERIA[scope]]],
            "sections": {s["section_title"]: [] for s in sections} or {"default": []},
            "defaultSection": (sections[0]["section_title"] if sections else "default"),
        },
        "live_visual_expansion": visuals,
        # What each chart is SUPPOSED to plot. Carried so a reviewer can check
        # what Sophia actually drew against what was approved — see _UNRESOLVED.
        "expected_metrics": [
            {
                "chart": c["name"],
                "chart_title": c.get("chart_title"),
                "metric": c.get("metric"),
                "metric_status": (by_name.get(c.get("metric")) or {}).get("status"),
                "source_doctype": (by_name.get(c.get("metric")) or {}).get("source_doctype"),
                "calculation_type": (by_name.get(c.get("metric")) or {}).get("calculation_type"),
                "group_by_field": (by_name.get(c.get("metric")) or {}).get("group_by_field"),
            }
            for c in charts
        ],
        "unresolved": list(_UNRESOLVED),
    }
