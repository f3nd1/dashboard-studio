"""Which database would `reconcile_numbers.py` actually touch? Print it.

    exec(open('apps/dashboard_studio/scripts/which_database.py').read())

Written because the question "does this reach production?" was answered by
inference once, and inference is not an answer. Nothing in this repo can see a
bench, so the only honest way to settle it is to read the connection on the
machine that has one and print it.

It prints, for the bench it runs on:

  1. the SITE database — what `frappe.db.sql` connects to, which is the half of
     the harness that runs the card's exported SQL;
  2. every Insights Data Source v3 — which is the half that runs our converted
     query, and is NOT necessarily the same database;
  3. whether those two agree, because if they do not, the harness would be
     comparing two databases rather than two translations;
  4. where the exported SQL came FROM, as far as this bench can tell.

**Names and hosts only. Never a password, a username or a token** — this prints
to a terminal and gets pasted into chat. The credential fields on
`Insights Data Source v3` are `password`, `username`, `api_token`, `api_password`
and `bigquery_service_account_key`; none of them is read here, and a test
asserts that.

Read-only: it reads configuration and prints. No query is run against any of the
databases it names.

ponytail: one function, imports inside, no blank lines in indented blocks —
bench console's split namespaces and IPython's blank-line rule.
"""

def _which():
    # noqa on the block: isort wants a blank line before the first-party
    # import, and a blank line here breaks the piped-paste form.
    import frappe  # noqa: I001
    def host_of(url):
        """The host part of a URL, without any credentials it may carry."""
        text = str(url or "")
        text = text.split("://", 1)[-1]
        text = text.split("/", 1)[0]
        return text.rsplit("@", 1)[-1] or "(not set)"
    print("=" * 78)
    print("SITE DATABASE — what frappe.db.sql connects to")
    print("   this is the half that runs the CARD's exported SQL")
    print("=" * 78)
    site_db = frappe.conf.get("db_name")
    site_host = frappe.conf.get("db_host") or "localhost"
    print(f"   site:          {frappe.local.site}")
    print(f"   database name: {site_db}")
    print(f"   host:          {site_host}")
    print(f"   port:          {frappe.conf.get('db_port') or '(default)'}")
    print("")
    print("=" * 78)
    print("INSIGHTS DATA SOURCES — what our converted query connects to")
    print("=" * 78)
    sources = frappe.get_all(
        "Insights Data Source v3",
        fields=["name", "title", "database_type", "host", "port",
                "database_name", "is_site_db", "is_frappe_db", "status"])
    if not sources:
        print("   none found — is Insights v3 installed on this site?")
    for source in sources:
        print(f"   {source.get('name')}  ({source.get('title')})")
        print(f"      type:          {source.get('database_type')}")
        print(f"      is_site_db:    {source.get('is_site_db')}")
        print(f"      database name: {source.get('database_name') or '(site db)'}")
        print(f"      host:          {source.get('host') or '(site db)'}")
        print(f"      port:          {source.get('port') or '(site db)'}")
        print(f"      status:        {source.get('status')}")
    print("")
    print("=" * 78)
    print("DO THE TWO HALVES MEET ON THE SAME DATABASE?")
    print("=" * 78)
    used = [s for s in sources if s.get("name") == "Site DB"] or sources
    for source in used:
        if source.get("is_site_db"):
            print(f"   {source.get('name')}: marked is_site_db — same database as "
                  f"the site, {site_db}. The comparison is like for like.")
            continue
        same = ((source.get("database_name") or site_db) == site_db
                and (source.get("host") or site_host) == site_host)
        print(f"   {source.get('name')}: "
              + ("same host and database name as the site."
                 if same else
                 "DIFFERENT from the site database — the harness would compare "
                 "two databases, not two translations. Do not read its output "
                 "as a translation result until this is resolved."))
    print("")
    print("=" * 78)
    print("WHERE THE EXPORTED SQL CAME FROM")
    print("=" * 78)
    print(f"   metabase_url host: {host_of(frappe.conf.get('metabase_url'))}")
    print("   Which database THAT Metabase reads is configured inside Metabase")
    print("   and cannot be read from this bench. It does not affect the")
    print("   harness: both halves run here, against the databases named above.")
    print("")
    print("No query was run against any of these. No credential was printed.")


_which()
