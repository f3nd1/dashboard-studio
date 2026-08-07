"""scripts/subquery_shapes.py groups the subquery refusals by what is in them.

It exists to stop the next wrapper rule being written against whichever example
arrived first. So the assertions are about the grouping being trustworthy: two
reports with the same shape and different table names land together, two with
genuinely different shapes do not, and it describes the statement the existing
rules LEAVE BEHIND rather than the raw file.
"""

import contextlib
import io
import pathlib
import re
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "subquery_shapes.py"

# Same shape, different tables and columns. One group.
OUTER_WHERE_A = ("SELECT `w`.`y` AS `y`, `w`.`avg` AS `avg` FROM ( "
                 "SELECT `c`.`year` AS `y`, AVG(`c`.`value`) AS `avg` FROM `tabQPO` "
                 "LEFT JOIN `tabQPO Child` c ON `tabQPO`.`name` = c.`parent` "
                 "GROUP BY `c`.`year` ) AS `w` WHERE `w`.`avg` > 5")
OUTER_WHERE_B = ("SELECT `w`.`m` AS `m`, `w`.`n` AS `n` FROM ( "
                 "SELECT `s`.`status` AS `m`, COUNT(*) AS `n` FROM `tabIntake` "
                 "LEFT JOIN `tabIntake Row` s ON `tabIntake`.`name` = s.`parent` "
                 "GROUP BY `s`.`status` ) AS `w` WHERE `w`.`n` > 0")
# A different shape: the outer limits rather than filters.
OUTER_LIMIT = ("SELECT `w`.`y` AS `y`, `w`.`avg` AS `avg` FROM ( "
               "SELECT `c`.`year` AS `y`, AVG(`c`.`value`) AS `avg` FROM `tabQPO` "
               "GROUP BY `c`.`year` ) AS `w` LIMIT 10")
# Nesting where no wrapper rule ever looks.
IN_CLAUSE = ("SELECT COUNT(*) AS `n` FROM `tabQPO` "
             "WHERE `tabQPO`.`name` IN ( SELECT `parent` FROM `tabQPO Child` )")
# Converts today — must not appear at all.
CLEAN = ("SELECT `academic_year`, COUNT(*) AS `n` FROM `tabStudent Applicant` "
         "GROUP BY `academic_year`")


class _Base(unittest.TestCase):
    def run_script(self, files, namespace_split=True, argv=None, raw_argv=None):
        saved_argv = list(sys.argv)
        with tempfile.TemporaryDirectory() as directory:
            for name, sql in files.items():
                (pathlib.Path(directory) / f"{name}.sql").write_text(sql)
            sys.argv = (raw_argv if raw_argv is not None else
                        ["subquery_shapes.py"] + (argv if argv is not None else [directory]))
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    if namespace_split:
                        # bench console: globals() and locals() are different dicts.
                        exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), {}, {})
                    else:
                        exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), {})
            finally:
                sys.argv = saved_argv
            return out.getvalue()

    def group_lines(self, text):
        """The counted lines, e.g. "    2  outer[where] items[same] ..."."""
        return [line.strip() for line in text.splitlines()
                if re.match(r"^\s+\d+\s+\w", line) and "bytes" not in line]


class TestItRuns(_Base):
    def test_runs_under_bench_consoles_split_namespaces(self):
        self.assertIn("distinct shapes", self.run_script({"a": OUTER_WHERE_A}, True))

    def test_runs_under_a_plain_module_level_exec(self):
        self.assertIn("distinct shapes", self.run_script({"a": OUTER_WHERE_A}, False))

    def test_no_blank_line_inside_an_indented_block(self):
        lines = SCRIPT.read_text().splitlines()
        indented = re.compile(r"^\s+\S")
        bad = [i + 1 for i in range(1, len(lines) - 1)
               if not lines[i].strip()
               and indented.match(lines[i - 1]) and indented.match(lines[i + 1])]
        self.assertEqual(bad, [], f"blank line inside a block at {bad} breaks piped paste")

    def test_no_directory_says_so(self):
        self.assertIn("I do not know which directory to read",
                      self.run_script({}, argv=[]))

    def test_bench_consoles_own_argv_is_not_scavenged_for_a_directory(self):
        """Same bug as bulk_dry_run's, same fix, asserted here too: these two
        scripts are handed over together and read the same folder."""
        text = self.run_script({"a": OUTER_WHERE_A},
                               argv=None, raw_argv=["/x/bench", "--site", "grc",
                                                    "console"])
        self.assertIn("I do not know which directory to read", text)


