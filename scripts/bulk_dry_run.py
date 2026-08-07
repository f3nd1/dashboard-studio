"""Run every exported report's SQL through the converter and group the refusals.

    python scripts/bulk_dry_run.py path/to/exported_sql/

Under ``bench console`` there is no argv to pass, so set an environment
variable — do NOT set a `directory` variable before exec(), which cannot work
because the function declares its own and shadows it:

    import os
    os.environ['DASHBOARD_STUDIO_SQL_DIR'] = '/full/path/to/exported_sql'
    exec(open('apps/dashboard_studio/scripts/bulk_dry_run.py').read())

argv is read ONLY when this file is run as a script. `bench --site grc console`
puts "grc" in sys.argv, and under the sites directory that IS a folder, so
scanning argv for "anything that is a directory" silently read the site folder
and reported a real number for the wrong two files. The resolved path and where
it came from are printed on every run.

Also runs under ``bench --site <site> console`` — pasted, piped, or exec'd —
where it additionally checks every column against the real schema (see "Two
depths" below). Point it at a directory of ``.sql`` files, one per report; the
file name is the report name in the output.

**Read-only, and it creates nothing.** It calls `analyze_sql` and
`operations_from_sql`, which are pure functions, and — on a site — reads DocType
metadata. It never calls `convert_sql`, so no Insights record is written, and it
executes no SQL anywhere.

It exists to answer one question: **where is the effort worth spending?** Fixing
the blocker that stops 40 reports beats fixing the one in front of you. The
output groups by REASON rather than by report, counts how many reports each
blocker stops, and — the number to steer by — how many it is the *only* blocker
for. A reason that stops 40 reports but is never the sole blocker unblocks
nothing on its own.

**Two depths, and the output says which one ran.** Without a Bench, only the
shape of the SQL is checked: subqueries, joins, LIMIT, CASE, computed columns.
On the live site every column is also checked against the real table, which is
where the second half of the real failures have come from. A report that passes
the first and fails the second is not a report that converts.

ponytail: no blank lines inside the function, and everything inside one
function with its imports. ``bench console`` runs an embedded IPython where
globals() and locals() are different dicts, so a bare exec(open(...).read())
would leave module-level names unreachable from the functions that need them —
that fault has already cost a round trip twice in this project.
"""

