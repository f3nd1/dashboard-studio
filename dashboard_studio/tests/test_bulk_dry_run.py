"""scripts/bulk_dry_run.py must group by REASON, must not overstate what it
checked, and must create nothing.

The point of the script is to decide where effort goes, so the failure that
matters is not a crash — it is a plausible-looking summary that sends someone
to fix the wrong thing. Three shapes of that, all tested here: two reports
blocked by the same thing counted as two different blockers; a refusal it does
not recognise quietly filed under the nearest one it does; and a shape-only run
reporting reports as converting when the column and operator checks never ran.
"""

import contextlib
import io
import os
import pathlib
import re
import sys
import tempfile
import types
import unittest

from dashboard_studio.tests.fake_frappe import _make_fake_frappe

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "bulk_dry_run.py"

CLEAN = ("SELECT `academic_year`, COUNT(*) AS `n` FROM `tabStudent Applicant` "
         "GROUP BY `academic_year`")
# Two orderings by an expression, different expressions. One blocker, not two —
# grouping on the whole message would split it, which is the fault this script
# cannot have. (A row limit used to be this example; it converts now.)
ORDER_COUNT = CLEAN + " ORDER BY COUNT(*) DESC"
ORDER_SUM = CLEAN + " ORDER BY SUM(`fees`) DESC"
# Two blockers at once: a CASE and a computed column. Blocked by each, sole
# blocker for neither.
TWO_FAULTS = ("SELECT CASE WHEN `status` = 'x' THEN 1 ELSE 0 END AS `flag`, "
              "COUNT(*) AS `n` FROM `tabStudent Applicant` GROUP BY `status`")
# Passes every SHAPE check and still refuses on a site: LIKE is an operator the
# converter does not translate, and that check needs the column metadata.
LIKE = "SELECT COUNT(*) AS `n` FROM `tabStudent Applicant` WHERE `status` LIKE 'A%'"

META = {"Student Applicant": [("status", "Select"), ("academic_year", "Data")]}
UNCONDITIONAL = ["name", "owner", "creation", "modified", "modified_by",
                 "docstatus", "idx", "parent", "parentfield", "parenttype"]
TABLES = {"Student Applicant": UNCONDITIONAL + ["status", "academic_year"]}


class _Base(unittest.TestCase):
    def run_script(self, files, namespace_split=True, frappe=None, argv=None,
                   raw_argv=None, env=None, extra_dirs=(), sidecars=None):
        """Write `files` to a temp directory and run the real script over it.

        `sidecars` is `{report_name: json_text}`, written as `<name>.json`
        beside the `.sql` — the pair `metabase_export_sql.py` produces."""
        saved_modules = {k: v for k, v in sys.modules.items()
                         if k == "frappe" or k.startswith("dashboard_studio.")}
        saved_argv = list(sys.argv)
        saved_env = dict(os.environ)
        with tempfile.TemporaryDirectory() as root:
            # The layout of a real bench: the sites directory holds BOTH the
            # export folder and the site folders, one of which is named in
            # bench's own argv.
            directory = str(pathlib.Path(root) / "sql")
            pathlib.Path(directory).mkdir()
            for name, sql in files.items():
                (pathlib.Path(directory) / f"{name}.sql").write_text(sql)
            for name, text in (sidecars or {}).items():
                (pathlib.Path(directory) / f"{name}.json").write_text(text)
            for name in extra_dirs:
                (pathlib.Path(root) / name).mkdir()
                (pathlib.Path(root) / name / "stray.sql").write_text(CLEAN)
            os.environ.update({k: v.replace("<DIR>", directory)
                               for k, v in (env or {}).items()})
            if frappe is not None:
                for key in list(sys.modules):
                    if key == "frappe" or key.startswith("dashboard_studio."):
                        sys.modules.pop(key, None)
                sys.modules["frappe"] = frappe
            else:
                # No Bench: dashboard_studio.api.convert must fail to import, so
                # frappe has to be absent rather than left over from another test.
                sys.modules.pop("frappe", None)
                sys.modules.pop("dashboard_studio.api.convert", None)
            # `<DIR>` in an argv entry is substituted exactly as it is in env,
            # so a test can put the flag either side of the path.
            sys.argv = (raw_argv if raw_argv is not None
                        else ["bulk_dry_run.py"]
                        + [a.replace("<DIR>", directory)
                           for a in (argv if argv is not None else [directory])])
            here = pathlib.Path.cwd()
            if raw_argv is not None:
                # bench console runs from the sites directory, which is why a
                # site folder named in argv resolves as a relative path at all.
                os.chdir(root)
            out = io.StringIO()
            try:
                source = SCRIPT.read_text()
                with contextlib.redirect_stdout(out):
                    if namespace_split:
                        # bench console: globals() and locals() are different dicts.
                        exec(compile(source, str(SCRIPT), "exec"), {}, {})
                    else:
                        exec(compile(source, str(SCRIPT), "exec"), {})
            finally:
                if raw_argv is not None:
                    os.chdir(here)
                os.environ.clear()
                os.environ.update(saved_env)
                sys.argv = saved_argv
                for key in list(sys.modules):
                    if key == "frappe" or key.startswith("dashboard_studio."):
                        sys.modules.pop(key, None)
                sys.modules.update(saved_modules)
            return out.getvalue()

    def with_frappe(self):
        store = {}
        frappe = _make_fake_frappe(store, {"Dashboard Studio Editor"},
                                   ("Insights Query v3",))
        frappe._doctypes = {"Insights Query v3", "Student Applicant"}
        frappe.get_meta = lambda dt: types.SimpleNamespace(fields=[
            types.SimpleNamespace(fieldname=f, fieldtype=t) for f, t in META[dt]])
        frappe._table_columns = {k: list(v) for k, v in TABLES.items()}
        return frappe, store


