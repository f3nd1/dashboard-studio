"""Metabase's own wrapper subqueries, flattened — and only where provable.

Metabase compiles a drag-and-drop question into SQL that wraps each joined
table in derived tables. The real thing is checked in at
``reference/metabase/duration_from_counselling_to_admission.sql`` and this test
reads that file rather than a hand-written approximation of it, because the
whole question here is what Metabase actually emits.

The rule being tested: a derived table is replaced by its base table ONLY when
it is a pure projection — no WHERE, no GROUP BY, no aggregate, no DISTINCT, no
LIMIT, no join, and no item that renames or computes. Such a projection returns
the same rows as the table it reads, so the swap is an identity. Everything
else stays a subquery and is refused by name, because a WHERE or an aggregate in
there changes which rows come back and flattening it would answer a different
question without failing.
"""

import pathlib
import unittest

from dashboard_studio.integrations.metabase.parser import (
    analyze_sql,
    unwrap_derived_tables,
)

REAL = (pathlib.Path(__file__).resolve().parents[2]
        / "reference" / "metabase" / "duration_from_counselling_to_admission.sql")

# The inner wrapper, exactly as Metabase writes it.
INNER = "( select * from `tabStudent Applicant` ) AS `__mb_source`"
# The outer one: every column of the table, each aliased to its own name.
OUTER = ("(SELECT `__mb_source`.`name` AS `name`, `__mb_source`.`gender` AS `gender` "
         "FROM " + INNER + ") AS `Student Applicant Model - Name`")


def flat(sql):
    return " ".join(unwrap_derived_tables(sql).split())


class TestUnwrapping(unittest.TestCase):
    def test_a_select_star_wrapper_becomes_its_table(self):
        self.assertEqual(flat("FROM " + INNER),
                         "FROM `tabStudent Applicant` AS `__mb_source`")

    def test_the_two_level_metabase_wrapper_collapses_to_one_table(self):
        self.assertEqual(flat("LEFT JOIN " + OUTER),
                         "LEFT JOIN `tabStudent Applicant` AS `Student Applicant Model - Name`")

    def test_a_wrapper_without_an_alias_still_flattens(self):
        self.assertEqual(flat("FROM (SELECT * FROM `tabStudent Applicant`)"),
                         "FROM `tabStudent Applicant`")

    def test_a_comma_inside_a_backticked_alias_does_not_split_the_item_list(self):
        """Metabase names its derived tables after the display name, which can
        contain anything — a comma included. Splitting the projection on that
        comma produces two halves, neither of which reads as a column, and the
        wrapper stops flattening for a reason nobody could see."""
        self.assertEqual(
            flat("FROM (SELECT `Applicant, Model`.`gender` AS `gender` "
                 "FROM `tabStudent Applicant` AS `Applicant, Model`) AS `w`"),
            "FROM `tabStudent Applicant` AS `w`")

    def test_nothing_to_unwrap_is_returned_unchanged(self):
        sql = "SELECT COUNT(*) FROM `tabStudent Applicant` WHERE `status` = 'x'"
        self.assertEqual(unwrap_derived_tables(sql), sql)


class TestWhatIsNotUnwrapped(unittest.TestCase):
    """Each of these changes which rows come back. Flattening any of them would
    produce a query that runs, returns rows, and answers something else."""

    def assert_left_alone(self, inner):
        sql = "FROM (" + inner + ") AS `w`"
        self.assertEqual(unwrap_derived_tables(sql), sql)
        # …and it therefore still refuses, by name, as a subquery.
        result = analyze_sql("SELECT COUNT(*) " + sql)
        self.assertFalse(result["supported"])
        self.assertIn("subquery", " | ".join(result["reasons"]))

    def test_a_where_inside_is_not_flattened(self):
        self.assert_left_alone("SELECT * FROM `tabStudent Applicant` WHERE `paid` = 1")

    def test_an_aggregate_inside_is_not_flattened(self):
        self.assert_left_alone("SELECT COUNT(*) AS `n` FROM `tabStudent Applicant`")

    def test_a_group_by_inside_is_not_flattened(self):
        self.assert_left_alone("SELECT `gender` FROM `tabStudent Applicant` GROUP BY `gender`")

    def test_distinct_inside_is_not_flattened(self):
        self.assert_left_alone("SELECT DISTINCT `gender` FROM `tabStudent Applicant`")

    def test_a_limit_inside_is_not_flattened(self):
        self.assert_left_alone("SELECT * FROM `tabStudent Applicant` LIMIT 10")

    def test_a_join_inside_is_not_flattened(self):
        self.assert_left_alone(
            "SELECT * FROM `tabStudent Applicant` JOIN `tabPurchase Order` ON 1 = 1")

    def test_a_renaming_projection_is_not_flattened(self):
        """`x AS y` means the outer query reads `y`, which the base table has no
        column called. Flattening would leave a reference to nothing."""
        self.assert_left_alone("SELECT `gender` AS `sex` FROM `tabStudent Applicant`")

    def test_a_computed_column_inside_is_not_flattened(self):
        self.assert_left_alone(
            "SELECT `a` - `b` AS `duration` FROM `tabStudent Applicant`")

    def test_a_literal_column_is_not_a_projection_of_the_table(self):
        """`SELECT 1 FROM `tabX`` projects a constant, not the table's columns.
        It read as a column called "1" and got flattened away."""
        self.assert_left_alone("SELECT 1 FROM `tabStudent Applicant`")

    def test_a_union_inside_is_not_flattened(self):
        self.assert_left_alone(
            "SELECT * FROM `tabStudent Applicant` UNION SELECT * FROM `tabPurchase Order`")


