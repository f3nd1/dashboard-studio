"""Read everything Dashboard Studio needs to know about Insights v3, in one go.

Any of these work::

    bench --site <site> console          # then paste this whole file
    bench --site <site> console < scripts/insights_v3_probe.py
    exec(open("apps/dashboard_studio/scripts/insights_v3_probe.py").read())

**Read-only.** Nothing here inserts, updates, deletes or executes anything. It
reads DocType metadata and existing records. Each check is caught on its own, so
one failure costs that check and not the report.

It answers the four things the v3 fix is blocked on:

  1. which Insights DocTypes exist, how many records each holds, and — the part
     that matters most — the real FIELD NAMES, because the version guard in
     api/insights.py is unsound: v3 ships the v2 DocTypes alongside its own, so
     ``exists("DocType", "Insights Query")`` is True on v3 and the guard passes;
  2. a real v3 native query's ``operations`` array, printed whole;
  3. whether ``Insights Query Result`` holds anything for a v3 query — v3 computes
     results on demand with a short cache, so a v2-style "read the executed
     columns" step may have no v3 counterpart at all;
  4. a real v3 chart's ``config``, printed whole, for one with axes actually set.

Checks 5 and 7 need a query and a chart somebody built by hand. The script looks
for existing ones first and only asks if it finds none.

**Why one big function, and why the imports are inside it.** ``bench console``
runs an *embedded* IPython shell, where ``globals()`` and ``locals()`` are two
different dicts. A bare ``exec(open(...).read())`` there writes top-level names
into locals while the functions it defines capture globals — so a helper looking
up a module-level ``REPORT`` raises NameError, which is exactly what the first
live run did. Everything lives in one function so every cross-reference is a
closure lookup, which cannot care which namespace it was exec'd into. ``frappe``
is imported here too rather than leaned on as an ambient global, for the same
reason.

And no blank lines inside the function: IPython reading from stdin ends an
indented block at the first one, which would break the piped form.
"""


