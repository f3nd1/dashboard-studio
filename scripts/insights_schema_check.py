"""Does Insights agree with the database about a table's columns?

Paste into ``bench --site <site> console``, or pipe it in, or exec it from an
open file — all three work (see the note at the bottom about why).

**Read-only.** It reads DocType metadata and Insights' own records. It writes
nothing, syncs nothing and executes no query.

It exists because a converted query has twice been written with a column the
table does not have, and each time it was found by a person opening the query
in Insights and reading the error. The converter now validates against
``frappe.db.get_table_columns`` — the live schema — which closes the case where
those two disagree. What it CANNOT close from outside the site is the case
where **Insights** holds its own synced copy of the schema and that copy is
stale: the converter would pass, and Insights would still refuse on open.

Whether Insights keeps such a copy, and where, is not guessed here. The script
DISCOVERS it: it lists the Insights DocTypes this site actually has, prints the
fields of the ones that look like a table/column cache, and then, for each
DocType you name, compares the live column list against anything Insights
appears to hold for that table. Send the whole output back — the names and
shapes it prints are what a real check would then be built against.

Edit the `tables` list inside the function to the DocTypes your report
touches.

ponytail: no blank lines inside the function, and everything inside one
function with its imports. ``bench console`` runs an embedded IPython where
globals() and locals() are different dicts, so a bare exec(open(...).read())
would leave module-level names unreachable from the functions that need them —
that fault has already cost a round trip twice in this project.
"""

def _check():
    # noqa on the block: isort wants a blank line before the first-party
    # import, and a blank line here breaks the piped-paste form.
    import frappe  # noqa: I001
    # INSIDE the function on purpose. `bench console` is an embedded IPython
    # where globals() and locals() are different dicts, so a module-level TABLES
    # is unreachable from here — that is the NameError this script's test caught
    # before it ever reached a site. Edit this list, not one above.
    tables = [
        "Quality Performance Outcomes",
        "Quality Performance Outcomes Performance Childtable",
        "Quality Performance Actual Value Parameter Childtable",
    ]
    print("=" * 72)
    print("1. Insights DocTypes on this site")
    print("=" * 72)
    insights = sorted(frappe.get_all("DocType", filters={"name": ["like", "%Insights%"]},
                                     pluck="name"))
    for name in insights:
        print("   " + name)
    if not insights:
        print("   none — Insights is not installed on this site")
        return
    print()
    print("=" * 72)
    print("2. Which of them look like a per-table column cache, and their shape")
    print("=" * 72)
    holders = [n for n in insights if "table" in n.lower() or "column" in n.lower()]
    column_lists = []
    for name in holders:
        meta = frappe.get_meta(name)
        rows = frappe.db.count(name)
        print(f"   {name}  ({rows} rows)")
        for field in meta.fields:
            options = f" -> {field.options}" if field.options else ""
            print(f"      {field.fieldname:<28} {field.fieldtype}{options}")
        if rows and any(f.fieldtype == "Table" for f in meta.fields):
            column_lists.append(name)
    if not column_lists:
        print()
        print("   FINDING: no populated DocType here holds a per-column child table,")
        print("   so Insights does not keep its column list in the database. A stale")
        print("   view therefore lives in the query engine's own connection, not in a")
        print("   record that could be resynced from here.")
    print()
    print("=" * 72)
    print("3. Live schema vs what Insights records, per table")
    print("=" * 72)
    for doctype in tables:
        table = "tab" + doctype
        print(f"-- {doctype}")
        try:
            live = sorted(frappe.db.get_table_columns(doctype))
        except Exception as error:
            print(f"   live schema UNREADABLE: {type(error).__name__}: {error}")
            continue
        print(f"   live columns ({len(live)}): {', '.join(live)}")
        # Frappe caches this list in redis. If the cache is stale, everything
        # reading through frappe.db sees the stale one — including this script,
        # so the two lines below are printed side by side deliberately.
        try:
            cached = frappe.cache.hget("table_columns", table)
        except Exception:
            cached = None
        if cached is None:
            print("   frappe's redis cache: no entry (read straight from the database)")
        elif sorted(cached) != live:
            print(f"   frappe's redis CACHE DISAGREES: {sorted(set(live) ^ set(cached))}")
        else:
            print("   frappe's redis cache: agrees")
        found_any = False
        for name in holders:
            # Keyed by the `table` FIELD, not the record name — Insights names
            # these records by hash, and matching on the name reported "no
            # record found" for tables that plainly had one.
            fields = [f.fieldname for f in frappe.get_meta(name).fields]
            if "table" not in fields:
                continue
            for row in frappe.get_all(name, filters={"table": table}, fields=["name"]):
                found_any = True
                record = frappe.get_doc(name, row["name"])
                print(f"   {name} '{row['name']}'")
                for field in fields:
                    value = record.get(field)
                    if value not in (None, "", 0):
                        print(f"      {field} = {value}")
        if not found_any:
            print(f"   no record in any Insights DocType has table = '{table}'")
    print()
    print("=" * 72)
    print("4. Data sources, and whether they record a sync")
    print("=" * 72)
    for source_doctype in [n for n in insights if "data source" in n.lower()]:
        for row in frappe.get_all(source_doctype, fields=["name"]):
            record = frappe.get_doc(source_doctype, row["name"])
            fields = [f.fieldname for f in frappe.get_meta(source_doctype).fields]
            interesting = [f for f in fields
                           if "sync" in f or "status" in f or "modified" in f]
            print(f"   {source_doctype} '{row['name']}'")
            for field in interesting or ["name"]:
                print(f"      {field} = {record.get(field)}")
    print()
    print("Send this whole output back. Nothing was written or synced.")


_check()
