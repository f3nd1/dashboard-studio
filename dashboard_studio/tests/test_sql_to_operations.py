"""Pasted SQL -> Insights operations.

Driven through the REAL parser rather than hand-built analysis dicts: the point
of this path is that somebody pastes SQL, so the test starts where they do.

Expected operations are asserted IN FULL rather than spot-checked. The failure
mode here is a query that runs fine and answers something else, so "the right
keys are present" proves nothing.
"""

import re
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


class TestSeveralAggregates(unittest.TestCase):
    """N aggregates are N measures in ONE summarize.

    `measures` is a list in Insights' SummarizeArgs, and the expression path
    already fills it with two, so the old "only one is translated" refusal was
    this converter's own cap from the single-metric era. It had no test at all,
    which is why it survived so long.
    """

    SQL = ("SELECT `academic_year`, COUNT(*), AVG(`fee`) FROM `tabStudent Applicant` "
           "GROUP BY `academic_year`")

    def test_two_aggregates_become_two_measures_in_one_summarize(self):
        result = run(self.SQL)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual([op["type"] for op in result["operations"]],
                         ["source", "summarize"])
        self.assertEqual(result["operations"][-1]["measures"], [
            {"measure_name": "count", "column_name": "count",
             "data_type": "Integer", "aggregation": "count"},
            {"measure_name": "avg_of_fee", "column_name": "fee",
             "data_type": "Decimal", "aggregation": "avg"},
        ])

    def test_the_grouping_is_kept_alongside_them(self):
        measures = run(self.SQL)["operations"][-1]
        self.assertEqual(measures["dimensions"], [
            {"dimension_name": "academic_year", "column_name": "academic_year",
             "data_type": "String"}])

    def test_the_same_aggregate_written_twice_is_one_measure(self):
        """A summarize defining the same measure_name twice is not a summarize."""
        result = run("SELECT COUNT(*) AS `a`, COUNT(*) AS `b` "
                     "FROM `tabStudent Applicant`")
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual(len(result["operations"][-1]["measures"]), 1)

    def test_one_bad_aggregate_still_refuses_the_whole_query(self):
        """Per-aggregate checks are not weakened by there being several: a
        partial summarize answers a different question."""
        result = run("SELECT COUNT(*), AVG(`status`) FROM `tabStudent Applicant`")
        self.assertFalse(result["supported"])
        self.assertEqual(result["operations"], [])
        self.assertIn("only a number can be AVG'd", " | ".join(result["reasons"]))

    def test_a_join_carries_the_columns_of_every_aggregate(self):
        result = run("SELECT COUNT(*), AVG(b.`amount`), SUM(a.`fee`) "
                     "FROM `tabStudent Applicant` a "
                     "JOIN `tabPurchase Order` b ON b.`ref` = a.`po`")
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual([c["column_name"] for c in result["operations"][1]["select_columns"]],
                         ["amount", "ref"])


class TestFrappesNumericFieldtypes(unittest.TestCase):
    """A field Frappe stores as a number must type as one.

    `Rating` and `Duration` were missing from the fieldtype map, so they fell
    through to String and an average over them refused as "only a number can be
    AVG'd" — over a column that is one. A rating is a fraction and a duration is
    a count of seconds; both are numeric in the database.
    """

    META = [("feedback_rating", "Rating"), ("time_taken", "Duration"),
            ("estimated_cost", "Currency"), ("notes", "Small Text")]

    def columns(self):
        return {"Training": columns_from_meta(
            self.META, valid_columns=["name", "feedback_rating", "time_taken",
                                      "estimated_cost", "notes"])}

    def test_a_rating_is_a_number(self):
        self.assertEqual(self.columns()["Training"]["feedback_rating"], "Decimal")

    def test_a_duration_is_a_number(self):
        self.assertEqual(self.columns()["Training"]["time_taken"], "Decimal")

    def test_averaging_a_rating_converts(self):
        result = run("SELECT AVG(`feedback_rating`) FROM `tabTraining`",
                     columns=self.columns())
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual(result["operations"][-1]["measures"][0],
                         {"measure_name": "avg_of_feedback_rating",
                          "column_name": "feedback_rating",
                          "data_type": "Decimal", "aggregation": "avg"})

    def test_averaging_real_text_still_refuses(self):
        """The guard on the guard: widening the map must not make every column
        averageable. `notes` is text and stays text."""
        result = run("SELECT AVG(`notes`) FROM `tabTraining`", columns=self.columns())
        self.assertFalse(result["supported"])
        self.assertIn("only a number can be AVG'd", " | ".join(result["reasons"]))