class TestTheRealMetabaseQuery(unittest.TestCase):
    """The file in reference/ — Metabase's compiled output for a real report."""

    def setUp(self):
        self.sql = REAL.read_text()
        self.result = analyze_sql(self.sql)
        self.reasons = " | ".join(self.result["reasons"])

    def test_the_wrappers_no_longer_refuse_it(self):
        self.assertNotIn("subquery", self.reasons,
                         "Metabase's own passthrough wrappers still refuse")

    def test_the_source_and_the_join_are_read_correctly(self):
        self.assertEqual(self.result["source_doctype"], "Student Admission UCC")
        self.assertEqual(self.result["join"], {
            "doctype": "Student Applicant",
            "join_type": "left",
            "on": ("`tabStudent Admission UCC`.`student_applicant` = "
                   "`Student Applicant Model - Name`.`name`"),
            "source_column": "student_applicant",
            "join_column": "name",
        })

    def test_the_where_clause_survives_the_unwrapping(self):
        self.assertEqual(self.result["filters"], [
            {"field": "docstatus", "operator": "=", "value": "1",
             "table": "Student Admission UCC"}])

    def test_metabases_own_row_cap_is_not_treated_as_a_row_limit(self):
        self.assertNotIn("LIMIT", self.reasons)

    def test_it_still_refuses_for_its_computed_column(self):
        """Unwrapping is not the same as converting. This report's whole point is
        `student_signed_date - pre_course_counseling AS "Process Duration"`, and
        that is a computed column Insights would not get. Refused BY NAME rather
        than converted into a report missing the only column anybody wanted."""
        self.assertFalse(self.result["supported"])
        self.assertIn("Process Duration", self.reasons)


class TestRowLimits(unittest.TestCase):
    """A row limit was previously read and then silently ignored, so "top 10"
    converted into "all of them" — a different number, with no error."""

    def test_a_real_limit_refuses_by_name(self):
        result = analyze_sql("SELECT `status`, COUNT(*) FROM `tabStudent Applicant` "
                             "GROUP BY `status` LIMIT 10")
        self.assertFalse(result["supported"])
        self.assertIn("LIMIT 10", " | ".join(result["reasons"]))

    def test_metabases_export_cap_is_not_a_row_limit(self):
        result = analyze_sql("SELECT COUNT(*) FROM `tabStudent Applicant` LIMIT 1048575")
        self.assertTrue(result["supported"], result["reasons"])


class TestComputedSelectColumns(unittest.TestCase):
    """The SELECT list is not otherwise read, so a computed column used to be
    dropped in silence — the converted query then answers a smaller question."""

    def test_an_arithmetic_column_refuses_by_name(self):
        result = analyze_sql("SELECT `a` - `b` AS `Process Duration` "
                             "FROM `tabStudent Applicant`")
        self.assertFalse(result["supported"])
        self.assertIn("Process Duration", " | ".join(result["reasons"]))

    def test_a_ratio_expression_refuses(self):
        result = analyze_sql(
            "SELECT (CAST(COUNT(*) AS double) / NULLIF(CAST(COUNT(*) AS double), 0.0)) "
            "AS `rate` FROM `tabStudent Applicant`")
        self.assertFalse(result["supported"])
        self.assertIn("rate", " | ".join(result["reasons"]))

    def test_plain_and_aggregated_columns_are_fine(self):
        result = analyze_sql("SELECT `academic_year`, COUNT(*) AS `count` "
                             "FROM `tabStudent Applicant` GROUP BY `academic_year`")
        self.assertTrue(result["supported"], result["reasons"])

    def test_select_star_is_fine(self):
        result = analyze_sql("SELECT * FROM `tabStudent Applicant`")
        self.assertTrue(result["supported"], result["reasons"])


if __name__ == "__main__":
    unittest.main()