class TestItRuns(_Base):
    def test_runs_under_bench_consoles_split_namespaces(self):
        self.assertIn("Bulk dry run", self.run_script({"a": CLEAN}, True))

    def test_runs_under_a_plain_module_level_exec(self):
        self.assertIn("Bulk dry run", self.run_script({"a": CLEAN}, False))

    def test_no_blank_line_inside_an_indented_block(self):
        """IPython reading stdin ends a block at the first blank line, so a
        piped paste would stop halfway through the function."""
        lines = SCRIPT.read_text().splitlines()
        indented = re.compile(r"^\s+\S")
        bad = [i + 1 for i in range(1, len(lines) - 1)
               if not lines[i].strip()
               and indented.match(lines[i - 1]) and indented.match(lines[i + 1])]
        self.assertEqual(bad, [], f"blank line inside a block at {bad} breaks piped paste")

    def test_no_directory_says_so_rather_than_crashing(self):
        text = self.run_script({"a": CLEAN}, argv=[])
        self.assertIn("I do not know which directory to read", text)


class TestItReadsTheDirectoryItWasGiven(_Base):
    """Two real bugs, reported twice from the live site, both here.

    `bench --site grc console` puts "grc" in sys.argv, and under the sites
    directory that IS a folder — so scanning argv for "anything that is a
    directory" found the site folder and reported confidently on the two files
    in it. And the function declares its own `directory`, so the documented
    "set it before exec()" was impossible: the local always shadowed it.
    """

    BENCH_ARGV = ["/home/x/ucc-sms-v2/env/bin/bench", "--site", "grc", "console"]

    def test_bench_consoles_own_argv_is_not_scavenged_for_a_directory(self):
        text = self.run_script({"a": CLEAN}, raw_argv=self.BENCH_ARGV,
                               extra_dirs=("grc",))
        self.assertIn("I do not know which directory to read", text)
        self.assertNotIn("report files under", text)

    def test_the_environment_variable_is_read_under_bench_console(self):
        """The one mechanism that works in all three run modes."""
        text = self.run_script({"a": CLEAN, "b": ORDER_COUNT},
                               raw_argv=self.BENCH_ARGV, extra_dirs=("grc",),
                               env={"DASHBOARD_STUDIO_SQL_DIR": "<DIR>"})
        self.assertIn("2 report files under", text)
        self.assertIn("directory came from $DASHBOARD_STUDIO_SQL_DIR", text)

    def test_the_environment_variable_beats_a_stray_site_folder(self):
        """The exact live failure: both are present, and the site folder must
        lose. It holds one .sql file, so picking it would report "1"."""
        text = self.run_script({"a": CLEAN, "b": ORDER_COUNT, "c": TWO_FAULTS},
                               raw_argv=self.BENCH_ARGV, extra_dirs=("grc",),
                               env={"DASHBOARD_STUDIO_SQL_DIR": "<DIR>"})
        self.assertIn("3 report files under", text)

    def test_it_prints_where_the_directory_came_from(self):
        """A silently wrong folder reports a real number for the wrong set.
        The source is printed so the next misfire is visible on line one."""
        text = self.run_script({"a": CLEAN})
        self.assertIn("directory came from the command line", text)

    def test_the_usage_says_that_presetting_the_variable_does_not_work(self):
        """It cannot: the function declares its own. Saying so is the fix for
        the instruction that wasted two attempts."""
        text = self.run_script({"a": CLEAN}, argv=[])
        self.assertIn("does NOT work", text)
        self.assertIn("DASHBOARD_STUDIO_SQL_DIR", text)

    def test_a_path_that_is_not_a_directory_says_which_source_gave_it(self):
        text = self.run_script({"a": CLEAN}, argv=["/no/such/place"])
        self.assertIn("Not a directory: /no/such/place", text)
        self.assertIn("from the command line", text)

    def test_an_empty_directory_says_so(self):
        self.assertIn("No .sql files under", self.run_script({}))


