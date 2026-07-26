"""Hand a pasted SQL query to Frappe Insights as a real, queryable Query.

**Scope is deliberately one thing: create the Query.** No chart, no dashboard, no
workbook. Insights already has a chart editor — title, axes, reference line,
palette, curve toggles — and Dashboard Studio is not rebuilding any of it. Once
the Query exists, the person opens Insights and builds the chart there.

Chart creation was investigated and rejected, not forgotten: a valid Insights
chart config has to declare a ``data_type`` for every axis column, and for a
native SQL query those types only exist after execution. Studio would be
guessing them from parsed SQL text, and a wrong guess renders a wrong chart in
another app with no error this side can catch.

Verified against the site on 2026-07-26 (record QRY-1308): this site runs
Insights **v2**, whose ``Insights Query`` carries the SQL in a plain ``sql``
field with ``is_native_query`` and a ``data_source`` Link. Insights v3 models the
same thing completely differently — ``Insights Query v3`` requires a workbook and
buries the SQL in an ``operations`` JSON array as ``{"type": "sql", "raw_sql":
…}`` — so this module is v2-only and says so out loud rather than half-supporting
both. ``_require_insights`` names the version problem if the DocType is absent.

**Security boundary, stated because it is a real one.** This writes SQL that
another app will execute. Dashboard Studio never runs it: the record is stored,
and Insights executes it later under Insights' own permissions and its own SQL
validation. That is the whole reason this endpoint refuses anything that is not
a single read-only statement — Studio must not be the thing that filed a DELETE.
It also means this route bypasses the DS Metric allowlist and approval gate by
design; it is a scratchpad for exploring a migrated query, and nothing published
as EduTrust evidence should come from it.
"""

import frappe

from dashboard_studio.api.studio import DS_WRITE_ROLES

# The v2 DocType. Named once so the version assumption has a single home.
QUERY_DOCTYPE = "Insights Query"

# Insights manages this data source itself and points it at the site's own
# database, so a query written here reaches the same tables ERPNext uses. Its
# name is literally "Site DB" — enforced on the Insights side by "Only one site
# database can be configured".
SITE_DB = "Site DB"

# Creating an Insights Query needs an Insights role, which a Dashboard Studio
# Editor does not automatically hold. Checked explicitly so the refusal names the
# missing role instead of surfacing as a bare permission error.
INSIGHTS_ROLES = ("Insights User", "Insights Admin")

# UNVERIFIED — the one thing in this module I could not confirm from source. The
# Insights v2 single-query route is /query/build/<name>, but the SPA's base path
# differs by install: a standalone v2 serves it at /insights, while a v3 install
# running the legacy UI serves it at /insights_v2. If the link 404s, this
# constant is the only thing to change. The Desk URL returned alongside it is
# derived from Frappe itself and is correct either way, which is why both are
# returned rather than one guess.
INSIGHTS_QUERY_PATH = "/insights/query/build/{name}"
DESK_QUERY_PATH = "/app/insights-query/{name}"

_READ_ONLY_STARTS = ("select", "with")


def query_title(analysis, sql=None):
    """A title for the Insights Query, from whatever the analysis managed.

    Degrades on purpose. The queries most worth handing to Insights are the ones
    the DS parser could NOT translate, so a title that only works for a clean
    parse would be missing exactly when it is needed.
    """
    analysis = analysis or {}
    doctypes = [d for d in (analysis.get("doctypes") or []) if d]
    group_by = [g for g in (analysis.get("group_by") or []) if g]
    aggregations = analysis.get("aggregations") or []
    function = str((aggregations[0] or {}).get("function") or "").title() if aggregations else ""

    if doctypes and len(doctypes) == 1 and group_by and function:
        return f"{function} of {doctypes[0]} by {group_by[0]}"
    if doctypes and len(doctypes) == 1:
        return f"{doctypes[0]} query"
    if len(doctypes) > 1:
        return " + ".join(sorted(doctypes)[:3]) + " query"
    return "Imported SQL query"


