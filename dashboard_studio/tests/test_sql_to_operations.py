"""Pasted SQL -> Insights operations.

Driven through the REAL parser rather than hand-built analysis dicts: the point
of this path is that somebody pastes SQL, so the test starts where they do.

Expected operations are asserted IN FULL rather than spot-checked. The failure
mode here is a query that runs fine and answers something else, so "the right
keys are present" proves nothing.
"""

import unittest

from dashboard_studio.integrations.metabase.parser import analyze_sql
from dashboard_studio.integrations.metabase.sql_ops import (
    columns_from_meta,
    operations_from_sql,
)

APPLICANT = {
    "name": "String",
    "status": "String",
    "academic_year": "String",
    "fee": "Decimal",
    "applied_on": "Date",
    "headcount": "Integer",
    "po": "String",
}
# `name` and `status` are deliberately in BOTH: every Frappe table has a `name`,
# so an unqualified column in a joined query is genuinely ambiguous.
PURCHASE = {"name": "String", "ref": "String", "amount": "Decimal", "status": "String"}
COLUMNS = {"Student Applicant": APPLICANT, "Purchase Order": PURCHASE}


def run(sql, columns=None):
    return operations_from_sql(analyze_sql(sql), COLUMNS if columns is None else columns)


class TestSupported(unittest.TestCase):
    def test_count_by_group_in_full(self):
        result = run("SELECT `academic_year`, COUNT(*) FROM `tabStudent Applicant` "
                     "GROUP BY `academic_year`")
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"], [
            {"type": "source", "table": {"type": "table", "data_source": "Site DB",
                                         "table_name": "tabStudent Applicant"}},
            {"type": "summarize",
             "measures": [{"measure_name": "count", "column_name": "count",
                           "data_type": "Integer", "aggregation": "count"}],
             "dimensions": [{"dimension_name": "academic_year",
                             "column_name": "academic_year", "data_type": "String"}]},
        ])

    def test_a_where_clause_becomes_filter_operations(self):
        result = run("SELECT COUNT(*) FROM `tabStudent Applicant` "
                     "WHERE `status` = 'Enrolled'")
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"][1], {
            "type": "filter", "column": {"type": "column", "column_name": "status"},
            "operator": "=", "value": "Enrolled"})

    def test_a_numeric_filter_value_is_sent_as_a_number(self):
        """The parser hands everything back as text. "100" compared against a
        Decimal column is a string comparison that quietly matches nothing."""
        result = run("SELECT COUNT(*) FROM `tabStudent Applicant` WHERE `fee` >= 100")
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"][1]["value"], 100.0)
        self.assertNotIsInstance(result["operations"][1]["value"], str)

    def test_an_integer_column_gets_an_int_not_a_float(self):
        result = run("SELECT COUNT(*) FROM `tabStudent Applicant` WHERE `headcount` > 5")
        self.assertEqual(result["operations"][1]["value"], 5)
        self.assertIsInstance(result["operations"][1]["value"], int)

    def test_sum_of_a_numeric_column(self):
        result = run("SELECT `academic_year`, SUM(`fee`) FROM `tabStudent Applicant` "
                     "GROUP BY `academic_year`")
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"][1]["measures"], [
            {"measure_name": "sum_of_fee", "column_name": "fee",
             "data_type": "Decimal", "aggregation": "sum"}])

    def test_several_and_ed_filters_all_survive(self):
        result = run("SELECT COUNT(*) FROM `tabStudent Applicant` "
                     "WHERE `status` = 'Enrolled' AND `fee` >= 100")
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual([op["type"] for op in result["operations"]],
                         ["source", "filter", "filter", "summarize"])

    def test_a_date_column_can_be_grouped_by(self):
        result = run("SELECT `applied_on`, COUNT(*) FROM `tabStudent Applicant` "
                     "GROUP BY `applied_on`")
        self.assertEqual(result["operations"][1]["dimensions"][0]["data_type"], "Date")