class TestGroupingByReason(_Base):
    """The whole value of the script: one blocker, one line, counted."""

    def test_two_reports_with_different_expressions_are_ONE_blocker(self):
        """The messages differ — they quote `COUNT(*)` and `SUM(\u0060fees\u0060)`.
        Grouping on the message text would report two blockers of one report
        each, and the answer to "what should we fix first" would be noise."""
        text = self.run_script({"counted": ORDER_COUNT, "summed": ORDER_SUM})
        rows = [line for line in text.splitlines()
                if "ORDER BY an expression" in line]
        self.assertEqual(len(rows), 1, f"the blocker was split:\n{text}")
        self.assertRegex(rows[0], r"^\s+2\s+2\s+ORDER BY an expression")
        self.assertIn("e.g. counted, summed", text)

    def test_a_report_with_two_blockers_is_sole_for_neither(self):
        """`sole` is the number this script is steered by: fix that blocker and
        that many reports convert. Counting a two-blocker report as sole for
        each would promise conversions that would not happen."""
        text = self.run_script({"both": TWO_FAULTS, "ordered": ORDER_COUNT})
        case = [ln for ln in text.splitlines() if ln.strip().endswith("CASE expression")]
        computed = [ln for ln in text.splitlines() if "computed column" in ln]
        order = [ln for ln in text.splitlines() if "ORDER BY an expression" in ln]
        self.assertRegex(case[0], r"^\s+1\s+0\s+")
        self.assertRegex(computed[0], r"^\s+1\s+0\s+")
        self.assertRegex(order[0], r"^\s+1\s+1\s+")

    def test_the_examples_name_reports_not_reasons(self):
        text = self.run_script({"enrolment_by_year": ORDER_COUNT})
        self.assertIn("e.g. enrolment_by_year", text)

    def test_the_sole_flag_lists_every_file_a_blocker_is_the_only_one_for(self):
        """The "e.g." names are drawn from every report a blocker stops, and
        most of those have other blockers too — so they are the wrong files to
        go and capture. This lists the ones fixing that blocker converts."""
        text = self.run_script({"ordered": ORDER_COUNT, "summed": ORDER_SUM,
                                "both": TWO_FAULTS}, argv=["<DIR>", "--sole"])
        section = text.split("Sole-blocker report files", 1)[1]
        self.assertIn("ORDER BY an expression  (2)", section)
        self.assertIn("ordered", section)
        self.assertIn("summed", section)
        # `both` has two blockers, so it is nobody's sole blocker.
        self.assertNotIn("both", section)

    def test_the_environment_variable_turns_it_on_under_bench_console(self):
        """argv belongs to bench there, so the flag has to have an env twin —
        the same reason the directory does."""
        text = self.run_script({"ordered": ORDER_COUNT},
                               raw_argv=TestItReadsTheDirectoryItWasGiven.BENCH_ARGV,
                               extra_dirs=("grc",),
                               env={"DASHBOARD_STUDIO_SQL_DIR": "<DIR>",
                                    "DASHBOARD_STUDIO_SOLE": "1"})
        self.assertIn("Sole-blocker report files", text)

    def test_without_the_flag_it_says_the_flag_exists(self):
        text = self.run_script({"ordered": ORDER_COUNT})
        self.assertNotIn("Sole-blocker report files", text)
        self.assertIn("--sole", text)

    def test_the_flag_is_not_read_as_the_directory(self):
        """`--sole` before the path, or after it, must not become the folder to
        read — the class of bug that made this script report on `grc` twice."""
        text = self.run_script({"ordered": ORDER_COUNT}, argv=["--sole", "<DIR>"])
        self.assertIn("1 report files under", text)
        self.assertIn("Sole-blocker report files", text)

    def test_a_clean_run_lists_no_sole_files(self):
        text = self.run_script({"a": CLEAN}, argv=["<DIR>", "--sole"])
        self.assertNotIn("Sole-blocker report files", text)

    def test_a_clean_run_says_so(self):
        text = self.run_script({"a": CLEAN})
        self.assertIn("nothing — every report converted", text)