def _normalised_sql(sql):
    """The SQL as it will be stored, or a refusal reason.

    Returns ``(sql, reason)`` — exactly one is set.

    ponytail: a start-of-statement check plus a no-second-statement check, not a
    SQL parser. Insights validates again before it executes, so this is the
    cheap outer guard whose only job is that Studio never writes a destructive
    statement into another app's record. Replace it with the real parser if this
    ever needs to allow anything more interesting than SELECT.
    """
    text = (sql or "").strip()
    if not text:
        return None, "There is no SQL to send. Paste a query first."
    # One trailing semicolon is ordinary; any other is a second statement.
    text = text.rstrip().rstrip(";").rstrip()
    if ";" in text:
        return None, (
            "That looks like more than one statement. Send a single SELECT — "
            "Insights runs what is stored here."
        )
    if not text.lower().lstrip("( \n\t").startswith(_READ_ONLY_STARTS):
        return None, (
            "Only a SELECT (or WITH) query can be sent to Insights. This one starts "
            f"with '{text.split()[0]}', and Dashboard Studio will not file a "
            "statement that writes."
        )
    return text, None


def _require_insights():
    """Refuse with the reason, before anything is written."""
    if not frappe.db.exists("DocType", QUERY_DOCTYPE):
        frappe.throw(
            f"Frappe Insights is not installed on this site, or is a version without "
            f"the '{QUERY_DOCTYPE}' DocType. This handoff supports Insights v2; v3 "
            "stores queries as 'Insights Query v3' and needs a different payload."
        )
    roles = set(frappe.get_roles())
    if not roles & set(INSIGHTS_ROLES):
        frappe.throw(
            "Creating an Insights query needs the "
            + " or ".join(INSIGHTS_ROLES)
            + " role, which this account does not have. A Dashboard Studio Editor "
            "does not get it automatically — ask an administrator to add it."
        )
    if not frappe.db.exists("Insights Data Source", SITE_DB):
        frappe.throw(
            f"Insights has no '{SITE_DB}' data source on this site, so there is "
            "nothing to run the query against. It is the built-in source pointing "
            "at this site's own database; open Insights once to have it created."
        )


@frappe.whitelist()
def create_insights_query(sql: str, title: str = None, analysis=None):
    """Create (or reuse) a native Insights Query holding this SQL.

    Returns the record and two links: the Insights UI and the Desk form. Two,
    because only the second is provably correct on every install — see
    INSIGHTS_QUERY_PATH.
    """
    frappe.only_for(DS_WRITE_ROLES)
    _require_insights()

    text, reason = _normalised_sql(sql)
    if reason:
        frappe.throw(reason)

    if isinstance(analysis, str):
        analysis = frappe.parse_json(analysis)
    name = (title or "").strip() or query_title(analysis, text)

    # Reuse rather than pile up duplicates: clicking twice is the normal way to
    # find out whether the first click worked. Keyed on the SQL, because that is
    # what makes two queries the same query — the title is editable in Insights.
    #
    # ponytail: exact-text match, so whitespace differences make a new record.
    # Normalising SQL properly needs a parser and this is a convenience, not a
    # correctness rule.
    existing = frappe.get_all(
        QUERY_DOCTYPE,
        filters={"is_native_query": 1, "sql": text},
        fields=["name", "title"],
        limit=1,
    )
    if existing:
        return _result(existing[0]["name"], existing[0].get("title") or name, reused=True)

    doc = frappe.get_doc({
        "doctype": QUERY_DOCTYPE,
        "title": name,
        "is_native_query": 1,
        "data_source": SITE_DB,
        "sql": text,
    }).insert()
    return _result(doc.name, name, reused=False)


def _result(name, title, reused):
    return {
        "name": name,
        "title": title,
        "reused": bool(reused),
        "data_source": SITE_DB,
        "insights_url": INSIGHTS_QUERY_PATH.format(name=name),
        "desk_url": DESK_QUERY_PATH.format(name=name),
    }
