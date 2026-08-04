"""Does Insights itself ever group by a NUMBER?

Paste into ``bench --site <site> console``, or pipe it in, or exec it from an
open file — all three work (see the note at the bottom about why).

**Read-only.** It reads Insights' own query records. It writes nothing, creates
nothing and executes nothing.

It settles one question, and only one. This converter refuses to group by an
Integer or a Decimal column, on the strength of `DIMENSION_DATA_TYPES =
("String", "Date", "Datetime", "Time")`. That constant's own recorded
provenance — in `archive/api_insights_sql_path.py` — says *"these are not our
rules, they are the ones the CHART RENDERER applies"*, and there it picked a
chart's x-axis. It is now applied to `summarize.dimensions`, which is a
different thing, and it is why 18 reports refuse with "Insights groups only by
text, a date or a time".

`query.types.ts` is not in this repo, so the question cannot be settled by
reading. It CAN be settled by evidence: if Insights has ever stored a summarize
whose dimension is Integer or Decimal, then it accepts one, and the constant is
this converter's own over-restriction. That is what this counts.

**A negative result proves nothing** and the output says so: nobody may simply
have built one. In that case the answer comes from building one by hand in the
Insights UI and reading back what it stores — the loop that produced the chart
config, the `cast` shape and the expression dialect.

The operations field is DISCOVERED rather than named: it prints the fields it
found and reads whichever one parses as a list of operations, so a field name
that differs on this version is visible rather than silently empty.

ponytail: no blank lines inside the function, and everything inside one
function with its imports. ``bench console`` runs an embedded IPython where
globals() and locals() are different dicts, so a bare exec(open(...).read())
would leave module-level names unreachable from the functions that need them.
"""

def _probe():
    # noqa on the block: isort wants a blank line before the first-party
    # import, and a blank line here breaks the piped-paste form.
    import json  # noqa: I001
    import frappe
    # INSIDE the function on purpose — see the note above about bench console's
    # split namespaces.
    doctype = "Insights Query v3"
    numeric = ("Integer", "Decimal")
    def operations_of(record, fields):
        """Every operation on a record, from whichever field holds them."""
        for field in fields:
            value = record.get(field)
            if not value:
                continue
            try:
                parsed = json.loads(value) if isinstance(value, str) else value
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, list) and any(
                    isinstance(item, dict) and item.get("type") for item in parsed):
                return parsed
        return []
    print("=" * 78)
    print("Does Insights ever group by a number? — READ ONLY, nothing changed")
    print("=" * 78)
    if not frappe.db.exists("DocType", doctype):
        print(f"   {doctype} does not exist on this site — Insights v3 is not here.")
        return
    fields = [f.fieldname for f in frappe.get_meta(doctype).fields]
    print(f"   {doctype} fields: {', '.join(fields)}")
    rows = frappe.get_all(doctype, fields=["name"])
    print(f"   {len(rows)} query records to read")
    print()
    seen, examples, read, with_summarize = {}, {}, 0, 0
    for row in rows:
        try:
            record = frappe.get_doc(doctype, row["name"])
        except Exception as error:  # noqa: BLE001
            print(f"   could not read {row['name']}: {type(error).__name__}: {error}")
            continue
        operations = operations_of(record, fields)
        if operations:
            read += 1
        for operation in operations:
            if not isinstance(operation, dict) or operation.get("type") != "summarize":
                continue
            with_summarize += 1
            for dimension in operation.get("dimensions") or []:
                if not isinstance(dimension, dict):
                    continue
                data_type = dimension.get("data_type") or "<none>"
                seen[data_type] = seen.get(data_type, 0) + 1
                examples.setdefault(data_type,
                                    f"{row['name']}: {dimension.get('column_name')}")
    print("=" * 78)
    print(f"Dimension data_types across {with_summarize} summarize steps "
          f"in {read} readable queries")
    print("=" * 78)
    for data_type in sorted(seen, key=lambda key: -seen[key]):
        mark = "  <-- A NUMBER" if data_type in numeric else ""
        print(f"   {seen[data_type]:>5}  {data_type}{mark}")
        print(f"          e.g. {examples[data_type]}")
    if not seen:
        print("   none — no summarize with a dimension was found")
    print()
    print("=" * 78)
    found = [d for d in seen if d in numeric]
    if found:
        print(f"ANSWER: yes. Insights has stored {', '.join(found)} dimensions, so it")
        print("accepts a numeric grouping and DIMENSION_DATA_TYPES is this converter's")
        print("own over-restriction. Send this output back and it comes out.")
    else:
        print("NO EVIDENCE EITHER WAY — and that is not a no.")
        print("Nobody may simply have built one. To settle it: in the Insights UI,")
        print("build any query grouped by a numeric column, save it, and re-run this.")
        print("If it still shows no numeric dimension after that, the restriction is")
        print("real and the 18 reports are a genuine limitation rather than a cap.")
    print("=" * 78)
    print("Nothing was written. No query was executed.")
    return seen


_probe()