class TestTheGrouping(_Base):
    def test_the_same_shape_over_different_tables_is_one_group(self):
        """If table and column names reached the signature, 340 reports would
        come back as 340 groups and the output would be worthless."""
        text = self.run_script({"a": OUTER_WHERE_A, "b": OUTER_WHERE_B})
        groups = self.group_lines(text)
        self.assertEqual(len(groups), 1, text)
        self.assertTrue(groups[0].startswith("2  outer[where]"), groups)

    def test_a_different_shape_is_a_different_group(self):
        text = self.run_script({"a": OUTER_WHERE_A, "c": OUTER_LIMIT})
        self.assertEqual(len(self.group_lines(text)), 2, text)

    def test_nesting_that_is_not_a_wrapper_is_called_that(self):
        """An IN (...) is a different problem wearing the same refusal, and
        filing it with the wrappers would inflate the group that looks fixable."""
        text = self.run_script({"d": IN_CLAUSE})
        self.assertIn("no FROM-subquery", text)

    def test_a_report_that_converts_is_not_counted(self):
        text = self.run_script({"a": OUTER_WHERE_A, "ok": CLEAN})
        self.assertIn("1 of 2 reports refuse on a subquery", text)

    def test_it_describes_what_the_rules_LEAVE_BEHIND(self):
        """Metabase's per-table wrappers come off first. Describing the raw
        file would report every report as "selects_inside=3" and hide the
        shape that actually blocks it."""
        wrapped = OUTER_WHERE_A.replace(
            "`tabQPO Child` c", "( SELECT * FROM `tabQPO Child` ) c")
        text = self.run_script({"nested": wrapped})
        self.assertIn("selects_inside=1", text)
        self.assertNotIn("selects_inside=2", text)

    def test_it_names_the_smallest_file_in_the_biggest_group(self):
        """The next rule gets written against a real capture, so the output
        ends by naming the shortest one that represents the most reports."""
        text = self.run_script({"a": OUTER_WHERE_A, "b": OUTER_WHERE_B, "c": OUTER_LIMIT})
        self.assertIn("Send this one back", text)
        self.assertRegex(text, r"Send this one back[\s\S]*?\n   \S+/b\.sql")


class TestTheExpressionVocabulary(_Base):
    """The outer SELECT is the part no wrapper rule can remove. Whether ONE
    expression capability clears a group, or twenty are needed, is a question
    about what those expressions are BUILT FROM — so it is counted, not
    assumed."""

    # The reported capture, reduced. The inner items have to be something the
    # lift still declines, or the query converts and leaves this script's
    # population altogether. This has now expired twice — first `* 5`, when a
    # scale factor became a pre-summarize mutate, then `MONTH`, when
    # `functions.py` confirmed Insights has one.
    #
    # `TRIM` should last: it was checked against the whole 85-function list in
    # `functions.py` at v3.12.2 and Insights has no trim of any spelling. If it
    # ever gains one, this expires again — pick the replacement the same way,
    # from that list, rather than from what looks unlikely.
    COMPOSITE = ("SELECT CAST( AVG(`w`.`Q1`) + AVG(`w`.`Q5`) AS double ) / 2.0 "
                 "AS `Actual No` FROM ( "
                 "SELECT TRIM(`c`.`qn_1`) AS `Q1`, TRIM(`c`.`qn_5`) AS `Q5` "
                 "FROM `tabSurvey` LEFT JOIN `tabEntry` c "
                 "ON `tabSurvey`.`name` = c.`parent` WHERE `x` > 1 ) AS `w`")
    DATE_PART = COMPOSITE.replace("CAST( AVG(`w`.`Q1`) + AVG(`w`.`Q5`) AS double ) / 2.0",
                                  "YEAR(`w`.`Q1`)")

    def vocabulary_lines(self, text):
        section = text.split("has to be TRANSLATED rather than dropped", 1)[-1]
        section = section.split("use nothing but", 1)[0]
        return {token: int(count) for count, token in
                re.findall(r"^\s+(\d+)\s+(\S+)$", section, re.MULTILINE)}

    def test_the_functions_and_operators_are_counted(self):
        text = self.run_script({"a": self.COMPOSITE})
        self.assertEqual(self.vocabulary_lines(text),
                         {"CAST": 1, "AVG": 1, "+": 1, "/": 1})

    def test_arithmetic_over_aggregates_is_counted_as_one_capability(self):
        text = self.run_script({"a": self.COMPOSITE})
        self.assertIn("1 of 1 use nothing but arithmetic over", text)

    def test_anything_else_is_counted_apart(self):
        """A date part is not arithmetic over aggregates. Folding it in would
        promise that one capability covers reports it does not."""
        text = self.run_script({"a": self.COMPOSITE, "b": self.DATE_PART})
        self.assertIn("YEAR", text)
        self.assertIn("1 of 2 use nothing but arithmetic over", text)

    def test_a_column_name_in_backticks_is_not_read_as_an_operator(self):
        """`Total - Net` is a column, not a subtraction."""
        text = self.run_script({"a": self.COMPOSITE.replace("`w`.`Q1`", "`w`.`Total - Net`")})
        self.assertIn("1 of 1 use nothing but arithmetic over", text)

    def test_count_star_does_not_read_as_a_multiplication(self):
        sql = ("SELECT COUNT(*) AS `n` FROM ( SELECT TRIM(`c`.`x`) AS `x` FROM `tabSurvey` "
               "LEFT JOIN `tabEntry` c ON `tabSurvey`.`name` = c.`parent` "
               "WHERE `x` > 1 ) AS `w`")
        text = self.run_script({"a": sql})
        self.assertIn("1 of 1 use nothing but arithmetic over", text)
        self.assertNotIn("*", self.vocabulary_lines(text))