class TestArithmeticOverAggregates(unittest.TestCase):
    """`( AVG(a) + AVG(b) ) / 2` -> a summarize plus a `mutate`.

    The mutate's expression is a PLAIN TEXT math string referencing the measure
    names the summarize defines — read out of a hand-built Insights query's own
    Operations JSON at v3.12.2, not guessed. That is why it is asserted in full
    AND cross-checked against the summarize: a literal that drifted alongside
    the code would still pass, but an expression naming a measure the summarize
    does not define is a query that fails when somebody opens it.
    """

    SQL = ("SELECT ( AVG(`c`.`qn_1`) + AVG(`c`.`qn_5`) ) / 2 AS `Actual No` "
           "FROM `tabSurvey` LEFT JOIN `tabEntry` c "
           "ON `tabSurvey`.`name` = c.`parent` "
           "WHERE `tabSurvey`.`survey_name` = 'Staff Onboarding'")
    COLUMNS = {"Survey": {"name": "String", "survey_name": "String"},
               "Entry": {"name": "String", "parent": "String",
                         "qn_1": "Integer", "qn_5": "Integer"}}

    def operations(self, sql=None, columns=None):
        result = run(sql or self.SQL, columns=columns or self.COLUMNS)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        return result["operations"]

    def refusal(self, sql, columns=None):
        result = run(sql, columns=columns or self.COLUMNS)
        self.assertFalse(result["supported"], "an untranslatable expression converted")
        self.assertEqual(result["operations"], [])
        return " | ".join(result["reasons"])

    def test_the_mutate_is_emitted_in_full(self):
        """Asserted whole. An unrecognised key is dropped by Insights without a
        word, so "the right keys are present" would prove nothing."""
        self.assertEqual(self.operations()[-1], {
            "type": "mutate",
            "new_name": "Actual No",
            "data_type": "Auto",
            "expression": {"type": "expression",
                           "expression": "( avg_of_qn_1 + avg_of_qn_5 ) / 2"},
        })

    def test_it_comes_after_the_summarize_that_defines_its_names(self):
        """Order is the whole point: before the summarize those measure names
        do not exist."""
        self.assertEqual([op["type"] for op in self.operations()],
                         ["source", "join", "filter", "summarize", "mutate"])

    def test_every_name_in_the_expression_is_a_measure_the_summarize_defines(self):
        """The cross-check the literal above cannot make. A measure_name rebuilt
        in two places drifts, and the drift only shows up in Insights."""
        operations = self.operations()
        defined = {m["measure_name"] for m in operations[-2]["measures"]}
        used = set(re.findall(r"[A-Za-z_]\w*",
                              operations[-1]["expression"]["expression"]))
        self.assertTrue(used, "the expression referenced no measure at all")
        self.assertEqual(used - defined, set(),
                         f"expression names {used - defined}, summarize defines {defined}")

    def test_both_aggregates_become_measures(self):
        measures = self.operations()[-2]["measures"]
        self.assertEqual([m["measure_name"] for m in measures],
                         ["avg_of_qn_1", "avg_of_qn_5"])
        self.assertEqual([m["aggregation"] for m in measures], ["avg", "avg"])

    def test_the_same_aggregate_twice_is_one_measure_referenced_twice(self):
        operations = self.operations(
            self.SQL.replace("AVG(`c`.`qn_5`)", "AVG(`c`.`qn_1`)"))
        self.assertEqual(len(operations[-2]["measures"]), 1)
        self.assertEqual(operations[-1]["expression"]["expression"],
                         "( avg_of_qn_1 + avg_of_qn_1 ) / 2")

    def test_the_join_carries_the_columns_the_expression_reads(self):
        """The aggregates inside a computed column are held apart from the
        query's own, and a join that did not carry them would be missing
        exactly the columns the chart is built from."""
        self.assertEqual([c["column_name"] for c in self.operations()[1]["select_columns"]],
                         ["parent", "qn_1", "qn_5"])

    def test_a_percentage_of_a_count_converts(self):
        operations = self.operations(
            "SELECT SUM(`c`.`qn_1`) * 100 / COUNT(*) AS `rate` FROM `tabSurvey` "
            "LEFT JOIN `tabEntry` c ON `tabSurvey`.`name` = c.`parent`")
        self.assertEqual(operations[-1]["expression"]["expression"],
                         "sum_of_qn_1 * 100 / count")

    def test_a_text_column_inside_the_expression_still_refuses(self):
        """The type check is not skipped just because the aggregate is inside
        an expression — averaging text is the fault ADR-009 is about."""
        columns = {"Survey": {"name": "String", "survey_name": "String"},
                   "Entry": {"name": "String", "parent": "String",
                             "qn_1": "String", "qn_5": "Integer"}}
        self.assertIn("only a number can be AVG'd", self.refusal(self.SQL, columns))


