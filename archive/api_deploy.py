"""Deploy check: what this app ships versus what the site actually has.

A site whose database is behind the code is invisible from both directions — the
app looks current because its Python *is* current, and the site looks healthy
because nothing errors until someone writes a field that does not exist yet. A
39-commit gap went unnoticed exactly that way.

Read-only, and a diagnostic rather than a feature: it reports the gap and names
the fix, it does not migrate anything.
"""

import json
import os

import frappe

from dashboard_studio.api.studio import DS_READ_ROLES

_DOCTYPE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard_studio", "doctype"
)

# What is worth comparing. Layout and label churn is noise; these three are what
# actually break a write when the site is behind.
_COMPARED = ("fieldtype", "options", "reqd")


def _shipped_doctypes():
    """Every DocType JSON this app ships, as (name, fields)."""
    for folder in sorted(os.listdir(_DOCTYPE_DIR)):
        path = os.path.join(_DOCTYPE_DIR, folder, folder + ".json")
        if os.path.exists(path):
            with open(path) as handle:
                shipped = json.load(handle)
            yield shipped["name"], shipped.get("fields", [])


@frappe.whitelist()
def deploy_check():
    """Compare shipped DocType JSON against installed metadata."""
    frappe.only_for(DS_READ_ROLES)
    absent, missing, differs, total = [], [], [], 0

    for name, fields in _shipped_doctypes():
        total += 1
        if not frappe.db.exists("DocType", name):
            absent.append(f"DocType not installed: {name}")
            continue
        meta = frappe.get_meta(name)
        for field in fields:
            fieldname = field.get("fieldname")
            if not fieldname:
                continue  # Section Break and friends carry no fieldname
            live = meta.get_field(fieldname)
            if live is None:
                missing.append(f"Field missing: {name}.{fieldname}")
                continue
            for key in _COMPARED:
                shipped_value, live_value = field.get(key) or "", getattr(live, key, None) or ""
                if str(shipped_value) != str(live_value):
                    differs.append(
                        f"Field differs: {name}.{fieldname}.{key} "
                        f"— ships {shipped_value!r}, site has {live_value!r}"
                    )

    issues = absent + missing + differs  # worst first: absent > missing > differs
    summary = (
        f"{total - len(absent)} of {total} DocTypes installed · "
        f"{len(missing)} fields missing · {len(differs)} fields differ"
    )
    if issues:
        summary += " · run bench migrate"
    return {"ok": not issues, "summary": summary, "issues": issues}
