"""Do the converted queries return the NUMBERS the cards return?

    import os
    os.environ['DASHBOARD_STUDIO_SQL_DIR'] = '/full/path/to/metabase_sql'
    os.environ['DASHBOARD_STUDIO_CARDS'] = '2076,1680'
    exec(open('apps/dashboard_studio/scripts/reconcile_numbers.py').read())

689 reports convert. Exactly one has had its figures compared against Metabase,
by a person, by eye. Every automated check in this repo proves a query CONVERTS
and OPENS — none of them proves it is RIGHT. This runs both halves and compares
the rows.

**It does not call Metabase, and it does not need to.** Running a card would
need `POST /api/card/:id/query`, which executes against the production database
and is on this project's never-add list. It is also unnecessary: the exported
`.sql` beside each card IS the SQL Metabase runs — native cards verbatim, GUI
cards compiled by Metabase itself through the approved compile-only endpoint —
and Metabase reads the same database this bench does. So the card's own SQL is
read off disk and run here. That is a better comparison as well as a smaller
one: it isolates our translation from Metabase's rendering, which is the only
thing in question.

**What it executes, and the two ways that is bounded.** The card's SQL, checked
by `_read_only` to be one SELECT and nothing else before the database sees it,
wrapped in a row cap, and rolled back afterwards. The disk it comes from is not
a trusted input — anyone who can reach the bench can write there — so the guard
is applied to the text rather than to the situation. The durable control is
still the one this project has always named: a SELECT-only database login.

**What a match proves, and what it does not.** It proves our operations compute
what the card's SQL computes. It cannot prove the CARD is right. If a card fans
out a one-to-many join, or never filtered `docstatus`, we reproduce that exactly
and both sides agree — correctly reported as a match, with the fault untouched.
Those are card-fidelity questions and this is a translation-fidelity instrument.
What it does catch: MySQL-versus-ibis semantics (integer division, rounding,
string case, COUNT(col) against NULLs), a join whose type or shape changed in
translation, a filter that did not survive, a grouping that collapsed, and
column names colliding once slugged.

Read-only, with one disclosure: Insights writes an execution-log row of its own
whenever a query runs, exactly as it does when a person opens one in the UI.
Nothing here writes an Insights Query — the query is built in memory from a doc
that is never inserted.

ponytail: everything inside one function with its imports, and no blank lines
inside indented blocks — bench console's split namespaces and IPython's
blank-line-ends-a-block rule have each cost a round trip already. `_read_only`
is returned by that function rather than defined beside it for the same reason:
a module-level helper is unreachable from inside the function under `exec`.
"""