class TestWhatAnExpressionRefuses(unittest.TestCase):
    """The allowlist. This builds a string Insights evaluates, so a token
    nobody has read the meaning of must not travel into it."""

    SQL = TestArithmeticOverAggregates.SQL
    COLUMNS = TestArithmeticOverAggregates.COLUMNS
    refusal = TestArithmeticOverAggregates.refusal

    def with_expression(self, expression):
        return self.SQL.replace("( AVG(`c`.`qn_1`) + AVG(`c`.`qn_5`) ) / 2", expression)

    def test_a_CAST_to_a_FLOAT_type_is_dropped_because_it_changes_nothing(self):
        """There is no cast function in Insights' expression language — 85 are
        defined in `functions.py` at v3.12.2 and none casts — and the `cast`
        OPERATION converts a named column, so an expression's result has
        nowhere to put one. Widening an already-numeric result to a float
        leaves every value alone, so the cast is removable instead."""
        result = run(self.with_expression(
            "CAST( AVG(`c`.`qn_1`) + AVG(`c`.`qn_5`) AS double ) / 2.0"),
            columns=self.COLUMNS)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        mutate = [op for op in result["operations"] if op["type"] == "mutate"][0]
        self.assertEqual(mutate["expression"]["expression"],
                         "(avg_of_qn_1 + avg_of_qn_5) / 2.0")

    def test_the_BRACKETS_the_cast_had_are_kept(self):
        """The one way this rewrite could return a different number. Dropping
        `CAST(a + b AS double) / 2` to `a + b / 2` is valid, converts without
        complaint, and is not the same arithmetic."""
        result = run(self.with_expression(
            "CAST( AVG(`c`.`qn_1`) + AVG(`c`.`qn_5`) AS double ) / 2.0"),
            columns=self.COLUMNS)
        expression = [op for op in result["operations"]
                      if op["type"] == "mutate"][0]["expression"]["expression"]
        self.assertTrue(expression.startswith("("), expression)
        self.assertNotEqual(expression, "avg_of_qn_1 + avg_of_qn_5 / 2.0")

    def test_a_CAST_to_an_INTEGER_type_still_refuses(self):
        """`CAST(5/2 AS signed)` is 2. That is not a widening, it is a
        truncation, and dropping it would round every value silently."""
        reasons = self.refusal(self.with_expression(
            "CAST( AVG(`c`.`qn_1`) + AVG(`c`.`qn_5`) AS signed ) / 2.0"))
        self.assertIn("CAST", reasons)

    def test_a_CAST_to_char_still_refuses(self):
        reasons = self.refusal(self.with_expression(
            "CAST( AVG(`c`.`qn_1`) + AVG(`c`.`qn_5`) AS char ) / 2.0"))
        self.assertIn("CAST", reasons)

    def test_a_date_part_refuses_by_name(self):
        self.assertIn("YEAR", self.refusal(self.SQL.replace(
            "( AVG(`c`.`qn_1`) + AVG(`c`.`qn_5`) ) / 2", "YEAR(AVG(`c`.`qn_1`))")))

    def test_string_concatenation_refuses_by_name(self):
        self.assertIn("CONCAT", self.refusal(self.SQL.replace(
            "( AVG(`c`.`qn_1`) + AVG(`c`.`qn_5`) ) / 2",
            "CONCAT(AVG(`c`.`qn_1`), 'x')")))

    def test_arithmetic_with_no_aggregate_refuses(self):
        """`a + b` per row is a computed column, not a measure. Translating it
        as one would answer a different question."""
        self.assertIn("no aggregate in it", self.refusal(self.SQL.replace(
            "( AVG(`c`.`qn_1`) + AVG(`c`.`qn_5`) ) / 2", "`c`.`qn_1` + `c`.`qn_5`")))

    def test_an_aggregate_inside_AND_outside_refuses(self):
        """Which of the two the chart draws would be a guess."""
        self.assertIn("two questions in one query", self.refusal(
            "SELECT ( AVG(`c`.`qn_1`) + AVG(`c`.`qn_5`) ) / 2 AS `Actual No`, "
            "COUNT(*) AS `n` FROM `tabSurvey` LEFT JOIN `tabEntry` c "
            "ON `tabSurvey`.`name` = c.`parent`"))

    def test_the_shape_it_IS_meant_to_translate(self):
        """A guard on the guard: if the allowlist stopped letting arithmetic
        through, every refusal above would pass for the wrong reason."""
        self.assertTrue(run(self.SQL, columns=self.COLUMNS)["supported"])


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

    def test_AND_and_OR_in_one_clause_is_refused(self):
        """`a AND b OR c` means `(a AND b) OR c`. Insights' filter group is one
        flat list under one operator — `FilterArgs` is a rule or an expression,
        never another group — so there is nowhere to put that precedence, and
        flattening it would read the same and select different rows."""
        self.assert_refused(
            run("SELECT COUNT(*) FROM `tabStudent Applicant` "
                "WHERE `status` = 'A' AND `academic_year` = '2024' OR `po` > 5"),
            "AND and OR in one WHERE clause")

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

    def test_grouping_by_a_number_is_ALLOWED(self):
        """This used to refuse, on a constant borrowed from the archived
        chart-building path whose own comment said it was the CHART RENDERER's
        rule for picking an x-axis. Applied to `summarize.dimensions` it was
        ours, not Insights'. Settled by evidence: query `s39rc7j648` on the live
        site stores a dimension typed Integer."""
        result = run("SELECT `fee`, COUNT(*) FROM `tabStudent Applicant` "
                     "GROUP BY `fee`")
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual(result["operations"][-1]["dimensions"], [
            {"dimension_name": "fee", "column_name": "fee", "data_type": "Decimal"}])

    def test_grouping_by_an_integer_is_allowed_too(self):
        result = run("SELECT `headcount`, COUNT(*) FROM `tabStudent Applicant` "
                     "GROUP BY `headcount`")
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual(result["operations"][-1]["dimensions"][0]["data_type"],
                         "Integer")

    def test_grouping_without_aggregating_is_refused(self):
        self.assert_refused(
            run("SELECT `status` FROM `tabStudent Applicant` GROUP BY `status`"),
            "groups without aggregating")

    def test_non_dict_input_is_a_programming_error(self):
        with self.assertRaises(TypeError):
            operations_from_sql("SELECT 1", COLUMNS)