def _dry_run():
    # noqa on the block: isort wants a blank line before the first-party
    # import, and a blank line here breaks the piped-paste form.
    import os  # noqa: I001
    import pathlib
    import sys
    # INSIDE the function on purpose — see the note above about bench console's
    # split namespaces. Edit this when running somewhere argv cannot be passed.
    directory = ""
    script_name = "bulk_dry_run.py"
    # How many report names to show per group. Two is enough to look at a
    # representative case and a second one to check it is representative.
    examples_per_group = 2
    # Substring -> the group it belongs to. A SUBSTRING of the message, not a
    # pattern over it, so an interpolated column or DocType name cannot split
    # one blocker into five groups of one. Order matters: first match wins.
    #
    # Anything matching nothing lands in "ungrouped" and is printed verbatim
    # rather than forced into the nearest bucket — a mis-grouped blocker is a
    # wrong answer to "what should we fix first", which is the only question
    # this script exists to answer.
    groups = [
        ("subquery / nested SELECT", "subquery a wrapper rule could not flatten"),
        ("different LIMITs in one statement", "two row limits in one statement"),
        # BEFORE the GROUP BY entry below, whose "which is not a plain column"
        # this message also contains.
        ("Insights orders by a named column", "ORDER BY an expression"),
        ("is not a column this query produces", "ORDER BY a column the result drops"),
        ("CASE expression", "CASE expression"),
        ("window function (OVER)", "window function (OVER)"),
        ("HAVING clause", "HAVING clause"),
        ("DISTINCT", "DISTINCT"),
        ("UNION", "UNION"),
        # The specific ones first: "first match wins", and a CAST inside a
        # computed column is the blocker worth counting on its own now that the
        # arithmetic around it translates.
        ("converts a column, not the result of an expression",
         "computed column using CAST"),
        ("which has no aggregate in it", "computed column with no aggregate"),
        ("two questions in one query", "aggregate inside AND outside a computed column"),
        ("the SELECT list computes", "computed column in the SELECT list"),
        # These two BEFORE the join's "is not a column of", which they would
        # otherwise match — a computation reading the wrong kind of column is
        # not a join naming a column its table lacks, and filing it there sends
        # whoever reads the report to the wrong half of the query.
        ("not a column of any table this query reads",
         "computed column reads a column no table in the query has"),
        ("from a column that is not a", "computed column reads the wrong kind of column"),
        ("is not a column of", "join names a column the table does not have"),
        ("are not known here", "table's columns could not be read"),
        ("There is no DocType called", "no such DocType on this site"),
        ("join present but not a simple", "join not in the `tab<DocType>` … ON a = b shape"),
        ("JOIN has no Insights equivalent", "join type (CROSS, and friends)"),
        ("more than once (or to itself)", "same table joined twice, or to itself"),
        ("is not a single equality", "join condition is not one equality"),
        ("does not name one column from", "join condition sides cannot be told apart"),
        ("which this converter does not know", "join attaches to a table not yet in scope"),
        ("is not a table or alias", "qualifier names no table or alias"),
        ("unparsed WHERE condition", "WHERE condition could not be read"),
        ("is not one this converter translates", "filter operator (LIKE, IN, …)"),
        ("is not translated", "aggregation this converter does not translate"),
        ("only a number can be", "aggregate over a non-numeric column"),
        ("Insights groups only by", "GROUP BY a numeric column"),
        ("which is not a plain column", "GROUP BY an expression"),
        ("coerced to a number, not the column itself", "GROUP BY a `* 1` coercion"),
        ("groups without aggregating", "GROUP BY with no aggregate"),
        ("no table found in this query", "no `tab<DocType>` table in the query"),
        ("converter raised", "the converter itself raised — a bug, not a refusal"),
    ]
    try:
        from dashboard_studio.integrations.metabase.parser import analyze_sql
        from dashboard_studio.integrations.metabase.sql_ops import operations_from_sql
    except ImportError:
        # Running the file directly: the repo root is not on the path, only
        # scripts/. Under bench console the app is installed and this never runs.
        here = globals().get("__file__")
        root = str(pathlib.Path(here).resolve().parents[1]) if here else os.getcwd()
        # append rather than prepend: nothing else on the path provides this
        # package, and the write guard in this script's test reads a list
        # insertion as a Frappe document write.
        sys.path.append(root)
        from dashboard_studio.integrations.metabase.parser import analyze_sql
        from dashboard_studio.integrations.metabase.sql_ops import operations_from_sql
    try:
        from dashboard_studio.api.convert import _table_columns
        typed = True
    except Exception:
        # No Bench here. Shape only, and the output says so — never let a
        # shape-only pass read as "these convert".
        _table_columns, typed = None, False
    # Where the .sql files are. Resolved in ONE place and PRINTED, because
    # getting it wrong silently reads a different folder and reports a real
    # number for it. Three sources, most deliberate first.
    chosen_from = ""
    if directory:
        chosen_from = "the `directory` variable inside this function"
    elif os.environ.get("DASHBOARD_STUDIO_SQL_DIR"):
        directory = os.environ["DASHBOARD_STUDIO_SQL_DIR"]
        chosen_from = "$DASHBOARD_STUDIO_SQL_DIR"
    elif os.path.basename(sys.argv[0] or "") == script_name and len(sys.argv) > 1:
        directory = sys.argv[1]
        chosen_from = "the command line"
    # argv is read ONLY when this file was run AS a script. Under `bench
    # console` sys.argv belongs to bench — `bench --site grc console` — and
    # scanning it for anything that happens to be a directory found the site
    # folder `grc` and confidently reported on the two files in it.
    if not directory:
        print("I do not know which directory to read. Either:")
        print(f"   python scripts/{script_name} path/to/exported_sql/")
        print("or, under `bench console`, set the environment variable first:")
        print("   import os")
        print("   os.environ['DASHBOARD_STUDIO_SQL_DIR'] = '/full/path/to/exported_sql'")
        print(f"   exec(open('apps/dashboard_studio/scripts/{script_name}').read())")
        print("Setting a `directory` variable before exec() does NOT work: this")
        print("function declares its own, which would shadow it.")
        return
    folder = pathlib.Path(directory).expanduser()
    if not folder.is_dir():
        print(f"Not a directory: {folder}   (from {chosen_from})")
        return
    files = sorted(folder.rglob("*.sql"))
    if not files:
        print(f"No .sql files under {folder.resolve()}   (from {chosen_from})")
        return
    clean, blocked, ungrouped = [], {}, {}
    unreadable_tables = {}
    per_report = {}
    for path in files:
        report = path.stem
        try:
            analysis = analyze_sql(path.read_text())
            reasons = list(analysis["reasons"])
            if not reasons and typed:
                columns, unreadable = {}, []
                for doctype in analysis["doctypes"]:
                    try:
                        columns[doctype] = _table_columns(doctype)
                    except Exception as error:
                        unreadable.append(f"{doctype}: {error}")
                        # Tallied by TABLE as well as by report: the group line
                        # says how many reports are blocked, and this says WHICH
                        # tables to go and look at, which is the actionable half.
                        unreadable_tables.setdefault(
                            f"{doctype}: {error}", set()).add(report)
                reasons = ([f"the columns of {', '.join(unreadable)} are not known here"]
                           if unreadable
                           else operations_from_sql(analysis, columns)["reasons"])
        except Exception as error:
            # A crash is a finding in its own right: every input here is a real
            # report, and the converter is supposed to refuse, not raise.
            reasons = [f"converter raised {type(error).__name__}: {error}"]
        if not reasons:
            clean.append(report)
            continue
        found = set()
        for reason in reasons:
            label = next((name for text, name in groups if text in reason), None)
            if label is None:
                ungrouped.setdefault(reason, []).append(report)
                label = "ungrouped: " + " ".join(reason.split())[:70]
            found.add(label)
            blocked.setdefault(label, []).append(report)
        per_report[report] = found
    print("=" * 78)
    print("Bulk dry run — READ ONLY. No Insights query was created.")
    print("=" * 78)
    print(f"{len(files)} report files under {folder.resolve()}")
    print(f"   directory came from {chosen_from}")
    if typed:
        print(f"   {len(clean)} convert cleanly")
        print(f"   {len(files) - len(clean)} refuse")
        print("   depth: SHAPE + COLUMNS — every check the converter makes, so")
        print("   these numbers are the real ones.")
    else:
        # Never let a half-run read as an answer. The column, operator and type
        # checks all live past this point and all need a site, so a report with
        # no shape blocker may still refuse — LIKE, IN, averaging a text column,
        # a column the table does not have. Saying "converts cleanly" here would
        # overcount, and the overcount would look like good news.
        print(f"   {len(clean)} have no SHAPE blocker — which is NOT the same as")
        print("   converting, and must not be reported as if it were")
        print(f"   {len(files) - len(clean)} are blocked on shape alone")
        print("   depth: SHAPE ONLY. No Bench here, so the column, operator and")
        print("   type checks did not run — a LIKE filter, an average over a text")
        print("   column and a column the table no longer has all pass this run and")
        print("   refuse on a site. Run it under `bench console` for the real answer.")
    print()
    print("=" * 78)
    print("Blocked by — most reports first")
    print("=" * 78)
    print("   reports  sole  blocker")
    print("   -------  ----  -------")
    for label in sorted(blocked, key=lambda name: (-len(set(blocked[name])), name)):
        reports = sorted(set(blocked[label]))
        sole = [r for r in reports if per_report.get(r) == {label}]
        print(f"   {len(reports):>7}  {len(sole):>4}  {label}")
        print(f"                    e.g. {', '.join(reports[:examples_per_group])}")
    if not blocked:
        print("   nothing — every report converted")
    print()
    print("   'sole' is how many of those reports this is the ONLY blocker for —")
    print("   fix it and that many convert. A blocker with a high count and a low")
    print("   sole count unblocks nothing by itself. A report with three blockers")
    print("   is counted once in each group, so the counts do not sum to the total.")
    if unreadable_tables:
        print()
        print("=" * 78)
        print(f"Tables whose columns could not be read ({len(unreadable_tables)})")
        print("=" * 78)
        print("   Each line is one table and the error it gave. This is where that")
        print("   group's reports actually go wrong — a DocType that is not on this")
        print("   site, or a table the schema read cannot see.")
        for detail in sorted(unreadable_tables, key=lambda key: -len(unreadable_tables[key])):
            reports = sorted(unreadable_tables[detail])
            print(f"   {len(reports):>5}  {detail}")
            print(f"          e.g. {', '.join(reports[:examples_per_group])}")
    if ungrouped:
        print()
        print("=" * 78)
        print(f"Refusals that matched no group ({len(ungrouped)}) — verbatim")
        print("=" * 78)
        print("   These are printed whole rather than forced into the nearest")
        print("   bucket. A new refusal message belongs in `groups` above.")
        for reason, reports in sorted(ungrouped.items(), key=lambda kv: -len(kv[1])):
            print(f"   {len(set(reports)):>4}  {' '.join(reason.split())}")
            print(f"         e.g. {', '.join(sorted(set(reports))[:examples_per_group])}")
    print()
    print("Nothing was written. No query was executed.")


_dry_run()
