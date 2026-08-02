"""Shared Insights v3 plumbing for the Metabase converter.

What is left of a much larger module. The SQL-paste path that used to live here
— create_insights_query, apply_insights_chart, the SELECT-only guard, the axis
picker — went to `archive/api_insights_sql_path.py` when the product narrowed to
the converter. Nothing imports it; it is kept because it was working code, not
because anything still calls it.

These pieces stay because `api/convert.py` and the workbook picker need them:
the v3 DocType names, the varchar(140) title clamp, the installed-and-permitted
check, and workbook resolution.

**Insights v3 only.** The v2 DocTypes still ship alongside v3, which is why
`_require_insights` tests for `Insights Query v3` specifically — checking for the
v2 name passes on a v3 site and writes an orphan nothing can open. The same fault
is why the Site DB check reads `Insights Data Source v3` and not the v2 table
that happens to hold a row of the same name.
"""

import frappe

from dashboard_studio.roles import DS_READ_ROLES

# The v3 DocTypes. Named once so the version assumption has a single home.
QUERY_DOCTYPE = "Insights Query v3"


WORKBOOK_DOCTYPE = "Insights Workbook"


# Insights manages this data source itself and points it at the site's own
# database, so a query written here reaches the same tables ERPNext uses. The
# NAME is unchanged from v2 — confirmed live, v3 lists exactly "Site DB" — but
# the DocType holding it is not: v3 resolves a query's data_source against
# "Insights Data Source v3", and both tables exist side by side on this site.
SITE_DB = "Site DB"


SOURCE_DOCTYPE = "Insights Data Source v3"


# Creating an Insights Query needs an Insights role, which a Dashboard Studio
# Editor does not automatically hold. Checked explicitly so the refusal names the
# missing role instead of surfacing as a bare permission error.
INSIGHTS_ROLES = ("Insights User", "Insights Admin")


# Every query this app creates lands in one workbook, created on first use.
# Queries are not loose objects in v3 — `workbook` is a required Link — and a
# workbook per query would litter the Insights sidebar with singletons.
WORKBOOK_TITLE = "Dashboard Studio"


# Insights Query v3.title is a Frappe Data field: varchar(140). Frappe refuses
# an over-long value with "Value too big" and aborts the insert, so the title is
# trimmed to fit rather than allowed to cost somebody their query.
MAX_TITLE_LENGTH = 140


# Metabase's base_type -> v3's data_type. Anything unlisted becomes String, which
# degrades safely: a String X axis is normal, and a String Y axis is refused by
# name below rather than charted.
BASE_TYPE_TO_DATA_TYPE = {
    "type/Integer": "Integer",
    "type/BigInteger": "Integer",
    "type/SmallInteger": "Integer",
    "type/Quantity": "Integer",
    "type/Float": "Decimal",
    "type/Decimal": "Decimal",
    "type/Number": "Decimal",
    "type/Date": "Date",
    "type/DateTime": "Datetime",
    "type/DateTimeWithTZ": "Datetime",
    "type/DateTimeWithLocalTZ": "Datetime",
    "type/Instant": "Datetime",
    "type/Time": "Time",
    "type/TimeWithTZ": "Time",
}


def clamp_title(name):
    """A title Insights will accept, or as much of one as fits.

    ``title`` is a Frappe Data field — varchar(140) — and Frappe refuses an
    over-long value with "Value too big", which aborts the whole insert. A title
    is cosmetic and a query is not, so this trims rather than letting a long name
    cost somebody their query.

    Real Metabase-compiled SQL is what surfaced this: its generated join aliases
    (``Quality Performance Actual Value Parameter Child_a3e4a16b``) are long
    enough that two or three of them blow the limit on their own.
    """
    name = " ".join(str(name or "").split())
    if len(name) <= MAX_TITLE_LENGTH:
        return name
    return name[: MAX_TITLE_LENGTH - 1].rstrip() + "…"


def _require_insights():
    """Refuse with the reason, before anything is written.

    Tests the **v3** DocType specifically. The old guard tested for the v2
    "Insights Query", which a v3 site still ships — so it passed on v3 and let a
    v2-shaped record be written where nothing would ever read it.
    """
    if not frappe.db.exists("DocType", QUERY_DOCTYPE):
        frappe.throw(
            f"Frappe Insights is not installed on this site, or is older than v3: "
            f"there is no '{QUERY_DOCTYPE}' DocType. Dashboard Studio supports "
            "Insights v3 only — v2 stored queries as 'Insights Query', with a "
            "different payload that this no longer writes."
        )
    roles = set(frappe.get_roles())
    if not roles & set(INSIGHTS_ROLES):
        frappe.throw(
            "Creating an Insights query needs the "
            + " or ".join(INSIGHTS_ROLES)
            + " role, which this account does not have. A Dashboard Studio Editor "
            "does not get it automatically — ask an administrator to add it."
        )
    # Against the v3 table, which is the one v3 resolves the query's data_source
    # against. This read the v2 "Insights Data Source" and passed only because
    # both tables happen to hold a row called "Site DB" — the same fault as the
    # version guard above, checking one generation to decide about the other. It
    # would have started refusing every create the moment the v2 records were
    # deleted, with a message blaming a source that was fine.
    if not frappe.db.exists(SOURCE_DOCTYPE, SITE_DB):
        frappe.throw(
            f"Insights has no '{SITE_DB}' data source on this site, so there is "
            "nothing to run the query against. It is the built-in source pointing "
            "at this site's own database; open Insights once to have it created."
        )


def _studio_workbook():
    """The default workbook, made on first use.

    v3 requires one — `workbook` is a reqd Link — so there is no version of this
    that skips it. Used when the caller names none.
    """
    existing = frappe.get_all(
        WORKBOOK_DOCTYPE, filters={"title": WORKBOOK_TITLE}, fields=["name"],
        order_by="creation asc", limit=1,
    )
    if existing:
        return existing[0]["name"]
    return frappe.get_doc({
        "doctype": WORKBOOK_DOCTYPE,
        "title": WORKBOOK_TITLE,
    }).insert().name


def list_insights_workbooks():
    """The workbooks a query can be created in, newest activity first.

    Read-only. Returns the default's name separately so the picker can preselect
    it without having to know the title convention.
    """
    frappe.only_for(DS_READ_ROLES)
    _require_insights()
    rows = frappe.get_all(
        WORKBOOK_DOCTYPE, fields=["name", "title"], order_by="modified desc", limit=100,
    )
    return {
        "workbooks": [
            {"name": r["name"], "title": r.get("title") or r["name"]} for r in rows
        ],
        "default_title": WORKBOOK_TITLE,
    }


def _resolve_workbook(workbook):
    """The workbook to create in — the named one, or the default.

    The name is CHECKED, never trusted: it arrives from the browser, and
    `workbook` is a Link that Frappe would happily accept as a dangling
    reference on insert, leaving a query in a workbook that does not exist.
    """
    workbook = str(workbook or "").strip()
    if not workbook:
        return _studio_workbook()
    if not frappe.db.exists(WORKBOOK_DOCTYPE, workbook):
        frappe.throw(
            f"There is no Insights workbook '{workbook}'. Pick one from the list, "
            "or leave it unset to use the Dashboard Studio workbook."
        )
    return workbook