class TestTheDedupeMode(_Base):
    """One report exported four times is one report, and the raw count says four.

    The export names the same report several ways, so a blocker stopping 92
    FILES may be stopping a dozen reports. Both numbers are printed: the file
    count is a fact, the base name is read off a naming convention.

    Nothing is dropped, and that is asserted rather than described — a mode
    that quietly filtered would report a smaller total and look like progress.
    """

    # The reported case, verbatim: four files, one report. The last one is the
    # awkward member — `-Average-` sits before two more suffixes, and stripping
    # those takes its trailing dash with them.
    OBJECTIVE_6 = ["Academic Staff Performance - Objective 6 - delete--1808",
                   "Academic Staff Performance - Objective 6 - retain--2041",
                   "Academic Staff Performance - Objective 6 - retain - Duplicate--2188",
                   "Academic Staff Performance - Objective 6 "
                   "-Average- - retain - Duplicate--2156"]

    def files(self, extra=()):
        return {name: ORDER_COUNT for name in list(self.OBJECTIVE_6) + list(extra)}

    def test_four_variants_of_one_report_count_as_one(self):
        text = self.run_script(self.files(), argv=["<DIR>", "--dedupe"])
        self.assertIn("4 report files under", text)
        self.assertIn("dedupe: 1 distinct reports across those 4 files", text)

    def test_the_blocker_line_carries_both_counts(self):
        text = self.run_script(self.files(), argv=["<DIR>", "--dedupe"])
        rows = [ln for ln in text.splitlines() if "ORDER BY an expression" in ln]
        self.assertRegex(rows[0], r"^\s+4\s+4\s+ORDER BY an expression")
        self.assertIn("distinct: 1 reports, 1 sole", text)

    def test_the_card_id_alone_is_not_a_variant(self):
        """Every file carries `--NNNN`; `metabase_export_sql.py` puts it there.
        Counting that as a variant would report every report as one."""
        text = self.run_script({"Plain Report--1902": ORDER_COUNT},
                               argv=["<DIR>", "--dedupe"])
        self.assertIn("0 of the 1 refusing files carry a variant", text)
        self.assertIn("dedupe: 1 distinct reports across those 1 files", text)

    def test_it_counts_how_many_refusing_files_carry_a_variant_at_all(self):
        text = self.run_script(self.files(extra=["Plain Report--1902"]),
                               argv=["<DIR>", "--dedupe"])
        self.assertIn("4 of the 5 refusing files carry a variant", text)

    def test_the_prefix_and_the_x_placeholder_are_variants_too(self):
        text = self.run_script({"Test - Enrolment by Year--1900": ORDER_COUNT,
                                "Enrolment by Year--1901": ORDER_COUNT,
                                "Withdrawals xxxxxxx--1902": ORDER_COUNT,
                                "Withdrawals--1903": ORDER_COUNT},
                               argv=["<DIR>", "--dedupe"])
        self.assertIn("dedupe: 2 distinct reports across those 4 files", text)

    def test_two_DIFFERENT_reports_are_not_collapsed(self):
        """The failure that would understate the work rather than overstate it.
        Only the observed markers are stripped, so nothing else merges."""
        text = self.run_script({"Objective 6--1": ORDER_COUNT,
                                "Objective 7--2": ORDER_COUNT},
                               argv=["<DIR>", "--dedupe"])
        self.assertIn("dedupe: 2 distinct reports across those 2 files", text)

    def test_it_DROPS_nothing(self):
        """A counting mode, not a filter. Every file is still read, still
        grouped, and still listed under --sole."""
        text = self.run_script(self.files(), argv=["<DIR>", "--dedupe", "--sole"])
        self.assertIn("4 report files under", text)
        rows = [ln for ln in text.splitlines() if "ORDER BY an expression" in ln]
        self.assertRegex(rows[0], r"^\s+4\s+4\s+")
        for name in self.OBJECTIVE_6:
            self.assertIn(name, text)

    def test_the_sole_list_groups_the_files_under_the_report(self):
        text = self.run_script(self.files(), argv=["<DIR>", "--dedupe", "--sole"])
        section = text.split("Sole-blocker report files", 1)[1]
        self.assertIn("ORDER BY an expression  (4 files, 1 reports)", section)
        self.assertIn("Academic Staff Performance - Objective 6  (4)", section)

    def test_without_the_flag_the_counts_are_unchanged_and_it_says_the_flag_exists(self):
        text = self.run_script(self.files())
        self.assertNotIn("distinct reports across", text)
        self.assertNotIn("distinct: ", text)
        rows = [ln for ln in text.splitlines() if "ORDER BY an expression" in ln]
        self.assertRegex(rows[0], r"^\s+4\s+4\s+")
        self.assertIn("--dedupe", text)

    def test_the_environment_variable_turns_it_on_under_bench_console(self):
        text = self.run_script(self.files(),
                               raw_argv=TestItReadsTheDirectoryItWasGiven.BENCH_ARGV,
                               extra_dirs=("grc",),
                               env={"DASHBOARD_STUDIO_SQL_DIR": "<DIR>",
                                    "DASHBOARD_STUDIO_DEDUPE": "1"})
        self.assertIn("dedupe: 1 distinct reports", text)

    def test_the_flag_is_not_read_as_the_directory(self):
        text = self.run_script({"ordered": ORDER_COUNT}, argv=["--dedupe", "<DIR>"])
        self.assertIn("1 report files under", text)
        self.assertIn("dedupe: 1 distinct reports", text)