class TestAnOrInTheWhere(unittest.TestCase):
    """`FilterGroup = { type: 'filter_group' } & { logical_operator; filters }`,
    with `LogicalOperator = 'And' | 'Or'` — read from `query.types.ts` at
    v3.12.2. Before that file was read, an OR refused because the converter
    believed Insights had AND-only conditions. It does not.
    """

    COLUMNS = {"Student Applicant": {"name": "String", "status": "String",
                                     "academic_year": "String", "po": "Decimal"}}

    def operations(self, where):
        result = run("SELECT COUNT(*) AS `n` FROM `tabStudent Applicant` WHERE " + where,
                     columns=self.COLUMNS)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        return result["operations"]

    def test_an_or_becomes_one_filter_group_in_full(self):
        operations = self.operations("`status` = 'A' OR `status` = 'B'")
        self.assertEqual(operations[1], {
            "type": "filter_group",
            "logical_operator": "Or",
            "filters": [
                {"column": {"type": "column", "column_name": "status"},
                 "operator": "=", "value": "A"},
                {"column": {"type": "column", "column_name": "status"},
                 "operator": "=", "value": "B"},
            ]})

    def test_the_group_MEMBERS_carry_no_type_key(self):
        """`Filter = { type: 'filter' } & FilterArgs` has one because it is an
        Operation. Inside a group the members are bare `FilterArgs`. An
        unrecognised key is dropped silently, so this is asserted rather than
        assumed to be harmless."""
        group = self.operations("`status` = 'A' OR `status` = 'B'")[1]
        for member in group["filters"]:
            self.assertNotIn("type", member)

    def test_the_operator_is_capitalised_the_way_the_type_spells_it(self):
        """'Or', not 'or' — the odd one out among these shapes."""
        self.assertEqual(self.operations("`status` = 'A' OR `status` = 'B'")[1]
                         ["logical_operator"], "Or")

    def test_brackets_around_the_whole_clause_are_grouping_and_are_dropped(self):
        self.assertEqual(self.operations("(`status` = 'A' OR `status` = 'B')"),
                         self.operations("`status` = 'A' OR `status` = 'B'"))

    def test_brackets_around_EACH_condition_are_dropped_too(self):
        """A separate strip from the whole-clause one, and it needs its own
        test: without it `(a) OR (b)` reaches the condition matcher with the
        brackets still on and refuses as unparsable."""
        self.assertEqual(
            self.operations("(`status` = 'A') OR (`status` = 'B')"),
            self.operations("`status` = 'A' OR `status` = 'B'"))

    def test_three_or_ed_conditions_are_one_group_of_three(self):
        group = self.operations(
            "`status` = 'A' OR `status` = 'B' OR `status` = 'C'")[1]
        self.assertEqual([m["value"] for m in group["filters"]], ["A", "B", "C"])

    def test_values_are_still_TYPED_inside_a_group(self):
        """The check that keeps a filter comparing like with like — it applies
        to a group member exactly as it does to a standalone filter."""
        group = self.operations("`po` > 5 OR `po` < 1")[1]
        self.assertEqual([m["value"] for m in group["filters"]], [5.0, 1.0])

    def test_AND_ed_conditions_stay_separate_operations(self):
        """Not a group of one operator each — Insights' own editor produces a
        row per AND-ed condition, and each row is something somebody can read
        and click."""
        operations = self.operations("`status` = 'A' AND `po` > 5")
        self.assertEqual([op["type"] for op in operations][:3],
                         ["source", "filter", "filter"])

    def test_one_condition_is_not_wrapped_in_a_group(self):
        self.assertEqual(self.operations("`status` = 'A'")[1]["type"], "filter")

    def test_a_bad_column_inside_a_group_still_refuses(self):
        result = run("SELECT COUNT(*) AS `n` FROM `tabStudent Applicant` "
                     "WHERE `status` = 'A' OR `nonsense` = 'B'", columns=self.COLUMNS)
        self.assertFalse(result["supported"])
        self.assertEqual(result["operations"], [])
        self.assertIn("nonsense", " | ".join(result["reasons"]))

    def test_an_operator_this_converter_does_not_translate_still_refuses(self):
        result = run("SELECT COUNT(*) AS `n` FROM `tabStudent Applicant` "
                     "WHERE `status` = 'A' OR `status` LIKE 'B%'", columns=self.COLUMNS)
        self.assertFalse(result["supported"])
        self.assertEqual(result["operations"], [])


