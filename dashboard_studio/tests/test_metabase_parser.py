"""What `analyze_sql` reads out of a statement.

The join tests are the load-bearing ones. A join condition arrives as
``b.`ref` = a.`po`` — two qualified column references and an equals sign — and
Insights needs it as ``{left_column, right_column}`` oriented by TABLE, not by
which side of the ``=`` somebody happened to type. Getting that backwards
produces a join that runs, returns rows, and answers a different question, so
every shape that cannot be oriented with certainty refuses by name instead.
"""

import unittest

from dashboard_studio.integrations.metabase.parser import (
    analyze_sql,
    discover_frappe_doctypes,
)

JOIN_SQL = ("SELECT a.`name` FROM `tabStudent Applicant` a "
            "LEFT JOIN `tabPurchase Order` b ON b.`ref` = a.`po`")


class TestMetabaseParser(unittest.TestCase):
    def test_discovers_unique_doctypes(self):
        sql = "SELECT * FROM `tabStudent Applicant` JOIN `tabStudent Admission UCC` ON 1=1"
        self.assertEqual(
            discover_frappe_doctypes(sql),
            ["Student Applicant", "Student Admission UCC"],
        )


class TestSourceTable(unittest.TestCase):
    def test_the_source_is_the_FROM_table_not_the_first_one_mentioned(self):
        """A column of the joined table can appear in the SELECT list first.
        Taking the first `tab…` in the text would then build the query on the
        wrong side of the join."""
        result = analyze_sql(
            "SELECT `tabPurchase Order`.`ref` FROM `tabStudent Applicant` "
            "JOIN `tabPurchase Order` ON `tabPurchase Order`.`ref` = "
            "`tabStudent Applicant`.`po`")
        self.assertEqual(result["doctypes"][0], "Purchase Order")
        self.assertEqual(result["source_doctype"], "Student Applicant")

    def test_a_table_with_no_alias_still_resolves(self):
        result = analyze_sql("SELECT COUNT(*) FROM `tabStudent Applicant` "
                             "WHERE `status` = 'Enrolled'")
        self.assertEqual(result["source_doctype"], "Student Applicant")
        self.assertTrue(result["supported"], result["reasons"])


class TestJoin(unittest.TestCase):
    def test_a_simple_join_is_read_into_named_columns(self):
        result = analyze_sql(JOIN_SQL)
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["joins"], [{
            "doctype": "Purchase Order",
            "join_type": "left",
            "on": "b.`ref` = a.`po`",
            "source_table": "Student Applicant",
            "source_column": "po",
            "join_column": "ref",
        }])

    def test_the_sides_are_oriented_by_table_not_by_where_they_were_typed(self):
        """`b.ref = a.po` and `a.po = b.ref` are the same join. If the writing
        order decided which column went where, one of them would be wrong."""
        flipped = analyze_sql("SELECT a.`name` FROM `tabStudent Applicant` a "
                              "LEFT JOIN `tabPurchase Order` b ON a.`po` = b.`ref`")
        self.assertEqual(flipped["joins"][0]["source_column"], "po")
        self.assertEqual(flipped["joins"][0]["join_column"], "ref")

    def test_full_table_names_work_as_qualifiers_too(self):
        result = analyze_sql(
            "SELECT COUNT(*) FROM `tabStudent Applicant` "
            "INNER JOIN `tabPurchase Order` ON `tabPurchase Order`.`ref` = "
            "`tabStudent Applicant`.`po`")
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["joins"][0]["source_column"], "po")
        self.assertEqual(result["joins"][0]["join_column"], "ref")

    def test_every_join_keyword_maps_to_its_insights_type(self):
        for keyword, expected in (("LEFT ", "left"), ("LEFT OUTER ", "left"),
                                  ("RIGHT ", "right"), ("INNER ", "inner"),
                                  ("FULL OUTER ", "full"), ("", "inner")):
            result = analyze_sql(
                f"SELECT a.`name` FROM `tabStudent Applicant` a {keyword}JOIN "
                "`tabPurchase Order` b ON b.`ref` = a.`po`")
            self.assertTrue(result["supported"], result["reasons"])
            self.assertEqual(result["joins"][0]["join_type"], expected,
                             f"{keyword or 'bare'}JOIN")

    def test_aliases_resolve_in_the_where_clause_and_group_by(self):
        result = analyze_sql(
            "SELECT a.`academic_year`, COUNT(*) FROM `tabStudent Applicant` a "
            "JOIN `tabPurchase Order` b ON b.`ref` = a.`po` "
            "WHERE b.`status` = 'Paid' GROUP BY a.`academic_year`")
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["filters"], [{"field": "status", "operator": "=",
                                              "value": "Paid",
                                              "table": "Purchase Order"}])
        self.assertEqual(result["group_by"], [{"field": "academic_year",
                                               "table": "Student Applicant"}])

    def test_an_unqualified_column_keeps_no_table(self):
        result = analyze_sql("SELECT COUNT(*) FROM `tabStudent Applicant` "
                             "WHERE `status` = 'Enrolled' GROUP BY `academic_year`")
        self.assertEqual(result["filters"][0]["table"], None)
        self.assertEqual(result["group_by"][0]["table"], None)

    def test_an_aggregate_argument_is_stripped_of_its_qualifier(self):
        result = analyze_sql("SELECT SUM(b.`amount`) FROM `tabStudent Applicant` a "
                             "JOIN `tabPurchase Order` b ON b.`ref` = a.`po`")
        self.assertEqual(result["aggregations"],
                         [{"function": "SUM", "argument": "amount",
                           "table": "Purchase Order", "coerced": False}])