class TestItDoesNotOverstateWhatItChecked(_Base):
    """A shape-only pass that reads as a verdict is worse than no pass."""

    def test_without_a_bench_it_refuses_to_say_convert_cleanly(self):
        text = self.run_script({"a": CLEAN, "b": LIKE})
        self.assertIn("SHAPE ONLY", text)
        self.assertIn("no SHAPE blocker", text)
        self.assertNotIn("convert cleanly", text)

    def test_and_it_names_what_it_could_not_check(self):
        text = self.run_script({"a": CLEAN})
        for missed in ("LIKE filter", "text\n   column", "bench console"):
            self.assertIn(missed, text)

    def test_with_a_bench_the_operator_check_runs_and_LIKE_refuses(self):
        """The same file, the same script: shape-only calls it clean, a site
        calls it blocked. That gap is exactly why the wording above matters."""
        frappe, _ = self.with_frappe()
        text = self.run_script({"likes": LIKE}, frappe=frappe)
        self.assertIn("convert cleanly", text)
        self.assertIn("filter operator (LIKE, IN, …)", text)
        self.assertIn("1 refuse", text)

    def test_it_names_WHICH_tables_could_not_be_read(self):
        """The group line says how many reports are blocked; this says which
        tables to go and look at, which is the half you can act on."""
        frappe, _ = self.with_frappe()
        frappe._table_columns = {}          # no table's schema can be read
        text = self.run_script({"a": CLEAN}, frappe=frappe)
        self.assertIn("Tables whose columns could not be read", text)
        self.assertIn("Student Applicant:", text)
        self.assertIn("e.g. a", text)

    def test_with_a_bench_a_column_the_table_lacks_is_counted(self):
        """Column drift is half the real failures and is invisible off-site."""
        frappe, _ = self.with_frappe()
        frappe._table_columns["Student Applicant"] = list(UNCONDITIONAL)
        text = self.run_script({"drifted": CLEAN}, frappe=frappe)
        self.assertIn("0 convert cleanly", text)
        self.assertIn("1 refuse", text)


