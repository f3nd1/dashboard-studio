"""Pasted SQL -> Insights operations.

Driven through the REAL parser rather than hand-built analysis dicts: the point
of this path is that somebody pastes SQL, so the test starts where they do.

Expected operations are asserted in full and against the MBQL path's output for
the same question — if the two converters ever disagree about what a query
means, that is the bug worth catching, not a formatting difference.
"""

import unittest

from dashboard_studio.integrations.metabase.mbql import translate_card
from dashboard_studio.integrations.metabase.parser import analyze_sql
from dashboard_studio.integrations.metabase.sql_ops import (
    columns_from_meta,
    operations_from_sql,
)

COLUMNS = {
    "name": "String",
    "status": "String",
    "academic_year": "String",
    "fee": "Decimal",
    "applied_on": "Date",
    "headcount": "Integer",
}


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


class TestAgreesWithTheCardPath(unittest.TestCase):
    """Two converters, one question. A disagreement here is the real hazard."""

    def test_the_same_question_produces_the_same_operations(self):
        sql = ("SELECT `academic_year`, COUNT(*) FROM `tabStudent Applicant` "
               "WHERE `status` = 'Enrolled' GROUP BY `academic_year`")
        from_sql = run(sql)

        card = {"id": 1, "dataset_query": {"lib/type": "mbql/query", "stages": [{
            "lib/type": "mbql.stage/mbql", "source-table": 1,
            "filters": [["=", {}, ["field", {}, 11], "Enrolled"]],
            "aggregation": [["count", {}]],
            "breakout": [["field", {}, 12]]}]}}
        from_card = translate_card(card, {
            "tables": {1: {"name": "tabStudent Applicant"}},
            "fields": {11: {"name": "status", "data_type": "String"},
                       12: {"name": "academic_year", "data_type": "String"}}})

        self.assertTrue(from_sql["supported"], from_sql["reasons"])
        self.assertTrue(from_card["supported"], from_card["reasons"])
        self.assertEqual(from_sql["operations"], from_card["operations"],
                         "the SQL and card paths disagree about the same question")


class TestRefusals(unittest.TestCase):
    def assert_refused(self, result, fragment):
        self.assertFalse(result["supported"], "expected a refusal")
        self.assertEqual(result["operations"], [],
                         "a refused translation still handed back operations")
        joined = " | ".join(result["reasons"])
        self.assertIn(fragment, joined)
        return joined

    def test_a_join_is_refused_and_says_why(self):
        """The line. analyze_sql hands a join condition back as text with table
        aliases in it; splitting that is how a wrong join gets built."""
        joined = self.assert_refused(
            run("SELECT a.`name` FROM `tabStudent Applicant` a "
                "JOIN `tabPurchase Order` b ON b.`ref` = a.`po`"),
            "this query joins tables")
        self.assertIn("Build the join in Insights", joined)

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


if __name__ == "__main__":
    unittest.main()