class TestJoins(unittest.TestCase):
    """The join a screenshot was once thought to be needed for. Everything
    Insights' JoinArgs wants is in the SQL: both tables, the strategy, and both
    columns. The only thing SQL cannot supply is the types, and those come from
    the DocType metadata — which doubles as the check that both column names are
    real."""

    JOIN = ("SELECT a.`academic_year`, COUNT(*) FROM `tabStudent Applicant` a "
            "LEFT JOIN `tabPurchase Order` b ON b.`ref` = a.`po` "
            "WHERE b.`amount` >= 100 GROUP BY a.`academic_year`")

    def test_the_whole_operation_list_in_full(self):
        result = run(self.JOIN)
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"], [
            {"type": "source", "table": {"type": "table", "data_source": "Site DB",
                                         "table_name": "tabStudent Applicant"}},
            {"type": "join", "join_type": "left",
             "table": {"type": "table", "data_source": "Site DB",
                       "table_name": "tabPurchase Order"},
             "select_columns": [{"type": "column", "column_name": c}
                                for c in ["amount", "name", "ref", "status"]],
             "join_condition": {
                 "left_column": {"type": "column", "column_name": "po"},
                 "right_column": {"type": "column", "column_name": "ref"}}},
            {"type": "filter", "column": {"type": "column", "column_name": "amount"},
             "operator": ">=", "value": 100.0},
            {"type": "summarize",
             "measures": [{"measure_name": "count", "column_name": "count",
                           "data_type": "Integer", "aggregation": "count"}],
             "dimensions": [{"dimension_name": "academic_year",
                             "column_name": "academic_year", "data_type": "String"}]},
        ])

    def test_the_left_column_is_the_source_table_whichever_side_it_was_typed(self):
        flipped = run(self.JOIN.replace("ON b.`ref` = a.`po`", "ON a.`po` = b.`ref`"))
        self.assertTrue(flipped["supported"], flipped["reasons"])
        self.assertEqual(flipped["operations"][1]["join_condition"],
                         run(self.JOIN)["operations"][1]["join_condition"])

    def test_a_joined_column_is_typed_from_its_own_doctype(self):
        """`amount` only exists on Purchase Order. Typing it against the source
        table would make the filter value a string and match nothing."""
        result = run("SELECT COUNT(*) FROM `tabStudent Applicant` a "
                     "JOIN `tabPurchase Order` b ON b.`ref` = a.`po` "
                     "WHERE b.`amount` > 5")
        self.assertIsInstance(result["operations"][2]["value"], float)

    def test_summing_a_column_of_the_joined_table(self):
        result = run("SELECT a.`academic_year`, SUM(b.`amount`) "
                     "FROM `tabStudent Applicant` a "
                     "JOIN `tabPurchase Order` b ON b.`ref` = a.`po` "
                     "GROUP BY a.`academic_year`")
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"][-1]["measures"], [
            {"measure_name": "sum_of_amount", "column_name": "amount",
             "data_type": "Decimal", "aggregation": "sum"}])


class TestMetabaseCompiledSql(unittest.TestCase):
    """The shape Metabase actually emits, end to end.

    Metabase wraps every joined table in derived tables and appends its own row
    cap. That combination refused every real report until the wrappers could be
    flattened, so this is the test that says the tool works on the SQL people
    have rather than on the SQL a test would write.
    """

    SQL = """SELECT `Student Applicant Model - Name`.`gender` AS `gender`,
                    COUNT(*) AS `count`
             FROM `tabStudent Admission UCC`
             LEFT JOIN (
               SELECT `__mb_source`.`name` AS `name`,
                      `__mb_source`.`gender` AS `gender`
               FROM ( select * from `tabStudent Applicant` ) AS `__mb_source`
             ) AS `Student Applicant Model - Name`
               ON `tabStudent Admission UCC`.`student_applicant` =
                  `Student Applicant Model - Name`.`name`
             WHERE `tabStudent Admission UCC`.`docstatus` = 1
             GROUP BY `Student Applicant Model - Name`.`gender`
             LIMIT 1048575"""

    COLUMNS = {
        "Student Admission UCC": {"name": "String", "student_applicant": "String",
                                  "docstatus": "Integer"},
        "Student Applicant": {"name": "String", "gender": "String"},
    }

    def test_it_converts_in_full(self):
        result = run(self.SQL, columns=self.COLUMNS)
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"], [
            {"type": "source", "table": {"type": "table", "data_source": "Site DB",
                                         "table_name": "tabStudent Admission UCC"}},
            {"type": "join", "join_type": "left",
             "table": {"type": "table", "data_source": "Site DB",
                       "table_name": "tabStudent Applicant"},
             "select_columns": [{"type": "column", "column_name": "gender"},
                                {"type": "column", "column_name": "name"}],
             "join_condition": {
                 "left_column": {"type": "column", "column_name": "student_applicant"},
                 "right_column": {"type": "column", "column_name": "name"}}},
            {"type": "filter", "column": {"type": "column", "column_name": "docstatus"},
             "operator": "=", "value": 1},
            {"type": "summarize",
             "measures": [{"measure_name": "count", "column_name": "count",
                           "data_type": "Integer", "aggregation": "count"}],
             "dimensions": [{"dimension_name": "gender", "column_name": "gender",
                             "data_type": "String"}]},
        ])

    def test_the_grouping_column_is_typed_from_the_JOINED_table(self):
        """`gender` lives on Student Applicant, reached through a wrapper alias.
        Typing it against the source table would be typing it against a table
        that has no such column."""
        result = run(self.SQL, columns=self.COLUMNS)
        self.assertEqual(result["operations"][-1]["dimensions"][0]["data_type"], "String")