def _reconcile(guard_only=False):
    # noqa on the block: isort wants a blank line before the first-party
    # import, and a blank line here breaks the piped-paste form.
    import os  # noqa: I001
    import pathlib
    import re
    import sys
    script_name = "reconcile_numbers.py"
    # Rows past this and the card is skipped rather than compared: pulling a
    # million rows into python to check a report nobody reads that way is not
    # what this is for. Insights' own executor clamps a page at 10,000 anyway
    # (ibis_utils.execute_ibis_query), so this stays under it.
    row_cap = 5000
    # Compare against the LIVE database, which is the one the card's SQL runs
    # against. If the site reads through a warehouse copy instead, a difference
    # would be sync lag rather than translation — a true finding wearing a
    # confusing hat. Set False only if you mean to test the warehouse.
    use_live_connection = True
    # `{card id: {card column: our column}}` for columns that cannot pair by
    # name — the card's `AVG(x) AS avg` is our `avg_of_x`. The run prints a
    # ready-to-fill block for whatever it could not pair; paste it back here.
    column_maps = {}
    _WRITES = ("INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER",
               "CREATE", "GRANT", "REVOKE", "REPLACE", "CALL", "LOAD", "SET",
               "INTO", "HANDLER", "LOCK", "RENAME", "COMMIT", "ROLLBACK",
               "START", "BEGIN", "PREPARE", "EXECUTE", "DO", "USE")
    def _strip(text):
        """Comments, string literals and backticked names removed.
        A backticked name is an IDENTIFIER by construction (ADR-032's argument),
        so a column called `update` is not an UPDATE; and a value like 'x; y' is
        not a second statement. Both appear in the real corpus."""
        out, index, quote = [], 0, ""
        while index < len(text):
            char = text[index]
            if quote:
                if char == "\\" and quote in "'\"":
                    index += 2
                    continue
                if char == quote:
                    quote = ""
                index += 1
                continue
            if char in "'\"`":
                quote = char
                out.append(" ")
                index += 1
                continue
            if text.startswith("--", index) or char == "#":
                while index < len(text) and text[index] != "\n":
                    index += 1
                continue
            if text.startswith("/*", index):
                end = text.find("*/", index + 2)
                index = len(text) if end == -1 else end + 2
                out.append(" ")
                continue
            out.append(char)
            index += 1
        return "".join(out)
    def _read_only(statement):
        """"" if this is one plain SELECT; otherwise why it is refused."""
        bare = _strip(statement or "")
        parts = [part for part in bare.split(";") if part.strip()]
        if len(parts) > 1:
            return f"{len(parts)} statements in one file — only a single SELECT is run"
        if not parts:
            return "no statement found"
        first = parts[0].lstrip().lstrip("(").lstrip()
        if not re.match(r"^SELECT\b", first, re.IGNORECASE):
            word = (re.match(r"^\s*(\w+)", first) or [None, "?"])[1]
            return f"statement starts with {word!r}, not SELECT"
        for verb in _WRITES:
            if re.search(r"\b" + verb + r"\b", bare, re.IGNORECASE):
                return f"statement contains {verb} — refused, this only ever reads"
        return ""
    if guard_only:
        return _read_only
    directory, chosen_from, cards = "", "", []
    if os.environ.get("DASHBOARD_STUDIO_SQL_DIR"):
        directory = os.environ["DASHBOARD_STUDIO_SQL_DIR"]
        chosen_from = "$DASHBOARD_STUDIO_SQL_DIR"
    elif os.path.basename(sys.argv[0] or "") == script_name and len(sys.argv) > 1:
        directory = sys.argv[1]
        chosen_from = "the command line"
    if os.environ.get("DASHBOARD_STUDIO_CARDS"):
        cards = [c.strip() for c in os.environ["DASHBOARD_STUDIO_CARDS"].split(",")
                 if c.strip()]
    elif os.path.basename(sys.argv[0] or "") == script_name and len(sys.argv) > 2:
        cards = [c.strip() for c in sys.argv[2:] if c.strip()]
    if not directory or not cards:
        print("Usage: which folder, and which card ids.")
        print(f"   python scripts/{script_name} path/to/metabase_sql/ 2076 1680")
        print("or, under bench console, set both first:")
        print("   import os")
        print("   os.environ['DASHBOARD_STUDIO_SQL_DIR'] = '/full/path/to/metabase_sql'")
        print("   os.environ['DASHBOARD_STUDIO_CARDS'] = '2076,1680'")
        print(f"   exec(open('apps/dashboard_studio/scripts/{script_name}').read())")
        print("")
        print("Pick a sample covering the SHAPES, not the biggest reports:")
        print("   a plain aggregate, a joined one, one with a computed column,")
        print("   one with a coerced type (ADR-009's `* 1`), one with a filter,")
        print("   and one report whose numbers a person has already checked —")
        print("   that last one is the control, and if IT disagrees the harness")
        print("   is what is wrong, not the converter.")
        return
    folder = pathlib.Path(directory).expanduser()
    if not folder.is_dir():
        print(f"Not a directory: {folder}   (from {chosen_from})")
        return
    # Imported only once there is work to do, so the usage text above prints
    # anywhere — this file is read by its own tests, which have no bench.
    import json  # noqa: I001
    import frappe
    from dashboard_studio.api.convert import _table_columns
    from dashboard_studio.integrations.metabase.parser import analyze_sql
    from dashboard_studio.integrations.metabase.sql_ops import operations_from_sql
    from dashboard_studio.integrations.reconcile import compare_results, describe
    from insights.insights.doctype.insights_data_source_v3.ibis_utils import (
        IbisQueryBuilder,
        execute_ibis_query,
    )
    print(f"Reading {folder.resolve()}   (from {chosen_from})")
    print("Read-only: one SELECT per card, row-capped, rolled back. "
          "Metabase is not contacted.")
    verdicts, unpaired = [], {}
    for card in cards:
        matches = sorted(folder.glob(f"*--{card}.sql"))
        print("")
        print("=" * 78)
        if not matches:
            print(f"card {card}: NO FILE matching *--{card}.sql")
            verdicts.append((card, "no file"))
            continue
        path = matches[0]
        print(f"card {card}: {path.name}")
        raw = path.read_text().strip().rstrip(";")
        refusal = _read_only(raw)
        if refusal:
            print(f"   NOT RUN: {refusal}")
            verdicts.append((card, "refused by the read-only guard"))
            continue
        try:
            capped = f"SELECT * FROM (\n{raw}\n) `_reconcile` LIMIT {row_cap + 1}"
            card_rows = frappe.db.sql(capped, as_dict=True)
        except Exception as error:  # noqa: BLE001
            print(f"   the card's SQL did not run: {type(error).__name__}: {error}")
            verdicts.append((card, "card SQL failed"))
            frappe.db.rollback()
            continue
        frappe.db.rollback()
        if len(card_rows) > row_cap:
            print(f"   more than {row_cap} rows — skipped, not compared")
            verdicts.append((card, "too many rows"))
            continue
        analysis = analyze_sql(raw)
        doctypes = [d for d in (analysis.get("doctypes") or []) if d]
        columns = ({d: _table_columns(d) for d in doctypes}
                   if analysis.get("supported") else {})
        converted = operations_from_sql(analysis, columns)
        if not converted["supported"]:
            print("   does not convert: " + " | ".join(converted["reasons"]))
            verdicts.append((card, "does not convert"))
            continue
        try:
            doc = frappe.new_doc("Insights Query v3")
            doc.title = f"reconcile {card}"
            doc.operations = json.dumps(converted["operations"])
            doc.use_live_connection = 1 if use_live_connection else 0
            built = IbisQueryBuilder(doc).build()
            ours, _taken = execute_ibis_query(
                built, page_size=row_cap, force=True, cache=False)
            our_rows = ours.to_dict(orient="records")
        except Exception as error:  # noqa: BLE001
            print(f"   our query did not run: {type(error).__name__}: {error}")
            verdicts.append((card, "our query failed"))
            continue
        report = compare_results(
            {"columns": list(card_rows[0].keys()) if card_rows else [],
             "rows": card_rows},
            {"columns": list(our_rows[0].keys()) if our_rows else [],
             "rows": our_rows},
            column_maps.get(card))
        for line in describe(report, card):
            print("   " + line if not line.startswith("card") else line)
        if report["columns"]["only_expected"] or report["columns"]["only_actual"]:
            unpaired[card] = (report["columns"]["only_expected"],
                              report["columns"]["only_actual"])
        verdicts.append((card, "INCONCLUSIVE (no rows)" if report["inconclusive"]
                         else "MATCH" if report["match"] else "DIFFERS"))
    print("")
    print("=" * 78)
    for card, verdict in verdicts:
        print(f"   card {card}: {verdict}")
    if unpaired:
        print("")
        print("Columns that could not be paired by name. They are NOT compared —")
        print("pairing leftovers by position can agree as easily as disagree.")
        print("Fill these in as `column_maps` at the top and run it again:")
        print("   column_maps = {")
        for card, (theirs, ours_left) in unpaired.items():
            print(f'       "{card}": {{  # ours: {ours_left}')
            for name in theirs:
                print(f'           "{name}": "",')
            print("       },")
        print("   }")
    print("")
    print("Nothing was written. Insights logs its own executions, as it does "
          "whenever a query is opened.")


_read_only = _reconcile(guard_only=True)
_reconcile()
