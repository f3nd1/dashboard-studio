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
             # Only what the query reads from Purchase Order: the join key and
             # the filtered column. `name` and `status` exist on that table and
             # are not carried, because nothing here asks for them.
             "select_columns": [{"type": "column", "column_name": c}
                                for c in ["amount", "ref"]],
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

    def test_an_UNQUALIFIED_column_is_still_carried_by_the_right_join(self):
        """`amount` is only on Purchase Order, so the SQL need not qualify it.
        If it were not attributed to that table it would not be carried, and
        the filter would reference a column the join never brought across."""
        result = run("SELECT COUNT(*) FROM `tabStudent Applicant` a "
                     "JOIN `tabPurchase Order` b ON b.`ref` = a.`po` "
                     "WHERE `amount` >= 100")
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual([c["column_name"] for c in result["operations"][1]["select_columns"]],
                         ["amount", "ref"])

    def test_a_column_used_only_by_the_GROUPING_is_carried(self):
        result = run("SELECT b.`status`, COUNT(*) FROM `tabStudent Applicant` a "
                     "JOIN `tabPurchase Order` b ON b.`ref` = a.`po` "
                     "GROUP BY b.`status`")
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual([c["column_name"] for c in result["operations"][1]["select_columns"]],
                         ["ref", "status"])

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


class TestParentWithChildTables(unittest.TestCase):
    """The shape most UCC quality reports are built in: one parent DocType
    joined to several of its child tables on `parent.name = child.parent`,
    filtered to one parent record, aggregated over a child column.

    N joins are N Insights operations. Each attaches its table to the result so
    far, which is exactly what join_condition.left_column means, so the second
    join is not a harder problem than the first — only a longer list.
    """

    SQL = ("SELECT AVG(`c`.`score`) AS `avg` "
           "FROM `tabQuality Performance Outcomes` "
           "LEFT JOIN `tabQPO Criteria` c "
           "  ON `tabQuality Performance Outcomes`.`name` = c.`parent` "
           "LEFT JOIN `tabQPO Band` b "
           "  ON `tabQuality Performance Outcomes`.`name` = b.`parent` "
           "WHERE `tabQuality Performance Outcomes`.`name` = 'Aggregated Performance Index' "
           "GROUP BY `c`.`criteria`, `b`.`band`")

    COLUMNS = {
        "Quality Performance Outcomes": {"name": "String"},
        "QPO Criteria": {"name": "String", "parent": "String", "criteria": "String",
                         "score": "Decimal"},
        "QPO Band": {"name": "String", "parent": "String", "band": "String"},
    }

    def result(self):
        return run(self.SQL, columns=self.COLUMNS)

    def test_two_joins_become_two_join_operations(self):
        result = self.result()
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual([op["type"] for op in result["operations"]],
                         ["source", "join", "join", "filter", "summarize"])

    def test_each_join_names_its_own_table_and_columns(self):
        operations = self.result()["operations"]
        self.assertEqual(operations[1]["table"]["table_name"], "tabQPO Criteria")
        self.assertEqual(operations[1]["join_condition"], {
            "left_column": {"type": "column", "column_name": "name"},
            "right_column": {"type": "column", "column_name": "parent"}})
        self.assertEqual(operations[2]["table"]["table_name"], "tabQPO Band")
        self.assertEqual(operations[2]["join_condition"], {
            "left_column": {"type": "column", "column_name": "name"},
            "right_column": {"type": "column", "column_name": "parent"}})

    def test_the_filter_on_the_parent_survives(self):
        """`table.column = 'literal'` with a fully-qualified backticked table."""
        self.assertEqual(self.result()["operations"][3], {
            "type": "filter", "column": {"type": "column", "column_name": "name"},
            "operator": "=", "value": "Aggregated Performance Index"})

    def test_grouping_by_a_column_from_each_child(self):
        dimensions = self.result()["operations"][-1]["dimensions"]
        self.assertEqual([d["column_name"] for d in dimensions], ["criteria", "band"])

    def test_a_third_join_is_no_different(self):
        columns = dict(self.COLUMNS,
                       **{"QPO Note": {"parent": "String", "note": "String"}})
        result = run(self.SQL.replace(
            " WHERE ", " LEFT JOIN `tabQPO Note` n "
            "ON `tabQuality Performance Outcomes`.`name` = n.`parent` WHERE "),
            columns=columns)
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual([op["type"] for op in result["operations"]].count("join"), 3)

    def test_a_chained_join_attaches_to_the_table_before_it(self):
        """Join 2 onto join 1's table, not onto the source. Each join's
        source_column has to be checked against the table it actually names —
        checking it against the FROM table looks in the wrong place."""
        columns = dict(self.COLUMNS,
                       **{"QPO Note": {"criteria": "String", "note": "String"}})
        result = run(
            "SELECT COUNT(*) FROM `tabQuality Performance Outcomes` "
            "LEFT JOIN `tabQPO Criteria` c "
            "  ON `tabQuality Performance Outcomes`.`name` = c.`parent` "
            "LEFT JOIN `tabQPO Note` n ON n.`criteria` = c.`criteria`",
            columns=columns)
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"][2]["join_condition"], {
            "left_column": {"type": "column", "column_name": "criteria"},
            "right_column": {"type": "column", "column_name": "criteria"}})

    def test_a_chained_joins_source_column_is_checked_against_ITS_table(self):
        """`nonsense` is not on QPO Criteria. Checked against the FROM table
        instead, this would be reported against the wrong table — or, if the
        FROM table happened to have the column, not reported at all."""
        columns = dict(self.COLUMNS,
                       **{"QPO Note": {"criteria": "String"},
                          "Quality Performance Outcomes": {"name": "String",
                                                           "nonsense": "String"}})
        result = run(
            "SELECT COUNT(*) FROM `tabQuality Performance Outcomes` "
            "LEFT JOIN `tabQPO Criteria` c "
            "  ON `tabQuality Performance Outcomes`.`name` = c.`parent` "
            "LEFT JOIN `tabQPO Note` n ON n.`criteria` = c.`nonsense`",
            columns=columns)
        self.assertFalse(result["supported"], "a column of the wrong table passed")
        self.assertIn("'nonsense', which is not a column of QPO Criteria",
                      " | ".join(result["reasons"]))

    def test_a_join_column_is_still_checked_against_its_own_table(self):
        result = run(self.SQL.replace("c.`parent`", "c.`nonsense`"),
                     columns=self.COLUMNS)
        self.assertFalse(result["supported"])
        self.assertIn("'nonsense', which is not a column of QPO Criteria",
                      " | ".join(result["reasons"]))

    def test_the_same_child_table_joined_twice_is_refused(self):
        """`columns` is keyed by DocType, so two copies cannot be told apart."""
        result = run(self.SQL.replace("`tabQPO Band` b", "`tabQPO Criteria` b"),
                     columns=self.COLUMNS)
        self.assertFalse(result["supported"])
        self.assertIn("more than once", " | ".join(result["reasons"]))


