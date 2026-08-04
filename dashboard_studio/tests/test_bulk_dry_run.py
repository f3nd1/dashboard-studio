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
# Two row limits, different numbers. One blocker, not two — grouping on the
# whole message would split it, which is the fault this script cannot have.
LIMIT_TEN = CLEAN + " LIMIT 10"
LIMIT_FIFTY = CLEAN + " LIMIT 50"
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
                   raw_argv=None, env=None, extra_dirs=()):
        """Write `files` to a temp directory and run the real script over it."""
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
            sys.argv = (raw_argv if raw_argv is not None
                        else ["bulk_dry_run.py"] + (argv if argv is not None else [directory]))
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
        text = self.run_script({"a": CLEAN, "b": LIMIT_TEN},
                               raw_argv=self.BENCH_ARGV, extra_dirs=("grc",),
                               env={"DASHBOARD_STUDIO_SQL_DIR": "<DIR>"})
        self.assertIn("2 report files under", text)
        self.assertIn("directory came from $DASHBOARD_STUDIO_SQL_DIR", text)

    def test_the_environment_variable_beats_a_stray_site_folder(self):
        """The exact live failure: both are present, and the site folder must
        lose. It holds one .sql file, so picking it would report "1"."""
        text = self.run_script({"a": CLEAN, "b": LIMIT_TEN, "c": TWO_FAULTS},
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

    def test_two_reports_with_different_limits_are_ONE_blocker(self):
        """The messages differ — `LIMIT 10` and `LIMIT 50`. Grouping on the
        message text would report two blockers of one report each, and the
        answer to "what should we fix first" would be noise."""
        text = self.run_script({"ten": LIMIT_TEN, "fifty": LIMIT_FIFTY})
        rows = [line for line in text.splitlines() if "row limit (LIMIT)" in line]
        self.assertEqual(len(rows), 1, f"the limit blocker was split:\n{text}")
        self.assertRegex(rows[0], r"^\s+2\s+2\s+row limit \(LIMIT\)")
        self.assertIn("e.g. fifty, ten", text)

    def test_a_report_with_two_blockers_is_sole_for_neither(self):
        """`sole` is the number this script is steered by: fix that blocker and
        that many reports convert. Counting a two-blocker report as sole for
        each would promise conversions that would not happen."""
        text = self.run_script({"both": TWO_FAULTS, "ten": LIMIT_TEN})
        case = [ln for ln in text.splitlines() if ln.strip().endswith("CASE expression")]
        computed = [ln for ln in text.splitlines() if "computed column" in ln]
        limit = [ln for ln in text.splitlines() if "row limit (LIMIT)" in ln]
        self.assertRegex(case[0], r"^\s+1\s+0\s+")
        self.assertRegex(computed[0], r"^\s+1\s+0\s+")
        self.assertRegex(limit[0], r"^\s+1\s+1\s+")

    def test_the_examples_name_reports_not_reasons(self):
        text = self.run_script({"enrolment_by_year": LIMIT_TEN})
        self.assertIn("e.g. enrolment_by_year", text)

    def test_a_clean_run_says_so(self):
        text = self.run_script({"a": CLEAN})
        self.assertIn("nothing — every report converted", text)


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
        self.run_script({"a": CLEAN, "b": LIMIT_TEN, "c": LIKE}, frappe=frappe)
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