class TestNothingIsForcedIntoTheWrongBucket(_Base):
    """A refusal the table does not know must be visible, not absorbed."""

    def fake_parser(self, reasons=None, raises=None):
        """Stand in for the real converter, so an unknown message can be
        produced on demand — every message the real one emits is in the table
        by construction, which is what makes this case hard to reach honestly."""
        parser = types.ModuleType("dashboard_studio.integrations.metabase.parser")
        ops = types.ModuleType("dashboard_studio.integrations.metabase.sql_ops")

        def analyze_sql(text):
            if raises:
                raise raises
            return {"supported": False, "reasons": list(reasons), "doctypes": []}
        parser.analyze_sql = analyze_sql
        ops.operations_from_sql = lambda *a, **k: {"reasons": [], "operations": []}
        return {"dashboard_studio.integrations.metabase.parser": parser,
                "dashboard_studio.integrations.metabase.sql_ops": ops}

    def run_with(self, modules, files):
        saved = {k: sys.modules.get(k) for k in modules}
        sys.modules.update(modules)
        try:
            return self.run_script(files)
        finally:
            for key, value in saved.items():
                if value is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = value

    def test_an_unrecognised_refusal_is_printed_verbatim(self):
        text = self.run_with(
            self.fake_parser(["something nobody has written a group for yet"]),
            {"odd": CLEAN})
        self.assertIn("matched no group", text)
        self.assertIn("something nobody has written a group for yet", text)
        self.assertIn("belongs in `groups`", text)

    def test_it_is_not_absorbed_into_a_group_that_nearly_matches(self):
        """"...is not translated" is a real group. A message that merely
        contains a similar phrase must not be filed under it."""
        text = self.run_with(self.fake_parser(["the moon is not translatable"]),
                             {"odd": CLEAN})
        self.assertIn("matched no group", text)
        self.assertNotIn("aggregation this converter does not translate", text)

    def test_a_converter_crash_is_a_finding_not_a_crash(self):
        """Every input here is a real report. The converter is meant to refuse,
        never to raise, so a raise is worth its own line in the summary."""
        text = self.run_with(self.fake_parser(raises=ValueError("boom")),
                             {"exploding": CLEAN})
        self.assertIn("the converter itself raised", text)
        self.assertIn("exploding", text)


class TestItCreatesNothing(_Base):
    def test_no_insights_record_is_written(self):
        frappe, store = self.with_frappe()
        self.run_script({"a": CLEAN, "b": ORDER_COUNT, "c": LIKE}, frappe=frappe)
        self.assertEqual(store, {}, "the dry run wrote something")

    def test_the_source_never_reaches_for_a_write(self):
        # A CALL, not the name: the docstring says out loud that it never calls
        # convert_sql, and a check that cannot survive its own documentation is
        # one somebody deletes.
        self.longMessage = False   # the haystack is the whole script
        source = SCRIPT.read_text()
        for forbidden in ("convert_sql(", ".insert(", ".save(", ".delete(",
                          "db.set_value", "db.sql(", "frappe.enqueue", "requests."):
            self.assertNotIn(forbidden, source,
                             f"bulk_dry_run.py contains {forbidden!r}, "
                             "which creates or executes something")


if __name__ == "__main__":
    unittest.main()