class TestABracketedWhere(unittest.TestCase):
    """The reported capture from report --3460's OUTER wrapper:

        WHERE (`__mb_source`.`PH` > 0) AND (`__mb_source`.`Academic Staff Yes` > 0)

    Two plain comparisons, each in brackets, AND-ed. It produced TWO "unparsed
    WHERE condition" reasons — `_CONDITION` is anchored, so the leading `(`
    matched nothing at all. Metabase brackets every condition it compiles, so
    this shape is not unusual; it is the ordinary one.

    Fixed incidentally by ADR-019's per-condition bracket strip, which is why
    this test exists: the fix arrived while building something else, and
    nothing pinned the AND case.
    """

    COLUMNS = {"Student Applicant": {"name": "String", "status": "String",
                                     "po": "Decimal", "fees": "Decimal"}}

    def test_bracketed_AND_ed_comparisons_parse(self):
        result = run("SELECT COUNT(*) AS `n` FROM `tabStudent Applicant` "
                     "WHERE (`po` > 0)\n  AND (`fees` > 0)", columns=self.COLUMNS)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual([op["type"] for op in result["operations"]],
                         ["source", "filter", "filter", "summarize"])

    def test_a_column_name_with_spaces_in_brackets_parses(self):
        """`Academic Staff Yes` — a wrapper's computed column, spaces and all."""
        columns = {"Student Applicant": {"name": "String", "Academic Staff Yes": "Decimal"}}
        result = run("SELECT COUNT(*) AS `n` FROM `tabStudent Applicant` "
                     "WHERE (`Academic Staff Yes` > 0)", columns=columns)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual(result["operations"][1]["column"]["column_name"],
                         "Academic Staff Yes")


class TestAnUnreadableWhereSaysWhatItFound(unittest.TestCase):
    """A refusal that says only "could not be read" files every unsupported
    WHERE into one opaque group — which then reads as a parser bug worth
    chasing when most of it is ordinary unsupported SQL. Each one names the
    construct that stopped it, so `bulk_dry_run.py` can separate them.
    """

    def reason(self, where):
        result = analyze_sql("SELECT COUNT(*) AS `n` FROM `tabStudent Applicant` "
                             "WHERE " + where)
        self.assertFalse(result["supported"])
        return " | ".join(result["reasons"])

    def test_a_CASE_in_the_where_is_named(self):
        """The reported capture from report --3460's inner wrapper. Its real
        blockers are a CASE and a LIKE, and it was filed under "could not be
        read" — which is why that group looked like 48 parser bugs."""
        self.assertIn("using a CASE expression", self.reason(
            "LOWER( CASE WHEN `status` LIKE 'UCC%' THEN '2025' END ) LIKE '%2026%'"))

    def test_IS_NULL_is_named(self):
        self.assertIn("using IS NULL", self.reason("`status` IS NOT NULL"))

    def test_BETWEEN_is_named(self):
        self.assertIn("using BETWEEN", self.reason("`po` BETWEEN 1 AND 2"))

    def test_a_function_call_is_named(self):
        """A date part in a WHERE is lifted now (ADR-024), so this needs a call
        that is not — `LOWER` is not in the allowlist and never was."""
        self.assertIn("using a function call", self.reason("LOWER(`status`) = 'x'"))

    def test_something_genuinely_unrecognised_still_says_so(self):
        """The generic message survives for what it was for. A construct nobody
        listed must not be filed under the nearest name."""
        reason = self.reason("`status` ~~ 3")
        self.assertIn("unparsed WHERE condition", reason)
        self.assertNotIn("which this converter does not translate", reason)


class TestACastInsideAnAggregate(unittest.TestCase):
    """`AVG(CAST(col AS double))` — ADR-009's `col * 1` said outright.

    Metabase writes `* 1` to coerce a text column before averaging; ADR-009
    reads that as a `cast` operation. `CAST(col AS double)` states the same
    thing, and MySQL agrees on the values — both take a leading numeric prefix
    and give 0 for anything else — so this emits ADR-009's cast unchanged,
    disclosure and all.
    """

    COLUMNS = {"Quality Action": {"name": "String", "custom_proposed_date": "Date",
                                  "v": "String", "n": "Decimal"}}

    def run_it(self, sql):
        return run(sql, columns=self.COLUMNS)

    def test_it_is_a_plain_aggregate_beside_another_one(self):
        """The refusal was "two questions in one query": the CAST made it read
        as an expression-over-aggregates, which cannot sit beside a COUNT."""
        result = self.run_it("SELECT AVG(CAST(`v` AS double)) AS `avg`, "
                             "COUNT(*) AS `count` FROM `tabQuality Action`")
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        summarize = [op for op in result["operations"]
                     if op["type"] == "summarize"][0]
        self.assertEqual([m["aggregation"] for m in summarize["measures"]],
                         ["avg", "count"])

    def test_the_cast_operation_carries_ADR_009s_disclosure(self):
        """A reader has to be able to see the source column is text."""
        result = self.run_it("SELECT AVG(CAST(`v` AS double)) AS `avg` "
                             "FROM `tabQuality Action`")
        self.assertIn({"type": "cast",
                       "column": {"type": "column", "column_name": "v"},
                       "data_type": "Decimal"}, result["operations"])
        measure = [op for op in result["operations"]
                   if op["type"] == "summarize"][0]["measures"][0]
        self.assertEqual(measure["coerced_from"], "String")

    def test_a_DOUBLY_nested_call_still_refuses(self):
        """Exactly one level. `.*` here once read `SUM(a) * 100 / COUNT(*)` as a
        plain aggregate and dropped the arithmetic in silence, so the pattern
        admits one nested call and never two."""
        result = self.run_it("SELECT AVG(CAST(ABS(`v`) AS double)) AS `avg` "
                             "FROM `tabQuality Action`")
        self.assertFalse(result["supported"])
        self.assertEqual(result["operations"], [])

    def test_arithmetic_over_aggregates_is_still_NOT_a_plain_aggregate(self):
        """The fault the old pattern caused, pinned again from this side."""
        result = self.run_it("SELECT SUM(`n`) * 100 / COUNT(*) AS `pct` "
                             "FROM `tabQuality Action`")
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        # It converts as an EXPRESSION — a summarize plus a mutate — not as one
        # aggregate with its arithmetic thrown away.
        self.assertEqual([op["type"] for op in result["operations"]],
                         ["source", "summarize", "mutate"])

    def test_a_cast_to_an_INTEGER_type_inside_an_aggregate_still_refuses(self):
        """To `signed` it truncates. That is not a coercion, it is a different
        number."""
        result = self.run_it("SELECT AVG(CAST(`v` AS signed)) AS `avg` "
                             "FROM `tabQuality Action`")
        self.assertFalse(result["supported"])