class TestJoinRefusals(unittest.TestCase):
    def assert_refused(self, sql, fragment):
        result = analyze_sql(sql)
        self.assertFalse(result["supported"], "expected a refusal")
        self.assertEqual(result["joins"], [], "a refused join was still handed back")
        joined = " | ".join(result["reasons"])
        self.assertIn(fragment, joined)
        return joined

    def test_a_compound_on_clause_is_refused(self):
        """Two conditions ANDed together is not something Insights'
        {left_column, right_column} can hold, and picking one of them silently
        widens the join."""
        self.assert_refused(
            "SELECT a.`name` FROM `tabStudent Applicant` a JOIN `tabPurchase Order` b "
            "ON b.`ref` = a.`po` AND b.`year` = a.`year`", "single equality")

    def test_a_non_equality_on_clause_is_refused(self):
        self.assert_refused(
            "SELECT a.`name` FROM `tabStudent Applicant` a JOIN `tabPurchase Order` b "
            "ON b.`ref` > a.`po`", "single equality")

    def test_an_unqualified_side_is_refused(self):
        """`ON ref = a.po` does not say which table `ref` belongs to."""
        self.assert_refused(
            "SELECT a.`name` FROM `tabStudent Applicant` a JOIN `tabPurchase Order` b "
            "ON ref = a.`po`", "does not name one column from")

    def test_both_sides_from_the_same_table_is_refused(self):
        self.assert_refused(
            "SELECT a.`name` FROM `tabStudent Applicant` a JOIN `tabPurchase Order` b "
            "ON a.`ref` = a.`po`", "does not name one column from")

    def test_a_self_join_is_refused(self):
        self.assert_refused(
            "SELECT a.`name` FROM `tabStudent Applicant` a JOIN `tabStudent Applicant` b "
            "ON b.`ref` = a.`po`", "joins Student Applicant more than once")

    def test_a_cross_join_is_refused_by_name(self):
        self.assert_refused(
            "SELECT a.`name` FROM `tabStudent Applicant` a CROSS JOIN `tabPurchase Order` b "
            "ON b.`ref` = a.`po`", "CROSS JOIN")

    def test_an_expression_on_clause_is_refused(self):
        self.assert_refused(
            "SELECT a.`name` FROM `tabStudent Applicant` a JOIN `tabPurchase Order` b "
            "ON b.`ref` = CONCAT(a.`po`, 'x')", "does not name one column from")

    def test_a_second_join_onto_a_table_not_yet_joined_is_refused(self):
        """Order matters: a join cannot attach to a table the query reaches
        only later, and Insights' left_column is the result SO FAR."""
        result = analyze_sql(
            "SELECT a.`name` FROM `tabStudent Applicant` a "
            "JOIN `tabPurchase Order` b ON b.`ref` = `tabSales Order`.`x` "
            "JOIN `tabSales Order` c ON c.`ref` = a.`so`")
        self.assertFalse(result["supported"])
        self.assertIn("has not joined yet", " | ".join(result["reasons"]))

    def test_an_unknown_alias_is_refused(self):
        """The join itself is fine here — the WHERE names a table that is not in
        the query, so its column cannot be typed against anything."""
        result = analyze_sql(
            "SELECT COUNT(*) FROM `tabStudent Applicant` a JOIN `tabPurchase Order` b "
            "ON b.`ref` = a.`po` WHERE z.`status` = 'x'")
        self.assertFalse(result["supported"])
        self.assertIn("'z' is not a table or alias", " | ".join(result["reasons"]))


if __name__ == "__main__":
    unittest.main()