class TestTheUnchartableGroup(_Base):
    """Converts, but the chart cannot be drawn — its own group, on purpose.

    A month-of-year grouping is not a refusal and not "converts cleanly": the
    query is right and its numbers are right, and Insights' chart X axis takes
    only a date. Filed under either of the existing headings it would be lost,
    which is the whole problem at ~2000 reports — the point is one list rather
    than 2000 separate discoveries.
    """

    MONTHLY = ("SELECT MONTH(`applied_on`) AS `m`, COUNT(*) AS `n` "
               "FROM `tabStudent Applicant` GROUP BY MONTH(`applied_on`)")
    YEARLY = ("SELECT YEAR(`applied_on`) AS `y`, COUNT(*) AS `n` "
              "FROM `tabStudent Applicant` GROUP BY YEAR(`applied_on`)")

    def with_frappe(self):
        frappe, store = super().with_frappe()
        meta = {"Student Applicant": META["Student Applicant"] + [("applied_on", "Date")]}
        frappe.get_meta = lambda dt: types.SimpleNamespace(fields=[
            types.SimpleNamespace(fieldname=f, fieldtype=t) for f, t in meta[dt]])
        frappe._table_columns["Student Applicant"].append("applied_on")
        return frappe, store

    def test_a_month_grouping_is_reported_in_its_own_section(self):
        frappe, _ = self.with_frappe()
        text = self.run_script({"qipi": self.MONTHLY}, frappe=frappe)
        self.assertIn("Converts, but the chart cannot be drawn (1)", text)
        section = text.split("Converts, but the chart cannot be drawn", 1)[1]
        self.assertIn("MONTH  (1 files)", section)
        self.assertIn("qipi", section)

    def test_it_is_NOT_counted_as_a_refusal(self):
        """It converts. Reporting it as blocked would overstate the work and
        send somebody to fix a query that is already correct."""
        frappe, _ = self.with_frappe()
        text = self.run_script({"qipi": self.MONTHLY}, frappe=frappe)
        self.assertIn("1 convert cleanly", text)
        self.assertIn("0 refuse", text)

    def test_a_YEAR_grouping_is_not_in_it(self):
        """ADR-024 emits YEAR as a granularity on the date column, which stays
        chartable — so it never becomes a mutate and never lands here."""
        frappe, _ = self.with_frappe()
        text = self.run_script({"yearly": self.YEARLY}, frappe=frappe)
        self.assertNotIn("Converts, but the chart cannot be drawn", text)

    def test_a_report_that_REFUSES_is_not_listed_as_unchartable(self):
        """An unchartable axis on a query that does not convert is noise."""
        frappe, _ = self.with_frappe()
        text = self.run_script({"broken": self.MONTHLY + " UNION SELECT 1"},
                               frappe=frappe)
        self.assertNotIn("Converts, but the chart cannot be drawn", text)

    def test_the_parts_are_counted_apart(self):
        frappe, _ = self.with_frappe()
        text = self.run_script({"m": self.MONTHLY,
                                "d": self.MONTHLY.replace("MONTH", "DAY")},
                               frappe=frappe)
        self.assertIn("Converts, but the chart cannot be drawn (2)", text)
        self.assertIn("MONTH  (1 files)", text)
        self.assertIn("DAY  (1 files)", text)


class TestAutoChartCoverage(_Base):
    """Of the reports that convert, how many get their chart auto-built.

    The acceptance number for the display mapping lives here: the corpus run
    is the user's step, but the section's arithmetic — built vs fallback, the
    sidecar-less counted apart, reasons verbatim — is pinned on small sets.
    """

    SCALAR = "SELECT COUNT(*) AS `count` FROM `tabStudent Applicant`"

    def test_built_and_fallback_are_counted_apart(self):
        frappe, _ = self.with_frappe()
        text = self.run_script(
            {"single": self.SCALAR, "gauge": self.SCALAR, "bare": self.SCALAR},
            frappe=frappe,
            sidecars={"single": '{"display": "scalar", "series_settings": {}}',
                      "gauge": '{"display": "gauge", "series_settings": {}}'})
        self.assertIn("Auto-chart coverage: 1 of 2 converting reports", text)
        self.assertIn("drew this card as 'gauge'", text)
        # No sidecar is its own line, not a fallback reason — the fix is
        # re-running the exporter, not building anything.
        self.assertIn("1 more convert but have no .json sidecar", text)

    def test_a_refusing_report_is_not_in_the_coverage_arithmetic(self):
        """Chart coverage is a question about reports that CONVERT — and the
        refusal has to be a SITE-DEPTH one (LIKE, caught by the operator
        check), because a shape-level refusal never reaches this code at all
        and cannot exercise the guard. The first version used UNION and
        passed with the guard removed."""
        frappe, _ = self.with_frappe()
        text = self.run_script(
            {"likes": LIKE},
            frappe=frappe,
            sidecars={"likes": '{"display": "scalar", "series_settings": {}}'})
        self.assertIn("1 refuse", text)
        self.assertNotIn("Auto-chart coverage", text)

    def test_an_unreadable_sidecar_is_a_fallback_with_its_own_reason(self):
        frappe, _ = self.with_frappe()
        text = self.run_script({"odd": self.SCALAR}, frappe=frappe,
                               sidecars={"odd": "{not json"})
        self.assertIn("Auto-chart coverage: 0 of 1", text)
        self.assertIn("sidecar is not readable JSON", text)

    def test_off_bench_the_section_does_not_appear(self):
        """No operations off a bench, so nothing honest to count."""
        text = self.run_script({"single": self.SCALAR},
                               sidecars={"single": '{"display": "scalar"}'})
        self.assertNotIn("Auto-chart coverage", text)