class TestADatePartInAWhereAndAYearInAGroupBy(unittest.TestCase):
    """ADR-024. Two capabilities that had to ship together, because both turn
    on WHERE the lifted operation is emitted.

    `ibis_utils.py` applies operations in list order and `apply_filter` filters
    the query so far, so a filter may name a mutated column — provided the
    mutate comes first. Moving the mutates above the filters is what makes
    `WHERE YEAR(d) = 2025` translatable, and it is why ADR-009's cast had to be
    split off and left where it was.

    A `YEAR()` in a GROUP BY takes the other route entirely: it is the date
    column carrying `granularity: "year"`, which stays a Date and can be a
    chart's X axis. Only YEAR — see `_GRANULARITY_OF` for why MONTH is a
    different question rather than a different label.
    """

    COLUMNS = {"Quality Action": {"name": "String", "d": "Date", "v": "Decimal",
                                  "status": "String"}}

    def run_it(self, sql):
        return run(sql, columns=self.COLUMNS)

    def test_a_YEAR_in_a_WHERE_is_a_mutate_and_it_comes_BEFORE_the_filter(self):
        result = self.run_it("SELECT COUNT(*) AS `c` FROM `tabQuality Action` "
                             "WHERE YEAR(`d`) = 2025")
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual(result["operations"][1:3], [
            {"type": "mutate", "new_name": "year_of_d", "data_type": "Auto",
             "expression": {"type": "expression", "expression": "year(d)"}},
            {"type": "filter", "column": {"type": "column",
                                          "column_name": "year_of_d"},
             "operator": "=", "value": 2025},
        ])

    def test_a_YEAR_in_a_GROUP_BY_is_a_GRANULARITY_and_emits_no_mutate(self):
        result = self.run_it("SELECT YEAR(`d`) AS `y`, COUNT(*) AS `c` "
                             "FROM `tabQuality Action` GROUP BY YEAR(`d`)")
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual([op["type"] for op in result["operations"]],
                         ["source", "summarize"])
        self.assertEqual(result["operations"][1]["dimensions"],
                         [{"dimension_name": "d", "column_name": "d",
                           "data_type": "Date", "granularity": "year"}])

    def test_MONTH_QUARTER_and_DAY_keep_the_numeric_mutate(self):
        """`truncate("M")` is month-within-year; `MONTH()` pools every January
        across every year. Twelve rows against forty-odd — a different
        question, so these stay mutates and stay unchartable."""
        for name in ("MONTH", "QUARTER", "DAY"):
            with self.subTest(name):
                result = self.run_it(
                    f"SELECT {name}(`d`) AS `p`, COUNT(*) AS `c` "
                    f"FROM `tabQuality Action` GROUP BY {name}(`d`)")
                self.assertTrue(result["supported"], " | ".join(result["reasons"]))
                self.assertEqual([op["type"] for op in result["operations"]],
                                 ["source", "mutate", "summarize"])
                self.assertEqual(result["operations"][1]["new_name"],
                                 f"{name.lower()}_of_d")
                self.assertNotIn("granularity",
                                 result["operations"][2]["dimensions"][0])

    def test_a_granularity_on_a_column_that_is_not_a_date_refuses(self):
        """`truncate` needs a date. Grouping the raw string instead would
        convert cleanly and answer something else."""
        result = self.run_it("SELECT COUNT(*) AS `c` FROM `tabQuality Action` "
                             "GROUP BY YEAR(`status`)")
        self.assertFalse(result["supported"])
        self.assertEqual(result["operations"], [])
        self.assertIn("'status' is grouped by year but is String, not a date",
                      result["reasons"])

    def test_a_granularity_that_never_reached_a_dimension_refuses_by_name(self):
        """The parser rewrote `YEAR(`nope`)` to a bare column. If the dimension
        is then dropped for any reason, the grouping silently becomes every
        distinct date — so an unattached granularity is its own refusal."""
        result = self.run_it("SELECT COUNT(*) AS `c` FROM `tabQuality Action` "
                             "GROUP BY YEAR(`nope`)")
        self.assertFalse(result["supported"])
        self.assertTrue(any("the grouping by year on nope could not be applied"
                            in reason for reason in result["reasons"]),
                        result["reasons"])

    def test_a_YEAR_in_a_WHERE_is_NOT_turned_into_a_granularity(self):
        """A granularity is a property of a DIMENSION. A filter has none, so
        the WHERE side keeps the mutate even for the one function that would
        otherwise take the granularity route."""
        result = self.run_it("SELECT YEAR(`d`) AS `y`, COUNT(*) AS `c` "
                             "FROM `tabQuality Action` WHERE YEAR(`d`) = 2025 "
                             "GROUP BY YEAR(`d`)")
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual([op["type"] for op in result["operations"]],
                         ["source", "mutate", "filter", "summarize"])
        # The filter must name the MUTATED column. Pointed at `d` it would
        # compare a date against 2025 — supported, runnable, no rows.
        self.assertEqual(result["operations"][2],
                         {"type": "filter",
                          "column": {"type": "column", "column_name": "year_of_d"},
                          "operator": "=", "value": 2025})
        self.assertEqual(result["operations"][3]["dimensions"],
                         [{"dimension_name": "d", "column_name": "d",
                           "data_type": "Date", "granularity": "year"}])


