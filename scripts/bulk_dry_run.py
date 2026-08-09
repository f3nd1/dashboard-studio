"""Run every exported report's SQL through the converter and group the refusals.

    python scripts/bulk_dry_run.py path/to/exported_sql/
    python scripts/bulk_dry_run.py path/to/exported_sql/ --sole
    python scripts/bulk_dry_run.py path/to/exported_sql/ --dedupe

Under ``bench console`` there is no argv to pass, so set an environment
variable — do NOT set a `directory` variable before exec(), which cannot work
because the function declares its own and shadows it:

    import os
    os.environ['DASHBOARD_STUDIO_SQL_DIR'] = '/full/path/to/exported_sql'
    os.environ['DASHBOARD_STUDIO_SOLE'] = '1'      # optional, see below
    os.environ['DASHBOARD_STUDIO_DEDUPE'] = '1'    # optional, see below
    exec(open('apps/dashboard_studio/scripts/bulk_dry_run.py').read())

``--sole`` (or ``DASHBOARD_STUDIO_SOLE=1``) additionally lists every report
FILE each blocker is the sole blocker for. The "e.g." names in the main table
are drawn from every report a blocker stops, and most of those have several
blockers — so they are the wrong files to go and capture. The sole list is the
right one: fix that blocker and exactly those files convert.

``--dedupe`` (or ``DASHBOARD_STUDIO_DEDUPE=1``) prints a DISTINCT report count
beside every raw one. This export names the same report several times over —
"Academic Staff Performance - Objective 6" is four files: ``- delete--1808``,
``- retain--2041``, ``- retain - Duplicate--2188`` and ``-Average- - retain -
Duplicate--2156`` — so a blocker stopping 92 files may be stopping far fewer
actual reports, and "92" is the wrong size to plan against.

**It is a COUNTING mode and it drops nothing.** Every file is still read, still
grouped and still listed; the raw count keeps its place first, because the file
count is a fact and the base name is an inference from a naming convention.

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
    import json  # noqa: I001
    import os
    import pathlib
    import re
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
        # BEFORE the generic "could not be read" below. A WHERE the parser
        # cannot read is usually ordinary unsupported SQL rather than a parser
        # bug, and lumping them together made that group look like one thing
        # worth chasing. Each names what it actually found.
        ("WHERE condition using a CASE expression", "WHERE contains a CASE"),
        ("WHERE condition using a subquery", "WHERE contains a subquery"),
        ("WHERE condition using EXISTS", "WHERE uses EXISTS"),
        ("WHERE condition using IS NULL", "WHERE uses IS NULL"),
        ("WHERE condition using BETWEEN", "WHERE uses BETWEEN"),
        ("WHERE condition using REGEXP", "WHERE uses REGEXP"),
        ("WHERE condition using NOT", "WHERE uses NOT"),
        ("WHERE condition using a function call", "WHERE calls a function"),
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
        from dashboard_studio.integrations.metabase.chart_config import (
            chart_config_from_card,
            date_part_grouping,
        )
    except ImportError:
        chart_config_from_card = date_part_grouping = None
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
    # Dump every FILENAME a blocker is the sole blocker for, not just two
    # examples. The example names are drawn from all the reports a blocker
    # stops, most of which have other blockers too — so they are the wrong
    # thing to go and capture. This lists the ones where fixing that blocker
    # actually converts the report.
    sole_only = ("--sole" in sys.argv
                 and os.path.basename(sys.argv[0] or "") == script_name)
    sole_only = sole_only or os.environ.get("DASHBOARD_STUDIO_SOLE") not in (None, "", "0")
    # Count the same report once however many times the export named it. See
    # the module docstring: this DROPS NOTHING, it only counts a second way.
    dedupe = ("--dedupe" in sys.argv
              and os.path.basename(sys.argv[0] or "") == script_name)
    dedupe = dedupe or os.environ.get("DASHBOARD_STUDIO_DEDUPE") not in (None, "", "0")
    chosen_from = ""
    if directory:
        chosen_from = "the `directory` variable inside this function"
    elif os.environ.get("DASHBOARD_STUDIO_SQL_DIR"):
        directory = os.environ["DASHBOARD_STUDIO_SQL_DIR"]
        chosen_from = "$DASHBOARD_STUDIO_SQL_DIR"
    elif os.path.basename(sys.argv[0] or "") == script_name and len(sys.argv) > 1:
        arguments = [a for a in sys.argv[1:] if not a.startswith("--")]
        if arguments:
            directory = arguments[0]
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
    # The variant suffixes this export actually uses, lower-cased for matching.
    # Exactly the observed ones and no more: a marker list that guesses would
    # collapse two genuinely different reports into one and UNDERSTATE the size
    # of the work, which is the same class of wrong answer as overstating it.
    # `Test - ` is the one that appears at the FRONT.
    # `-Average-` is listed WITHOUT its trailing dash: stripping the `- retain`
    # after it takes that dash with it (`.strip(" -")` below), so a marker
    # spelled `-average-` matches on its own and never in company — which is
    # every real case, since it is always followed by something.
    variant_suffixes = ("- delete", "- retain", "- duplicate", "-average")
    variant_prefixes = ("test - ",)
    def base_name(report):
        """``(base, carries_a_variant_suffix)``. The trailing ``--NNNN`` is the
        Metabase card id `metabase_export_sql.py` appends to every file, so
        stripping it is not a variant and does not set the flag."""
        text = re.sub(r"--\d+$", "", report).strip()
        # A run of x's is a placeholder somebody typed; the observed one is
        # seven, and no real report name contains four in a row. Removed
        # wherever it sits, unlike the suffixes, which are stripped from the end.
        found = bool(re.search(r"(?i)x{4,}", text))
        text = re.sub(r"(?i)x{4,}", "", text).strip(" -").strip()
        changed = True
        while changed:
            changed = False
            for marker in variant_prefixes:
                if text.lower().startswith(marker):
                    text = text[len(marker):].strip(" -").strip()
                    changed = found = True
            for marker in variant_suffixes:
                if text.lower().endswith(marker):
                    text = text[:-len(marker)].strip(" -").strip()
                    changed = found = True
        # Never return nothing: a name that is entirely markers is still one
        # report, and an empty key would merge every such file into one.
        return (text or report), found
    def distinct(reports):
        return len({base_name(r)[0] for r in reports})
    # Reports that CONVERT but whose chart cannot be drawn: grouped by a date
    # NUMBER (month-of-year, quarter, day-of-month). Its own group on purpose —
    # it is neither a refusal nor "converts cleanly", and filing it under either
    # loses it. Keyed by the part so `month` and `day` are counted apart.
    unchartable = {}
    # Auto-chart coverage: of the reports that CONVERT, how many get their
    # chart built from the sidecar, and what stops the rest. Only measurable
    # at site depth — the chart is built from the typed operations.
    chart_built, chart_fallback, chart_no_sidecar = [], {}, []
    clean, blocked, ungrouped = [], {}, {}
    unreadable_tables = {}
    per_report = {}
    variant_named = set()
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
                converted = ({"reasons": [f"the columns of {', '.join(unreadable)} "
                                          "are not known here"], "operations": []}
                             if unreadable
                             else operations_from_sql(analysis, columns))
                reasons = converted["reasons"]
                # Only asked of reports that CONVERT — an unchartable axis on a
                # query that refuses is not a finding, it is noise.
                if not reasons and date_part_grouping:
                    part = date_part_grouping(converted["operations"])
                    if part:
                        unchartable.setdefault(part["part"], []).append(report)
                if not reasons and chart_config_from_card:
                    sidecar = path.with_suffix(".json")
                    if not sidecar.is_file():
                        chart_no_sidecar.append(report)
                    else:
                        try:
                            side = json.loads(sidecar.read_text())
                        except Exception:
                            side = None
                        config, _kind, why = (chart_config_from_card(
                            side, converted["operations"])
                            if isinstance(side, dict)
                            else (None, None, "the sidecar is not readable JSON"))
                        if config:
                            chart_built.append(report)
                        else:
                            chart_fallback.setdefault(
                                " ".join(str(why).split()), []).append(report)
        except Exception as error:
            # A crash is a finding in its own right: every input here is a real
            # report, and the converter is supposed to refuse, not raise.
            reasons = [f"converter raised {type(error).__name__}: {error}"]
        if not reasons:
            clean.append(report)
            continue
        if base_name(report)[1]:
            variant_named.add(report)
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
    if dedupe:
        stems = [p.stem for p in files]
        refusing = [r for r in stems if r not in set(clean)]
        print(f"   dedupe: {distinct(stems)} distinct reports across those "
              f"{len(files)} files")
        print(f"           {len(refusing)} refuse, and they are "
              f"{distinct(refusing)} distinct reports")
        print(f"           {len(variant_named)} of the {len(refusing)} refusing "
              "files carry a variant")
        print("           suffix at all — the rest are named once")
        print("   Nothing was dropped. Every file below is still counted, still")
        print("   grouped and still listed; this is a second way of counting the")
        print("   same set, and the raw file count stays first because it is the")
        print("   fact and the base name is read off a naming convention.")
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
    if typed and (chart_built or chart_fallback or chart_no_sidecar):
        covered = len(set(chart_built))
        eligible = covered + len({r for v in chart_fallback.values() for r in v})
        print()
        print("=" * 78)
        print(f"Auto-chart coverage: {covered} of {eligible} converting reports "
              "with a sidecar")
        print("=" * 78)
        print("   A covered report gets its Insights chart written by Convert —")
        print("   type, series and labels from the card's own settings. The rest")
        print("   convert fine and leave the chart for a person, for the reason")
        print("   shown. Reasons are this converter's own sentences, verbatim.")
        if chart_no_sidecar:
            print(f"   ({len(set(chart_no_sidecar))} more convert but have no "
                  ".json sidecar beside them — re-run")
            print("   scripts/metabase_export_sql.py, which now writes the pair.)")
        for why in sorted(chart_fallback, key=lambda k: -len(set(chart_fallback[k]))):
            reports = sorted(set(chart_fallback[why]))
            print(f"   {len(reports):>5}  {why}")
            print(f"          e.g. {', '.join(reports[:examples_per_group])}")
    if unchartable:
        print()
        print("=" * 78)
        total = sum(len(set(v)) for v in unchartable.values())
        print(f"Converts, but the chart cannot be drawn ({total})")
        print("=" * 78)
        print("   These are NOT refusals and NOT in the counts above. The query")
        print("   converts and its numbers are right; it groups by a date NUMBER")
        print("   (month-of-year, quarter, day-of-month), and Insights' chart X")
        print("   axis takes only a date. Each has a one-click 'group by year")
        print("   instead' in the converter — which is a DIFFERENT question, so")
        print("   nothing here changes anything by itself.")
        for part in sorted(unchartable, key=lambda key: -len(set(unchartable[key]))):
            reports = sorted(set(unchartable[part]))
            print()
            line = f"   {part.upper()}  ({len(reports)} files"
            print(line + (f", {distinct(reports)} reports)" if dedupe else ")"))
            for name in reports:
                print(f"      {name}")
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
        # On its own line rather than as two more columns: the labels already
        # run wide, and a wrapped table is one nobody reads.
        if dedupe:
            print(f"                    distinct: {distinct(reports)} reports, "
                  f"{distinct(sole)} sole")
        print(f"                    e.g. {', '.join(reports[:examples_per_group])}")
    if not blocked:
        print("   nothing — every report converted")
    print()
    print("   'sole' is how many of those reports this is the ONLY blocker for —")
    print("   fix it and that many convert. A blocker with a high count and a low")
    print("   sole count unblocks nothing by itself. A report with three blockers")
    print("   is counted once in each group, so the counts do not sum to the total.")
    if sole_only and blocked:
        print()
        print("=" * 78)
        print("Sole-blocker report files — the ones worth capturing")
        print("=" * 78)
        print("   Every file where this blocker is the ONLY thing stopping it, so")
        print("   fixing it converts that file. These are the names to pull, not the")
        print("   'e.g.' ones above — those are drawn from every report a blocker")
        print("   stops, and most of those have other blockers too.")
        for label in sorted(blocked, key=lambda name: (-len(set(blocked[name])), name)):
            sole = sorted(r for r in set(blocked[label])
                          if per_report.get(r) == {label})
            if not sole:
                continue
            print()
            if not dedupe:
                print(f"   {label}  ({len(sole)})")
                for name in sole:
                    print(f"      {name}")
                continue
            # Same files, grouped under the report they are variants of, so the
            # repetition is visible rather than something to count by eye.
            print(f"   {label}  ({len(sole)} files, {distinct(sole)} reports)")
            by_base = {}
            for name in sole:
                by_base.setdefault(base_name(name)[0], []).append(name)
            for base in sorted(by_base):
                print(f"      {base}  ({len(by_base[base])})")
                for name in sorted(by_base[base]):
                    print(f"         {name}")
        if not any(per_report.get(r) == {label}
                   for label in blocked for r in set(blocked[label])):
            print()
            print("   none — every blocked report has more than one blocker")
    elif blocked:
        print()
        print("   Re-run with --sole (or set DASHBOARD_STUDIO_SOLE=1 under bench")
        print("   console) to list every file each blocker is the SOLE blocker for.")
    if not dedupe and blocked:
        print()
        print("   Re-run with --dedupe (or DASHBOARD_STUDIO_DEDUPE=1) to count the")
        print("   same report once however many times the export named it. Nothing")
        print("   is dropped — the raw counts stay, a distinct count joins them.")
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