class TestJoinRefusals(unittest.TestCase):
    def assert_refused(self, result, fragment):
        self.assertFalse(result["supported"], "expected a refusal")
        self.assertEqual(result["operations"], [])
        self.assertIn(fragment, " | ".join(result["reasons"]))

    def test_a_join_column_the_doctype_does_not_have_is_refused(self):
        """The check that makes reading a join out of text safe at all: a name
        that is not a real column must never reach Insights."""
        self.assert_refused(
            run("SELECT COUNT(*) FROM `tabStudent Applicant` a "
                "JOIN `tabPurchase Order` b ON b.`nonsense` = a.`po`"),
            "the join condition uses 'nonsense', which is not a column of Purchase Order")

    def test_a_source_side_column_is_checked_too(self):
        self.assert_refused(
            run("SELECT COUNT(*) FROM `tabStudent Applicant` a "
                "JOIN `tabPurchase Order` b ON b.`ref` = a.`nonsense`"),
            "not a column of Student Applicant")

    def test_a_column_in_both_tables_must_be_qualified(self):
        """After a join, `name` and `status` exist on both sides. Picking one is
        picking which rows the filter keeps."""
        self.assert_refused(
            run("SELECT COUNT(*) FROM `tabStudent Applicant` a "
                "JOIN `tabPurchase Order` b ON b.`ref` = a.`po` "
                "WHERE `status` = 'Paid'"),
            "is a column of both Student Applicant and Purchase Order")

    def test_the_joined_tables_columns_are_needed_too(self):
        self.assert_refused(
            run("SELECT COUNT(*) FROM `tabStudent Applicant` a "
                "JOIN `tabPurchase Order` b ON b.`ref` = a.`po`",
                columns={"Student Applicant": APPLICANT}),
            "the columns of Purchase Order are not known here")