class TestTheCaseShapes(_Base):
    """A CASE that scores a survey answer and a CASE that labels a status share
    one refusal message. Telling them apart is the whole question behind "is
    this group one pattern", so the features are counted rather than eyeballed.
    """

    COMPOSITE_INDEX = (
        "SELECT CASE WHEN (CASE WHEN AVG(`w`.`1`) IS NULL THEN 0 ELSE 1 END) = 0 "
        "THEN 0 ELSE COALESCE(AVG(`w`.`1`), 0) / NULLIF(1, 0.0) END AS `HR` FROM ( "
        "SELECT CASE WHEN LOWER(`c`.`question`) LIKE "
        "'%I was helped to understand and engage with the vision and values%' "
        "THEN CASE WHEN LOWER(`c`.`response`) = 'agree' THEN 4 END END AS `1` "
        "FROM `tabSurvey` LEFT JOIN `tabResponse` c "
        "ON `tabSurvey`.`name` = c.`parent` ) AS `w`")
    PLAIN_LABEL = (
        "SELECT `w`.`Flag` AS `Flag`, COUNT(*) AS `n` FROM ( "
        "SELECT CASE WHEN LOWER(`c`.`answer`) = 'yes' THEN 1 ELSE 0 END AS `Flag` "
        "FROM `tabSurvey` LEFT JOIN `tabResponse` c "
        "ON `tabSurvey`.`name` = c.`parent` ) AS `w` GROUP BY `w`.`Flag`")

    def case_lines(self, text):
        section = text.split("does not.", 1)[-1].split("=" * 78, 1)[0]
        return [line.strip() for line in section.splitlines() if "branches=" in line]

    def test_a_composite_index_and_a_plain_label_are_different_shapes(self):
        text = self.run_script({"index": self.COMPOSITE_INDEX, "flag": self.PLAIN_LABEL})
        self.assertEqual(len(self.case_lines(text)), 2, text)

    def test_the_composite_index_shows_its_three_markers(self):
        """Many branches, a hardcoded question text, and null logic — the three
        things that make it report-specific rather than a general pattern."""
        text = self.run_script({"index": self.COMPOSITE_INDEX})
        line = self.case_lines(text)[0]
        self.assertIn("long-literals=1-2", line)
        self.assertIn("null-logic=yes", line)

    def test_a_plain_label_has_none_of_them(self):
        text = self.run_script({"flag": self.PLAIN_LABEL})
        line = self.case_lines(text)[0]
        self.assertIn("long-literals=0", line)
        self.assertIn("null-logic=no", line)

    def test_a_report_with_no_CASE_is_not_counted(self):
        text = self.run_script({"a": OUTER_WHERE_A})
        self.assertNotIn("What the CASE reports are built from", text)

    def test_a_flat_CASE_query_counts_even_without_a_subquery(self):
        """A CASE with no wrapper refuses on CASE alone. It is the same question
        about the same group, so restricting this section to subquery refusals
        would undercount it."""
        flat = ("SELECT CASE WHEN `status` = 'x' THEN 1 ELSE 0 END AS `f`, COUNT(*) "
                "FROM `tabStudent Applicant` GROUP BY `status`")
        text = self.run_script({"flat": flat})
        self.assertIn("What the CASE reports are built from (1 reports)", text)


class TestItSaysWhatItDoesNotKnow(_Base):
    def test_it_does_not_call_a_group_fixable(self):
        """A frequency count is not a proof. Two of the three existing rules
        were possible only because the wrapper provably returned the same rows
        as its inner query, and no group size changes that."""
        text = self.run_script({"a": OUTER_WHERE_A})
        self.assertIn("whether it is removable needs its own proof", text)
        for word in ("fixable", "can be removed", "TODO"):
            self.assertNotIn(word, text)

    def test_it_creates_nothing(self):
        source = SCRIPT.read_text()
        for forbidden in ("write_text", "mkdir", ".insert(", ".save(", "requests.",
                          "convert_sql(", "db.sql("):
            self.assertNotIn(forbidden, source, f"{forbidden} is not read-only")


if __name__ == "__main__":
    unittest.main()