class TestTheDialectTheParserAccepts(unittest.TestCase):
    """What an LLM wrote, and what the parser needs — diagnosed, not assumed.

    The reported refusal was blamed on the short table alias. It is not: an
    alias is fine. The cause is the UNBACKTICKED column inside the function,
    which ADR-022's inline lift cannot see, plus a second one nobody spotted —
    ordering by a SELECT-list alias rather than by a column the query produces.

    Both are fixed in the system prompt rather than here, so these pin the
    parser's side of the contract the prompt now describes.
    """

    COLUMNS = {"Sales Invoice": {"name": "String", "agent_name": "String",
                                 "sales_income": "Decimal", "posting_date": "Date"}}

    def run_it(self, select, group, order):
        return run(f"SELECT {select} FROM `tabSales Invoice` si "
                   f"GROUP BY {group} ORDER BY {order} DESC", columns=self.COLUMNS)

    def test_a_short_table_alias_is_NOT_the_problem(self):
        result = self.run_it(
            "si.`agent_name`, YEAR(si.`posting_date`) AS `y`, "
            "SUM(si.`sales_income`) AS `total`",
            "si.`agent_name`, YEAR(si.`posting_date`)", "`sum_of_sales_income`")
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))

    def test_an_UNBACKTICKED_column_inside_the_function_is(self):
        result = self.run_it(
            "si.agent_name, YEAR(si.posting_date) AS `y`, "
            "SUM(si.sales_income) AS `total`",
            "si.agent_name, YEAR(si.posting_date)", "`sum_of_sales_income`")
        self.assertFalse(result["supported"])
        self.assertIn("not a plain column", " | ".join(result["reasons"]))

    def test_ordering_by_a_SELECT_LIST_alias_is_the_second_cause(self):
        result = self.run_it(
            "si.`agent_name`, SUM(si.`sales_income`) AS `total`",
            "si.`agent_name`", "`total`")
        self.assertFalse(result["supported"])
        self.assertIn("ORDER BY 'total'", " | ".join(result["reasons"]))


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