class TestRefusals(unittest.TestCase):
    def assert_refused(self, result, fragment):
        self.assertFalse(result["supported"], "expected a refusal")
        self.assertEqual(result["operations"], [],
                         "a refused translation still handed back operations")
        joined = " | ".join(result["reasons"])
        self.assertIn(fragment, joined)
        return joined

    def test_a_subquery_is_refused(self):
        self.assert_refused(
            run("SELECT COUNT(*) FROM (SELECT 1 FROM `tabStudent Applicant`) x"),
            "subquery")

    def test_an_or_clause_is_refused(self):
        self.assert_refused(
            run("SELECT COUNT(*) FROM `tabStudent Applicant` "
                "WHERE `status` = 'A' OR `status` = 'B'"), "OR in WHERE")

    def test_distinct_union_having_case_are_all_refused(self):
        for sql, fragment in (
            ("SELECT DISTINCT `status` FROM `tabStudent Applicant`", "DISTINCT"),
            ("SELECT COUNT(*) FROM `tabStudent Applicant` HAVING COUNT(*) > 1", "HAVING"),
            ("SELECT CASE WHEN 1 THEN 2 END FROM `tabStudent Applicant`", "CASE"),
        ):
            self.assert_refused(run(sql), fragment)

    def test_without_column_types_nothing_is_translated(self):
        """A guessed data_type draws a chart that is wrong without saying so."""
        self.assert_refused(
            run("SELECT COUNT(*) FROM `tabStudent Applicant`", columns={}),
            "not known here")

    def test_a_column_the_table_does_not_have_is_refused(self):
        self.assert_refused(
            run("SELECT COUNT(*) FROM `tabStudent Applicant` WHERE `nonsense` = 'x'"),
            "'nonsense' is not a column")

    def test_a_like_filter_is_refused_by_name(self):
        self.assert_refused(
            run("SELECT COUNT(*) FROM `tabStudent Applicant` WHERE `status` LIKE 'E%'"),
            "not one this converter translates")

    def test_summing_a_text_column_is_refused(self):
        self.assert_refused(
            run("SELECT SUM(`status`) FROM `tabStudent Applicant`"),
            "only a number can be SUM'd")

    def test_grouping_by_a_number_is_refused(self):
        self.assert_refused(
            run("SELECT `fee`, COUNT(*) FROM `tabStudent Applicant` GROUP BY `fee`"),
            "groups only by")

    def test_grouping_without_aggregating_is_refused(self):
        self.assert_refused(
            run("SELECT `status` FROM `tabStudent Applicant` GROUP BY `status`"),
            "groups without aggregating")

    def test_non_dict_input_is_a_programming_error(self):
        with self.assertRaises(TypeError):
            operations_from_sql("SELECT 1", COLUMNS)


class TestColumnsFromMeta(unittest.TestCase):
    def test_frappe_fieldtypes_map_to_insights_data_types(self):
        columns = columns_from_meta([
            ("status", "Select"), ("fee", "Currency"), ("headcount", "Int"),
            ("applied_on", "Date"), ("seen_at", "Datetime"), ("notes", "Text"),
        ])
        self.assertEqual(columns["status"], "String")
        self.assertEqual(columns["fee"], "Decimal")
        self.assertEqual(columns["headcount"], "Integer")
        self.assertEqual(columns["applied_on"], "Date")
        self.assertEqual(columns["seen_at"], "Datetime")
        self.assertEqual(columns["notes"], "String")

    def test_name_is_always_there(self):
        """Every Frappe table has `name` and no DocType lists it as a field."""
        self.assertEqual(columns_from_meta([])["name"], "String")

    def test_an_unknown_fieldtype_degrades_to_string(self):
        self.assertEqual(columns_from_meta([("x", "Geolocation")])["x"], "String")

    def test_frappes_own_columns_are_there_even_though_no_DocType_lists_them(self):
        """`frappe.get_meta(...).fields` returns the fields somebody DEFINED.
        `parent` is not one of them, and on a child table it is the only column
        a join can possibly use — it refused as "not a column of X"."""
        columns = columns_from_meta([("score", "Float")])
        for standard in ("name", "parent", "parentfield", "parenttype", "idx",
                         "owner", "creation", "modified", "modified_by", "docstatus"):
            self.assertIn(standard, columns, f"{standard} is on every Frappe table")
        self.assertEqual(columns["creation"], "Datetime")
        self.assertEqual(columns["docstatus"], "Integer")
        self.assertEqual(columns["parent"], "String")

    def test_a_doctypes_own_field_wins_over_the_standard_one(self):
        self.assertEqual(columns_from_meta([("idx", "Data")])["idx"], "String")


class TestJoiningAChildTable(unittest.TestCase):
    """A child table joins on `parent`, which no DocType lists as a field."""

    def test_a_join_on_parent_converts(self):
        result = operations_from_sql(
            analyze_sql("SELECT COUNT(*) FROM `tabAssessment Result` a "
                        "LEFT JOIN `tabAssessment Result Detail` b "
                        "ON b.`parent` = a.`name`"),
            {"Assessment Result": columns_from_meta([("student", "Link")]),
             "Assessment Result Detail": columns_from_meta([("score", "Float")])})
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"][1]["join_condition"], {
            "left_column": {"type": "column", "column_name": "name"},
            "right_column": {"type": "column", "column_name": "parent"}})


if __name__ == "__main__":
    unittest.main()