def _probe():
    # noqa on the block because isort wants a blank line before the third-party
    # import, and a blank line here is the thing that breaks the piped form.
    import json  # noqa: I001
    import traceback
    import frappe
    # ---- what to look for -------------------------------------------------
    V2_DOCTYPES = [
        "Insights Query", "Insights Chart", "Insights Query Result",
        "Insights Data Source", "Insights Dashboard",
    ]
    V3_DOCTYPES = [
        "Insights Query v3", "Insights Chart v3", "Insights Workbook",
        "Insights Data Source v3", "Insights Dashboard v3",
    ]
    REPORT = []
    # ---- plumbing ---------------------------------------------------------
    def check(label, fn):
        """Run one check. A failure is recorded and printed, never raised."""
        print("\n" + "=" * 78)
        print("== " + label)
        print("=" * 78)
        try:
            REPORT.append((label, fn() or "read"))
        except Exception:
            traceback.print_exc(limit=4)
            REPORT.append((label, "FAILED - see traceback above"))
    # ----------------------------------------------------------------------
    def exists(doctype):
        return bool(frappe.db.exists("DocType", doctype))
    # ----------------------------------------------------------------------
    def loads(value):
        """A JSON field that may arrive as text or already decoded."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                return value
        return value
    # ----------------------------------------------------------------------
    def dump(label, value):
        print("  " + label + ":")
        try:
            print(json.dumps(loads(value), indent=2, default=str))
        except Exception:
            print("  " + repr(value))
    # ---- the checks -------------------------------------------------------
    def versions():
        apps = frappe.get_installed_apps()
        print("  installed apps:", ", ".join(apps))
        for app in ("frappe", "insights", "dashboard_studio"):
            if app not in apps:
                continue
            try:
                print(f"  {app} version:", frappe.get_attr(f"{app}.__version__"))
            except Exception as exc:  # noqa: BLE001
                print(f"  {app} version: unreadable ({exc})")
        return "insights installed" if "insights" in apps else "INSIGHTS NOT INSTALLED"
    # ----------------------------------------------------------------------
    def doctypes_and_counts():
        """Which generation is present, and how much is in each."""
        present = []
        for doctype in V2_DOCTYPES + V3_DOCTYPES:
            if not exists(doctype):
                print(f"  {doctype:28} absent")
                continue
            try:
                count = frappe.db.count(doctype)
            except Exception as exc:  # noqa: BLE001
                count = f"uncountable ({exc})"
            print(f"  {doctype:28} PRESENT  records={count}")
            present.append(doctype)
        v2 = [d for d in V2_DOCTYPES if d in present]
        v3 = [d for d in V3_DOCTYPES if d in present]
        print("\n  -> v2 DocTypes present:", len(v2), "| v3 DocTypes present:", len(v3))
        if v2 and v3:
            print("  -> BOTH generations ship together, which is exactly why the")
            print("     current version guard (exists('DocType', 'Insights Query'))")
            print("     passes on v3.")
        return f"v2={len(v2)} v3={len(v3)}"
    # ----------------------------------------------------------------------
    def fields(doctype):
        """Real field names - the thing a payload has to match."""
        if not exists(doctype):
            print(f"  {doctype}: absent")
            return
        meta = frappe.get_meta(doctype)
        print(f"  {doctype} - {len(meta.fields)} fields")
        for field in meta.fields:
            flags = []
            if field.reqd:
                flags.append("REQD")
            if field.read_only:
                flags.append("read_only")
            if field.unique:
                flags.append("unique")
            link = f" -> {field.options}" if field.fieldtype in ("Link", "Table") else ""
            suffix = ("  [" + ", ".join(flags) + "]") if flags else ""
            print(f"    {field.fieldname:26} {field.fieldtype:12}{link}{suffix}")
    # ----------------------------------------------------------------------
    def schemas():
        for doctype in ("Insights Query v3", "Insights Chart v3", "Insights Workbook",
                        "Insights Query", "Insights Chart"):
            fields(doctype)
            print("")
        return "printed"
    # ----------------------------------------------------------------------
    def data_sources():
        """Which data source a v3 query would have to point at."""
        for doctype in ("Insights Data Source", "Insights Data Source v3"):
            if not exists(doctype):
                print(f"  {doctype}: absent")
                continue
            rows = frappe.get_all(doctype, fields=["name"], limit=50)
            print(f"  {doctype}: " + (", ".join(r["name"] for r in rows) or "(none)"))
        print("\n  Site DB is what create_insights_query writes today. If the v3 list")
        print("  above has no Site DB, that name does not carry over.")
        return "printed"
    # ----------------------------------------------------------------------
    def native_v3_query():
        """A real v3 native query's operations array, printed whole."""
        if not exists("Insights Query v3"):
            print("  Insights Query v3 is absent - nothing to read.")
            return "absent"
        rows = frappe.get_all(
            "Insights Query v3",
            fields=["name", "title", "workbook", "operations", "modified"],
            order_by="modified desc", limit=200,
        )
        print(f"  scanned {len(rows)} v3 queries")
        native = []
        for row in rows:
            operations = loads(row.get("operations")) or []
            kinds = [op.get("type") for op in operations if isinstance(op, dict)]
            if "sql" in kinds:
                native.append((row, operations))
        print(f"  of those, {len(native)} contain an operation of type 'sql'")
        if not native:
            print("\n  NOTHING TO READ. Build one by hand, then re-run this script:")
            print("    Insights -> a workbook -> new query -> the SQL/code tab ->")
            print("    paste any SELECT -> save. Do not run it; saving is enough.")
            if rows:
                print(f"\n  For reference, the most recent v3 query ({rows[0]['name']}):")
                dump("operations", rows[0].get("operations"))
            return "NEEDS A HAND-BUILT NATIVE QUERY"
        for row, operations in native[:2]:
            print(f"\n  --- {row['name']}  workbook={row.get('workbook')!r} "
                  f"title={row.get('title')!r}")
            dump("operations", operations)
        return f"{len(native)} native v3 queries"
    # ----------------------------------------------------------------------
    def v3_results():
        """Does anything persist a v3 query's results?"""
        others = frappe.get_all("DocType", filters={"name": ["like", "%Insights%"]},
                                fields=["name"], limit=200)
        named = [d["name"] for d in others if "result" in d["name"].lower()]
        print("  DocTypes with 'result' in the name:", ", ".join(named) or "(none)")
        if not exists("Insights Query Result"):
            print("  Insights Query Result is absent on this site.")
            return "result DocType absent"
        total = frappe.db.count("Insights Query Result")
        print(f"  Insights Query Result rows: {total}")
        if not exists("Insights Query v3"):
            return f"{total} rows, no v3 to compare"
        v3_names = {r["name"] for r in frappe.get_all("Insights Query v3",
                                                      fields=["name"], limit=1000)}
        rows = frappe.get_all("Insights Query Result",
                              fields=["name", "query"], limit=1000)
        hits = [r for r in rows if r.get("query") in v3_names]
        print(f"  ...of which reference an Insights Query v3: {len(hits)}")
        if hits:
            print("  " + ", ".join(f"{r['name']}->{r['query']}" for r in hits[:5]))
        else:
            print("  -> none. That is the expected v3 answer: results are computed")
            print("     on demand and cached briefly, not stored. So")
            print("     apply_insights_chart's 'read the executed columns' step has")
            print("     no v3 counterpart.")
        return f"{len(hits)} v3 results persisted"
    # ----------------------------------------------------------------------
    def v3_chart_config():
        """A real v3 chart's config, printed whole - ideally one with axes set."""
        if not exists("Insights Chart v3"):
            print("  Insights Chart v3 is absent - nothing to read.")
            return "absent"
        rows = frappe.get_all(
            "Insights Chart v3",
            fields=["name", "title", "chart_type", "query", "workbook", "config",
                    "modified"],
            order_by="modified desc", limit=200,
        )
        print(f"  scanned {len(rows)} v3 charts")
        kinds = {}
        for row in rows:
            key = row.get("chart_type") or "(blank)"
            kinds[key] = kinds.get(key, 0) + 1
        print("  chart_type values in use:", json.dumps(kinds))
        configured = []
        for row in rows:
            config = loads(row.get("config"))
            if isinstance(config, dict) and (config.get("x_axis") or config.get("y_axis")):
                configured.append((row, config))
        print(f"  of those, {len(configured)} have x_axis or y_axis set")
        if not configured:
            print("\n  NOTHING TO READ. Build one by hand, then re-run this script:")
            print("    Insights -> the workbook holding the query above -> add a")
            print("    chart -> pick Bar -> set an X axis and a Y axis -> save.")
            if rows:
                print(f"\n  For reference, the most recent chart ({rows[0]['name']}):")
                dump("config", rows[0].get("config"))
            return "NEEDS A HAND-BUILT CHART WITH AXES"
        for row, config in configured[:2]:
            print(f"\n  --- {row['name']}  chart_type={row.get('chart_type')!r} "
                  f"query={row.get('query')!r} workbook={row.get('workbook')!r}")
            dump("config", config)
        return f"{len(configured)} configured v3 charts"
    # ----------------------------------------------------------------------
    def studio_records():
        """The v2 queries this app created - what became of them."""
        if not exists("Insights Query"):
            print("  Insights Query (v2) is absent.")
            return "v2 absent"
        rows = frappe.get_all(
            "Insights Query",
            filters={"is_native_query": 1},
            fields=["name", "title", "data_source", "chart", "modified"],
            order_by="modified desc", limit=30,
        )
        print(f"  native v2 queries: {len(rows)}")
        for row in rows[:15]:
            print(f"    {row['name']:12} data_source={str(row.get('data_source')):12} "
                  f"chart={str(row.get('chart')):14} {row.get('title')!r}")
        print("\n  These are the QRY-* records create_insights_query made. No v3 patch")
        print("  migrates them, so they are expected to be intact and invisible to")
        print("  the v3 UI rather than converted.")
        return f"{len(rows)} native v2 queries"
    # ---- run them ---------------------------------------------------------
    check("1. Versions and installed apps", versions)
    check("2. Which Insights DocTypes exist, and how full they are", doctypes_and_counts)
    check("3. Real field names on the DocTypes a payload has to match", schemas)
    check("4. Data sources in both generations", data_sources)
    check("5. A real v3 native query's operations array", native_v3_query)
    check("6. Are any v3 query results persisted?", v3_results)
    check("7. A real v3 chart's config", v3_chart_config)
    check("8. The v2 queries Dashboard Studio created", studio_records)
    print("\n\n" + "#" * 78)
    print("# SUMMARY")
    print("#" * 78)
    for label, note in REPORT:
        print(f"  {label:58} {note}")
    print("""
Two things the console cannot answer - check these in a browser:
  a) does /insights/query/build/QRY-1310 still load, or has the legacy UI moved
     to /insights_v2/... ?  (INSIGHTS_QUERY_PATH in api/insights.py)
  b) at what path does a v3 query open?
""")
    return REPORT


_probe()