class TestTheYearMutatePromotion(unittest.TestCase):
    """A grouped `year(col)` mutate becomes the Date dimension + granularity.

    One consolidation point on the FINAL operation list, so every spelling that
    reduces to "grouped by year(col)" — flat, wrapped, aliased, regrouped —
    lands on ADR-024's chartable shape. The guards matter more than the happy
    path: firing when anything else reads the alias breaks that reader, and a
    promotion that grabs a non-date column charts garbage.
    """

    COLUMNS = {"Quality Action": {"name": "String", "d": "Date",
                                  "v": "Decimal", "code": "Integer"}}

    def run_it(self, sql, columns=None):
        return run(sql, columns=columns or self.COLUMNS)

    def wrapped(self, inner_expr="CONCAT('', YEAR(`t`.`d`))", alias="Year"):
        return ("SELECT `__mb`.`" + alias + "` AS `" + alias + "`, "
                "AVG(`__mb`.`v`) AS `avg` FROM ( SELECT " +
                inner_expr.replace("`t`", "`tabQuality Action`") +
                " AS `" + alias + "`, `tabQuality Action`.`v` AS `v` "
                "FROM `tabQuality Action` ) AS `__mb` "
                "GROUP BY `__mb`.`" + alias + "` ORDER BY `__mb`.`" + alias + "` ASC")

    def test_the_wrapped_year_is_promoted_whole(self):
        result = self.run_it(self.wrapped())
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual([op["type"] for op in result["operations"]],
                         ["source", "summarize", "order_by"])
        self.assertEqual(
            [op for op in result["operations"] if op["type"] == "summarize"][0]
            ["dimensions"],
            [{"dimension_name": "d", "column_name": "d",
              "data_type": "Date", "granularity": "year"}])
        self.assertEqual(result["operations"][2]["column"]["column_name"], "d")

    def test_a_MONTH_mutate_is_left_exactly_alone(self):
        """Month-of-year is a different question (ADR-024); promoting it would
        silently regroup twelve pooled months into forty-odd years."""
        result = self.run_it(self.wrapped("CONCAT('', MONTH(`t`.`d`))", "Month"))
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual([op["new_name"] for op in result["operations"]
                          if op["type"] == "mutate"], ["month"])
        dim = [op for op in result["operations"]
               if op["type"] == "summarize"][0]["dimensions"][0]
        self.assertEqual(dim["data_type"], "Integer")
        self.assertNotIn("granularity", dim)

    def test_an_alias_a_FILTER_reads_is_not_promoted(self):
        """`WHERE year(d) = 2025 GROUP BY YEAR(d)` in the wrapped spelling: the
        filter names the mutate's alias, so removing the mutate would leave the
        filter reading a column that no longer exists."""
        sql = ("SELECT COUNT(*) AS `c` FROM `tabQuality Action` "
               "WHERE YEAR(`d`) = 2025 GROUP BY MONTH(`d`)")
        # The WHERE lift makes a `year_of_d` mutate the filter reads. Nothing
        # groups by it, so the promotion must not even consider it — but pin
        # the filter's survival, since that is what breaks if this regresses.
        result = self.run_it(sql)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertIn({"type": "mutate", "new_name": "year_of_d",
                       "data_type": "Auto",
                       "expression": {"type": "expression",
                                      "expression": "year(d)"}},
                      result["operations"])
        self.assertEqual(
            [op for op in result["operations"] if op["type"] == "filter"][0]
            ["column"]["column_name"], "year_of_d")

    def test_a_year_of_a_NON_DATE_column_is_not_promoted(self):
        """The upstream check already refuses year() over text; this pins the
        pass's own re-check so a text match can never out-vote the schema."""
        from dashboard_studio.integrations.metabase.sql_ops import (
            _promote_year_mutates,
        )
        operations = [
            {"type": "source", "table": {"table_name": "tabQuality Action"}},
            {"type": "mutate", "new_name": "Year", "data_type": "Auto",
             "expression": {"type": "expression", "expression": "year(code)"}},
            {"type": "summarize", "measures": [{"measure_name": "count",
                                                "column_name": "count"}],
             "dimensions": [{"dimension_name": "Year", "column_name": "Year",
                             "data_type": "Integer"}]},
        ]
        _promote_year_mutates(operations, self.COLUMNS)
        self.assertEqual([op["type"] for op in operations],
                         ["source", "mutate", "summarize"])

    def test_a_column_in_TWO_tables_is_ambiguous_and_left_alone(self):
        from dashboard_studio.integrations.metabase.sql_ops import (
            _promote_year_mutates,
        )
        operations = [
            {"type": "mutate", "new_name": "Year",
             "expression": {"type": "expression", "expression": "year(d)"}},
            {"type": "summarize", "measures": [],
             "dimensions": [{"dimension_name": "Year", "column_name": "Year",
                             "data_type": "Integer"}]},
        ]
        both = {"A": {"d": "Date"}, "B": {"d": "Date"}}
        _promote_year_mutates(operations, both)
        self.assertEqual(operations[0]["type"], "mutate")

    def test_an_alias_read_by_ANOTHER_mutate_is_left_alone(self):
        from dashboard_studio.integrations.metabase.sql_ops import (
            _promote_year_mutates,
        )
        operations = [
            {"type": "mutate", "new_name": "Year",
             "expression": {"type": "expression", "expression": "year(d)"}},
            {"type": "mutate", "new_name": "Shifted",
             "expression": {"type": "expression", "expression": "Year * 1"}},
            {"type": "summarize", "measures": [],
             "dimensions": [{"dimension_name": "Year", "column_name": "Year",
                             "data_type": "Integer"}]},
        ]
        _promote_year_mutates(operations, self.COLUMNS)
        self.assertEqual([op.get("new_name") for op in operations[:2]],
                         ["Year", "Shifted"])

    def test_the_regroup_buttons_output_takes_the_same_route(self):
        """MONTH( substituted for YEAR( by the button, in the WRAPPED spelling,
        must come out chartable — that is the whole point of the button."""
        result = self.run_it(self.wrapped("CONCAT('', MONTH(`t`.`d`))", "Month"))
        regrouped = self.run_it(self.wrapped("CONCAT('', YEAR(`t`.`d`))", "Month"))
        self.assertNotIn("granularity",
                         [op for op in result["operations"]
                          if op["type"] == "summarize"][0]["dimensions"][0])
        self.assertEqual(
            [op for op in regrouped["operations"]
             if op["type"] == "summarize"][0]["dimensions"][0]["granularity"],
            "year")
