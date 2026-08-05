"""What has Insights itself actually stored in its query operations?

Paste into ``bench --site <site> console``, or pipe it in, or exec it from an
open file — all three work (see the note at the bottom about why).

**Read-only.** It reads Insights' own query records. It writes nothing, creates
nothing and executes nothing.

It settles two open questions from evidence rather than reading, because
`query.types.ts` is not in this repo and the expression language is not
documented anywhere we can reach.

**1. Does Insights ever group by a NUMBER?** This converter refuses to group by an
Integer or a Decimal column, on the strength of `DIMENSION_DATA_TYPES =
("String", "Date", "Datetime", "Time")`. That constant's own recorded
provenance — in `archive/api_insights_sql_path.py` — says *"these are not our
rules, they are the ones the CHART RENDERER applies"*, and there it picked a
chart's x-axis. It is now applied to `summarize.dimensions`, which is a
different thing, and it is why 18 reports refuse with "Insights groups only by
text, a date or a time".

If Insights has ever stored a summarize whose dimension is Integer or Decimal,
then it accepts one, and the constant is this converter's own over-restriction.

**2. What may a `mutate` expression contain?** The one captured example is pure
arithmetic — `"(avg_of_idx + avg_of_docstatus) / 2"` — which says nothing about
whether the language has `YEAR()`, `CONCAT()`, `CAST()` or anything else. Every
stored expression is printed whole here, with the functions in it tallied. One
that calls a function settles it; the ALLOWLIST in `parser._ARITHMETIC_ONLY`
can then widen to exactly the functions seen, and no further.

**A negative result proves nothing** on either question, and the output says so:
nobody may simply have built one. In that case the answer comes from building
one by hand in the Insights UI and reading back what it stores — the loop that
produced the chart config, the `cast` shape and the arithmetic dialect.

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
    import re
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
    print("What Insights has stored in its own queries — READ ONLY, nothing changed")
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
    expressions, functions, orders = [], {}, []
    for row in rows:
        try:
            record = frappe.get_doc(doctype, row["name"])
        except Exception as error:  # noqa: BLE001
            print(f"   could not read {row['name']}: {type(error).__name__}: {error}")
            continue
        operations = operations_of(record, fields)
        if operations:
            read += 1
        kinds = [o.get("type") for o in operations if isinstance(o, dict)]
        if "mutate" in kinds:
            # The ORDER, from the stored record rather than the UI, which lists
            # the steps in its own display order. A mutate before a summarize
            # is what lets a grouping name a calculated column.
            orders.append((row["name"], " -> ".join(str(k) for k in kinds)))
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            if operation.get("type") == "mutate":
                text = ((operation.get("expression") or {}).get("expression")
                        if isinstance(operation.get("expression"), dict)
                        else operation.get("expression"))
                if text:
                    expressions.append((row["name"], operation.get("new_name"), text))
                    for name in re.findall(r"\b([A-Za-z_]\w*)\s*\(", str(text)):
                        functions[name.upper()] = functions.get(name.upper(), 0) + 1
            if operation.get("type") != "summarize":
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
    print(f"1. Dimension data_types across {with_summarize} summarize steps "
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
    print(f"2. Every `mutate` expression Insights has stored ({len(expressions)})")
    print("=" * 78)
    for name, new_name, text in expressions[:40]:
        print(f"   {name}: {new_name} = {text}")
    if len(expressions) > 40:
        print(f"   ...and {len(expressions) - 40} more")
    if not expressions:
        print("   none — no query here has a calculated column")
    if functions:
        print()
        print("   Functions called inside them:")
        for name in sorted(functions, key=lambda key: -functions[key]):
            print(f"      {functions[name]:>4}  {name}")
        print()
        print("   ANSWER: the expression language has functions, and these are")
        print("   ones it accepts. The allowlist can widen to exactly these.")
    else:
        print()
        print("   NO FUNCTION SEEN — and that is not "
              "'the language has none'.")
        print("   Every stored expression is plain arithmetic, which is all the")
        print("   captured example showed too. To settle it: in the Insights UI,")
        print("   add a calculated column that extracts a year from a date, save")
        print("   it, and re-run this. What it stores is the answer.")
    print()
    print("=" * 78)
    print(f"3. Stored operation ORDER for queries carrying a mutate ({len(orders)})")
    print("=" * 78)
    for name, order in orders[:20]:
        print(f"   {name}: {order}")
    if len(orders) > 20:
        print(f"   ...and {len(orders) - 20} more")
    if not orders:
        print("   none — no stored query has a mutate at all")
    else:
        before = [name for name, order in orders
                  if "mutate" in order.split(" -> summarize")[0]]
        print()
        print(f"   {len(before)} of {len(orders)} put the mutate BEFORE a summarize.")
        print("   That is the ordering a calculated column feeding a grouping needs,")
        print("   and this reads it from the record rather than from the UI's list.")
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