class TestTheEntangledMarker(_Base):
    """A month card whose label CASE also consumes MONTH( is marked in the
    scan — the one-click regroup does not apply there, and a list that sizes
    the one-click work must not count hand edits into it.

    The entangled fixture is `month_label_lookup.sql` itself — the REAL wrapped
    shape the live card had, since a flat CASE in a GROUP BY refuses and never
    reaches this section at all (the first draft of this test found that)."""

    LABELLED = (pathlib.Path(__file__).resolve().parent / "fixtures"
                / "month_label_lookup.sql").read_text()
    PLAIN = ("SELECT MONTH(`custom_proposed_date`) AS `m`, COUNT(*) AS `n` "
             "FROM `tabQuality Action` GROUP BY MONTH(`custom_proposed_date`)")

    def with_frappe(self):
        frappe, store = super().with_frappe()
        meta = {"Quality Action": [("custom_proposed_date", "Date"),
                                   ("custom_aggregated_performance_index_api",
                                    "Data")]}
        frappe._doctypes = {"Insights Query v3", "Quality Action"}
        frappe.get_meta = lambda dt: types.SimpleNamespace(fields=[
            types.SimpleNamespace(fieldname=f, fieldtype=t) for f, t in meta[dt]])
        frappe._table_columns = {"Quality Action": UNCONDITIONAL + [
            "custom_proposed_date", "custom_aggregated_performance_index_api"]}
        return frappe, store

    def test_an_entangled_report_is_marked_and_counted(self):
        frappe, _ = self.with_frappe()
        text = self.run_script({"labelled": self.LABELLED, "plain": self.PLAIN},
                               frappe=frappe)
        self.assertIn("2 convert cleanly", text)
        section = text.split("Converts, but the chart cannot be drawn", 1)[1]
        self.assertIn("1 also compute labels from it, marked *", section)
        self.assertIn("labelled *", section)
        # The plain one keeps its unmarked line.
        self.assertRegex(section, r"\n      plain\n")


class TestTheRenamedGroup(_Base):
    """Converts, after renaming a computed column — its own section (ADR-037).

    Every report in it WAS a refusal before the rename shipped, so it belongs
    with the other "neither a refusal nor nothing" section rather than being
    invisible. The number is the question the fix was sized against: one card
    with an unlucky alias, or a naming habit across the survey reports.
    """

    # `score * 5 AS "Academic Year"` slugs onto `academic_year`, which is a
    # real column of tabStudent Applicant.
    COLLIDING = ("SELECT `w`.`status` AS `status`, AVG(`w`.`Academic Year`) AS `avg` "
                 "FROM ( SELECT `tabStudent Applicant`.`score` * 5 AS `Academic Year`, "
                 "`tabStudent Applicant`.`status` AS `status` "
                 "FROM `tabStudent Applicant` ) AS `w` GROUP BY `w`.`status`")

    def with_frappe(self):
        frappe, store = super().with_frappe()
        meta = {"Student Applicant": META["Student Applicant"] + [("score", "Int")]}
        frappe.get_meta = lambda dt: types.SimpleNamespace(fields=[
            types.SimpleNamespace(fieldname=f, fieldtype=t) for f, t in meta[dt]])
        frappe._table_columns["Student Applicant"].append("score")
        return frappe, store

    def test_the_rename_is_reported_with_both_names(self):
        frappe, _ = self.with_frappe()
        text = self.run_script({"survey": self.COLLIDING}, frappe=frappe)
        self.assertIn("Converts, after renaming a computed column (1 files)", text)
        section = text.split("Converts, after renaming a computed column", 1)[1]
        self.assertIn("survey: academic_year -> academic_year_calc", section)

    def test_it_counts_as_CONVERTING_not_as_a_refusal(self):
        """It converts. Counting it as blocked would overstate the work left
        and send somebody to fix a report that is already right."""
        frappe, _ = self.with_frappe()
        text = self.run_script({"survey": self.COLLIDING}, frappe=frappe)
        self.assertIn("1 convert cleanly", text)
        self.assertIn("0 refuse", text)

    def test_a_report_with_no_collision_is_not_in_it(self):
        frappe, _ = self.with_frappe()
        text = self.run_script({"plain": CLEAN}, frappe=frappe)
        self.assertNotIn("after renaming a computed column", text)

    def test_it_needs_a_SITE_because_the_real_columns_are_the_point(self):
        """Off a bench there is no schema to collide with, so the section
        cannot appear — and must not, since a shape-only pass would report
        every one of these as converting with nothing renamed."""
        text = self.run_script({"survey": self.COLLIDING})
        self.assertNotIn("after renaming a computed column", text)