class TestACoercedTextColumn(unittest.TestCase):
    """`AVG(`col` * 1)` where `col` is TEXT.

    ADR-009 allowed this, because Metabase's `* 1` is the only reason the live
    report works. The first delivery attempt set the MEASURE's `data_type` to
    Decimal, which describes the result of the aggregate and converts nothing —
    Insights' engine reached the text column untouched and died on
    `'StringColumn' object has no attribute 'mean'`.

    The conversion is an OPERATION of its own, `{type: 'cast', column,
    data_type}`, read from `query.types.ts` at v3.12.2. These tests assert the
    emitted dict EXACTLY and assert where in the list it sits, because Insights
    drops a key it does not recognise silently: a wrong shape fails at run time
    in exactly the way the right shape was meant to prevent, while the
    operations list still reads as if it were fixed.
    """

    SQL = ("SELECT `c`.`metric` AS `m`, AVG(`c`.`actual_value` * 1) AS `avg` "
           "FROM `tabQPO` LEFT JOIN `tabQPO Child` c "
           "ON `tabQPO`.`name` = c.`parent` GROUP BY `c`.`metric`")
    # actual_value is a Data field: String, not a number.
    COLUMNS = {"QPO": {"name": "String"},
               "QPO Child": {"parent": "String", "metric": "String",
                             "actual_value": "String"}}

    def operations(self, sql=None, columns=None):
        result = run(sql or self.SQL, columns=columns or self.COLUMNS)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        return result["operations"]

    def test_a_real_cast_operation_is_emitted(self):
        """Asserted in FULL. An extra key is dropped by Insights without a
        word, so "the right keys are present" would prove nothing."""
        cast = [op for op in self.operations() if op["type"] == "cast"]
        self.assertEqual(cast, [{
            "type": "cast",
            "column": {"type": "column", "column_name": "actual_value"},
            "data_type": "Decimal",
        }])

    def test_the_cast_comes_before_the_summarize_that_reads_the_column(self):
        """Order is the whole point: a cast after the aggregate is the state
        that crashed. It sits after the filters too — `* 1` was scoped to the
        aggregate in the SQL, not to the WHERE."""
        self.assertEqual([op["type"] for op in self.operations()],
                         ["source", "join", "cast", "summarize"])

    def test_the_measure_no_longer_claims_the_conversion_by_itself(self):
        """`data_type` on a measure describes the result. It reads Decimal
        because the cast made it one — and `coerced_from` records that the
        source field is text, which is the only place that is visible."""
        measure = self.operations()[-1]["measures"][0]
        self.assertEqual(measure["data_type"], "Decimal")
        self.assertEqual(measure["coerced_from"], "String")

    def test_the_SAME_column_without_the_cast_still_refuses(self):
        """Nothing in the SQL asked for a conversion, so inventing one would
        answer a different question — text rows would average in as zero."""
        result = run(self.SQL.replace("`c`.`actual_value` * 1", "`c`.`actual_value`"),
                     columns=self.COLUMNS)
        self.assertFalse(result["supported"])
        self.assertEqual(result["operations"], [])
        self.assertIn("only a number can be AVG'd", " | ".join(result["reasons"]))

    def test_a_cast_on_a_column_that_is_already_numeric_emits_no_cast(self):
        """`x * 1` on a number is a no-op, and nothing here needs converting."""
        columns = {"QPO": {"name": "String"},
                   "QPO Child": {"parent": "String", "metric": "String",
                                 "actual_value": "Decimal"}}
        operations = self.operations(columns=columns)
        self.assertEqual([op["type"] for op in operations],
                         ["source", "join", "summarize"])
        self.assertNotIn("coerced_from", operations[-1]["measures"][0])

    def test_counting_a_coerced_text_column_emits_no_cast(self):
        """COUNT works on text. Converting first would change what is counted,
        and `cast` to Integer on a non-numeric row is a run-time failure for a
        conversion nothing needed."""
        operations = self.operations(
            self.SQL.replace("AVG(`c`.`actual_value` * 1)",
                             "COUNT(`c`.`actual_value` * 1)"))
        self.assertEqual([op["type"] for op in operations],
                         ["source", "join", "summarize"])
        self.assertNotIn("coerced_from", operations[-1]["measures"][0])

    def test_a_coerced_column_in_a_GROUP_BY_is_still_refused(self):
        """ADR-009 allowed the cast for an AGGREGATE only. Grouping by
        `col * 1` buckets by a value MySQL computes as 0 for every non-numeric
        row, silently merging them."""
        result = run(self.SQL.replace("GROUP BY `c`.`metric`",
                                      "GROUP BY `c`.`actual_value` * 1"),
                     columns=self.COLUMNS)
        self.assertFalse(result["supported"])
        self.assertEqual(result["operations"], [])
        # The `* 1` used to be read off the front and the rest dropped, so this
        # converted cleanly into a grouping by the raw column — a different
        # question, answered without a word.
        reasons = " | ".join(result["reasons"])
        self.assertIn("* 1", reasons)
        self.assertIn("not a plain column", reasons)


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

    def test_frappes_OPTIONAL_columns_are_never_assumed(self):
        """`_user_tags`, `_comments`, `_assign` and `_liked_by` are Frappe's own
        `optional_fields` and are not on every table. Assuming them produced a
        query that converted and then failed in Insights with "Column
        '_comments' is not found in table". Without a real column list, they are
        left out — this is the path taken when the schema cannot be read."""
        columns = columns_from_meta([("score", "Float")])
        for optional in ("_user_tags", "_comments", "_assign", "_liked_by", "_seen"):
            self.assertNotIn(optional, columns, f"{optional} is not on every table")

    def test_the_real_column_list_decides_in_both_directions(self):
        columns = columns_from_meta(
            [("score", "Float"), ("layout", "Section Break")],
            ["name", "parent", "score", "_comments"])
        # Present because the TABLE has it, though no DocField declares it.
        self.assertEqual(columns["_comments"], "String")
        # Typed from the DocField, not defaulted.
        self.assertEqual(columns["score"], "Decimal")
        # Absent because the table does not have them, seed or no seed.
        self.assertNotIn("idx", columns)
        self.assertNotIn("layout", columns, "a Section Break is not a column")
        self.assertEqual(set(columns), {"name", "parent", "score", "_comments"})


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
