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
    _produced_columns,
    analyze_sql,
    drop_passthrough_wrapper,
    lift_renaming_wrapper,
    unwrap_derived_tables,
)
from dashboard_studio.integrations.metabase.sql_ops import operations_from_sql

REAL = (pathlib.Path(__file__).resolve().parents[2]
        / "reference" / "metabase" / "duration_from_counselling_to_admission.sql")
# The second real capture: an AGGREGATING Metabase question, which wraps its
# joins instead of leaving them at the top level.
QPO = pathlib.Path(__file__).resolve().parent / "fixtures" / "quality_performance_outcomes.sql"
# The third: the same question compiled the other way up — the inner query is
# complete and the outer wrapper only re-selects its output columns. Reported
# 2026-08-03; the joined derived table was elided as `( ... )` in the report and
# is filled in from QPO above, which attaches the same child table under the
# same alias on the same condition.
#
# That file carries NO comment header, unlike its siblings, and deliberately:
# nothing strips SQL comments, so a comment line lands in the outer SELECT list
# and stops this rule reading it. See TestACommentIsNotStripped below.
RESELECTED = (pathlib.Path(__file__).resolve().parent / "fixtures"
              / "aggregated_then_reselected.sql")

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
        self.assertEqual(self.result["joins"], [{
            "doctype": "Student Applicant",
            "join_type": "left",
            "on": ("`tabStudent Admission UCC`.`student_applicant` = "
                   "`Student Applicant Model - Name`.`name`"),
            "source_table": "Student Admission UCC",
            "source_column": "student_applicant",
            "join_column": "name",
        }])

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


class TestMetabaseDisplayNameAliases(unittest.TestCase):
    """Metabase names its derived tables after the humanized table name, so the
    alias for `tabAssessment Result Detail` comes out as
    `TabAssessment Result Detail - Name` — capital T.

    Frappe's real tables are always lowercase `tab`. Matching that prefix
    case-insensitively made every one of these aliases read as a TABLE called
    "Assessment Result Detail - Name": a name in no alias map, and a DocType
    that does not exist.
    """

    SQL = ("SELECT COUNT(*) AS `count` FROM `tabAssessment Result` "
           "LEFT JOIN ( SELECT `__mb_source`.`parent` AS `parent` "
           "FROM ( select * from `tabAssessment Result Detail` ) AS `__mb_source` ) "
           "AS `TabAssessment Result Detail - Name` "
           "ON `tabAssessment Result`.`name` = "
           "`TabAssessment Result Detail - Name`.`parent`")

    def test_the_join_is_read_rather_than_refused(self):
        result = analyze_sql(self.SQL)
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["joins"], [{
            "doctype": "Assessment Result Detail",
            "join_type": "left",
            "on": ("`tabAssessment Result`.`name` = "
                   "`TabAssessment Result Detail - Name`.`parent`"),
            "source_table": "Assessment Result",
            "source_column": "name",
            "join_column": "parent",
        }])

    def test_the_alias_is_not_mistaken_for_a_third_table(self):
        """`_table_columns` is called for every DocType found, so an invented
        one refuses the whole conversion with "There is no DocType called…"."""
        self.assertEqual(analyze_sql(self.SQL)["doctypes"],
                         ["Assessment Result", "Assessment Result Detail"])

    def test_the_alias_resolves_in_the_group_by_too(self):
        """The ON clause, the WHERE and the GROUP BY all read a qualifier the
        same way, so the alias has to resolve in all three."""
        result = analyze_sql(
            self.SQL + " WHERE `TabAssessment Result Detail - Name`.`score` > 5"
            " GROUP BY `TabAssessment Result Detail - Name`.`criteria`")
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["group_by"],
                         [{"field": "criteria", "table": "Assessment Result Detail"}])
        self.assertEqual(result["filters"],
                         [{"field": "score", "operator": ">", "value": "5",
                           "table": "Assessment Result Detail"}])

    def test_a_lowercase_tab_prefix_is_still_a_real_table(self):
        self.assertEqual(
            analyze_sql("SELECT COUNT(*) FROM `tabAssessment Result`")["source_doctype"],
            "Assessment Result")

    def test_a_doctype_whose_own_name_starts_with_Tab_is_not_beheaded(self):
        """`tabTable Layout` -> "Table Layout". Stripping the prefix a second
        time, case-insensitively, turns it into "le Layout" — a DocType that
        does not exist, from a table that does."""
        self.assertEqual(
            analyze_sql("SELECT COUNT(*) FROM `tabTable Layout`")["source_doctype"],
            "Table Layout")


class TestLiftingARenamingWrapper(unittest.TestCase):
    """Metabase's other wrapper: the one it puts round the joins when the
    question aggregates.

    It is NOT a passthrough — it renames every column — so unwrap_ leaves it
    alone, correctly. It is still removable for a different and equally provable
    reason: it neither filters nor aggregates, so it returns the same ROWS as
    the query inside it, and a rename is a bijection on columns. Mapping the
    outer references back through its own `X AS Y` list recovers the original.
    """

    def setUp(self):
        self.sql = QPO.read_text()
        self.result = analyze_sql(self.sql)

    def test_the_real_report_converts(self):
        self.assertTrue(self.result["supported"], self.result["reasons"])

    def test_the_source_is_the_parent_doctype(self):
        self.assertEqual(self.result["source_doctype"], "Quality Performance Outcomes")

    def test_both_child_tables_are_joined_on_parent(self):
        self.assertEqual(
            [(j["doctype"], j["source_column"], j["join_column"], j["join_type"])
             for j in self.result["joins"]],
            [("Quality Performance Outcomes Performance Childtable", "name", "parent", "left"),
             ("Quality Performance Actual Value Parameter Childtable", "name", "parent", "left")])

    def test_the_filter_on_the_parent_record_survives_the_lift(self):
        self.assertEqual(self.result["filters"], [
            {"field": "name", "operator": "=", "value": "Aggregated Performance Index",
             "table": "Quality Performance Outcomes"}])

    def test_the_grouping_columns_map_back_through_the_rename(self):
        """The outer query groups by `__mb_source`.`Tab…Child_a3e4a16b`, a name
        no table has. It is the wrapper's alias for `metric`."""
        self.assertEqual(
            self.result["group_by"],
            [{"field": "metric",
              "table": "Quality Performance Actual Value Parameter Childtable"},
             {"field": "year",
              "table": "Quality Performance Actual Value Parameter Childtable"}])

    def test_the_aggregate_maps_back_through_the_rename_AND_the_times_one(self):
        """`AVG(`__mb_source`.`Observe Value`)` where the wrapper defines
        `Observe Value` as `actual_value * 1` — Metabase casting a text column
        to a number. The cast is carried through, not dropped: it is what makes
        the aggregate legal, and it is what a reader needs told (ADR-009)."""
        self.assertEqual(self.result["aggregations"],
                         [{"function": "AVG", "argument": "actual_value",
                           "table": "Quality Performance Actual Value Parameter Childtable",
                           "coerced": True}])


class TestTheRealReportEndToEnd(unittest.TestCase):
    """The whole thing, with `actual_value` typed as it really is on the site:
    a Frappe Data field, i.e. text."""

    COLUMNS = {
        "Quality Performance Outcomes": {"name": "String", "parent": "String"},
        "Quality Performance Outcomes Performance Childtable":
            {"name": "String", "parent": "String", "year": "String", "trend": "String"},
        "Quality Performance Actual Value Parameter Childtable":
            {"name": "String", "parent": "String", "year": "String",
             "metric": "String", "actual_value": "String"},
    }

    def operations(self):
        result = operations_from_sql(analyze_sql(QPO.read_text()), self.COLUMNS)
        self.assertTrue(result["supported"], result["reasons"])
        return result["operations"]

    def test_the_shape_of_the_whole_conversion(self):
        """With actual_value typed as a number, which is what it SHOULD be."""
        numeric = dict(self.COLUMNS)
        numeric["Quality Performance Actual Value Parameter Childtable"] = dict(
            numeric["Quality Performance Actual Value Parameter Childtable"],
            actual_value="Decimal")
        result = operations_from_sql(analyze_sql(QPO.read_text()), numeric)
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual([op["type"] for op in result["operations"]],
                         ["source", "join", "join", "filter", "summarize"])

    def test_a_join_carries_only_the_columns_the_report_reads(self):
        numeric = dict(self.COLUMNS)
        numeric["Quality Performance Actual Value Parameter Childtable"] = dict(
            numeric["Quality Performance Actual Value Parameter Childtable"],
            actual_value="Decimal")
        operations = operations_from_sql(analyze_sql(QPO.read_text()),
                                         numeric)["operations"]
        self.assertEqual([c["column_name"] for c in operations[1]["select_columns"]],
                         ["parent"])
        self.assertEqual([c["column_name"] for c in operations[2]["select_columns"]],
                         ["actual_value", "metric", "parent", "year"])

    def test_as_the_field_is_typed_TODAY_the_conversion_casts_it(self):
        """actual_value is a Frappe Data field, i.e. text. Insights called
        .mean() on it and died; the `* 1` Metabase wrote becomes a real `cast`
        operation, and it lands between the filter and the summarize that reads
        the column. This is the whole real report, not an approximation of it."""
        operations = self.operations()
        self.assertEqual([op["type"] for op in operations],
                         ["source", "join", "join", "filter", "cast", "summarize"])
        self.assertEqual(operations[4], {
            "type": "cast",
            "column": {"type": "column", "column_name": "actual_value"},
            "data_type": "Decimal",
        })
        measure = operations[5]["measures"][0]
        self.assertEqual(measure["column_name"], "actual_value")
        self.assertEqual(measure["aggregation"], "avg")
        self.assertEqual(measure["coerced_from"], "String")


class TestWhatIsNotLifted(unittest.TestCase):
    """Every bail-out leaves the statement exactly as it was. Nothing is
    half-rewritten.

    What happens NEXT is a separate claim, and since drop_passthrough_wrapper
    arrived it is not always "refused as a subquery": a wrapper lift declines
    may still be removable by that other rule, when the outer does nothing at
    all. The two cases where that is so say so by name below.
    """

    WRAPPED = ("SELECT `w`.`m` AS `m`, COUNT(*) AS `n` FROM ( "
               "SELECT `c`.`metric` AS `m` FROM `tabQPO` "
               "LEFT JOIN `tabQPO Child` c ON `tabQPO`.`name` = c.`parent` "
               "{extra}) AS `w` GROUP BY `w`.`m`")

    def assert_not_lifted(self, sql):
        self.assertEqual(lift_renaming_wrapper(sql)[0], sql,
                         "the statement was rewritten when it should not have been")
        result = analyze_sql(sql)
        self.assertFalse(result["supported"])
        self.assertIn("subquery", " | ".join(result["reasons"]))

    def test_the_shape_it_IS_meant_to_lift(self):
        """A guard on the guard: if this stopped lifting, every case below would
        pass for the wrong reason."""
        sql = self.WRAPPED.format(extra="")
        self.assertNotEqual(lift_renaming_wrapper(sql)[0], sql)
        self.assertTrue(analyze_sql(sql)["supported"], analyze_sql(sql)["reasons"])

    def test_a_wrapper_that_aggregates_is_not_lifted_but_IS_dropped(self):
        """There is nothing to lift — the inner already aggregates. The outer
        does nothing at all, though, so the other rule removes it and the query
        converts. This used to refuse, and refusing it was the conservative
        answer rather than the correct one."""
        sql = "SELECT `w`.`n` FROM ( SELECT COUNT(*) AS `n` FROM `tabQPO` ) AS `w`"
        self.assertEqual(lift_renaming_wrapper(sql)[0], sql)
        self.assertEqual(drop_passthrough_wrapper(sql).split(),
                         "SELECT COUNT(*) AS `n` FROM `tabQPO`".split())
        self.assertTrue(analyze_sql(sql)["supported"], analyze_sql(sql)["reasons"])

    def test_a_wrapper_that_groups_is_not_lifted(self):
        self.assert_not_lifted(self.WRAPPED.format(extra="GROUP BY `c`.`metric` "))

    def test_a_wrapper_with_a_limit_is_not_lifted(self):
        self.assert_not_lifted(self.WRAPPED.format(extra="LIMIT 10 "))

    def test_an_outer_WHERE_is_not_lifted(self):
        """It would have to be ANDed with the inner one; that is a different
        rewrite, and getting it wrong changes which rows are counted."""
        self.assert_not_lifted(self.WRAPPED.format(extra="") .replace(
            "GROUP BY `w`.`m`", "WHERE `w`.`m` = 'x' GROUP BY `w`.`m`"))

    def test_a_computed_item_in_the_wrapper_is_not_lifted(self):
        """`a - b AS x` is not a rename. Its value is not any column's.

        The outer here does nothing, so the wrapper does come off — and the
        flattened query then refuses NAMING the computed column, which is the
        better refusal of the two. What must not happen is the computed column
        being carried through in silence."""
        sql = ("SELECT `w`.`d` FROM ( SELECT `c`.`a` - `c`.`b` AS `d` FROM `tabQPO` "
               "LEFT JOIN `tabQPO Child` c ON `tabQPO`.`name` = c.`parent` ) AS `w`")
        self.assertEqual(lift_renaming_wrapper(sql)[0], sql)
        result = analyze_sql(sql)
        self.assertFalse(result["supported"])
        self.assertIn("the SELECT list computes 'd'", " | ".join(result["reasons"]))

    def test_an_outer_reference_the_wrapper_does_not_define_is_not_lifted(self):
        self.assert_not_lifted(
            "SELECT `w`.`missing` FROM ( SELECT `c`.`metric` AS `m` FROM `tabQPO` "
            "LEFT JOIN `tabQPO Child` c ON `tabQPO`.`name` = c.`parent` ) AS `w`")

    def test_grouping_by_a_times_one_alias_is_not_lifted(self):
        """Aggregating a coerced column is translated — see ADR-009 — because at
        UCC the cast is the only reason the report works. Grouping by one is
        not: every row that is not a number coerces to the same 0."""
        sql = ("SELECT `w`.`v` FROM ( SELECT `c`.`actual_value` * 1 AS `v` FROM `tabQPO` "
               "LEFT JOIN `tabQPO Child` c ON `tabQPO`.`name` = c.`parent` ) AS `w` "
               "GROUP BY `w`.`v`")
        self.assert_not_lifted(sql)
        # And it says WHY, rather than leaving a bare "subquery" to explain a
        # refusal that has nothing to do with nesting.
        reasons = " | ".join(analyze_sql(sql)["reasons"])
        self.assertIn("coerced to a number, not the column itself", reasons)
        self.assertIn("every row that is not a number coerces to the same 0", reasons)

    def test_a_wrapper_whose_joins_are_still_wrapped_is_not_lifted(self):
        """Nothing readable to lift onto: the joins are still subqueries."""
        self.assert_not_lifted(
            "SELECT `w`.`m` FROM ( SELECT `c`.`metric` AS `m` FROM `tabQPO` "
            "LEFT JOIN ( SELECT `x`.`metric` AS `metric` FROM `tabQPO Child` `x` "
            "WHERE `x`.`ok` = 1 ) AS c ON `tabQPO`.`name` = c.`parent` ) AS `w`")


class TestRefusalNoise(unittest.TestCase):
    """When a wrapper legitimately cannot be flattened, its internal aliases are
    unknown BY CONSTRUCTION. Reporting each one buries the reason that matters
    under an identifier nobody typed."""

    # A join nested inside the wrapper, so the wrapper is not a passthrough.
    SQL = ("SELECT COUNT(*) AS `count` FROM `tabAssessment Result` LEFT JOIN ( "
           "SELECT `__mb_source`.`name` AS `name` "
           "FROM ( select * from `tabAssessment Result Detail` ) AS `__mb_source` "
           "JOIN `tabStudent Applicant` ON 1 = 1 ) AS `W` "
           "ON `tabAssessment Result`.`name` = `W`.`name` "
           "WHERE `__mb_source`.`x` = 1 GROUP BY `__mb_source`.`y`")

    def test_the_internal_wrapper_alias_is_not_reported(self):
        reasons = analyze_sql(self.SQL)["reasons"]
        self.assertFalse([r for r in reasons if "__mb_source" in r],
                         f"Metabase's internal alias reached the user: {reasons}")

    def test_the_real_reason_survives(self):
        """One reason now: the wrapper contains a join, so it is not a
        passthrough. The join COUNT stopped being a reason when N joins became
        N operations — the nesting is what is left."""
        self.assertEqual([r for r in analyze_sql(self.SQL)["reasons"]
                          if "subquery" in r], analyze_sql(self.SQL)["reasons"])

    def test_the_subquery_message_says_why_it_could_not_be_removed(self):
        self.assertIn("plain projection of one table",
                      " | ".join(analyze_sql(self.SQL)["reasons"]))

    def test_one_fault_is_reported_once(self):
        """The same unknown alias in the WHERE, the GROUP BY and the aggregate
        is one thing wrong, not three."""
        reasons = analyze_sql(
            "SELECT COUNT(`z`.`a`) FROM `tabStudent Applicant` "
            "WHERE `z`.`b` = 1 GROUP BY `z`.`c`")["reasons"]
        self.assertEqual(len(reasons), len(set(reasons)), reasons)
        self.assertEqual(len([r for r in reasons if "'z'" in r]), 1, reasons)


class TestClauseBoundaries(unittest.TestCase):
    """A WHERE or GROUP BY is found by scanning forward to the next keyword,
    which runs straight past the ')' ending the subquery it lives in.

    The danger is not that it refuses — it is that it does NOT. The condition
    still matches `field <op> value`, with the wrapper's own tail swallowed into
    the value, so the filter compares against a string nothing equals.
    """

    NESTED = ("SELECT `w`.`c` FROM ( SELECT `tabQPO`.`name` AS `n` FROM `tabQPO` "
              "JOIN `tabQPO Detail` d ON d.`parent` = `tabQPO`.`name` "
              "WHERE `tabQPO`.`name` = 'Aggregated Performance Index' ) AS `w` "
              "GROUP BY `w`.`c`")

    def test_the_filter_value_is_the_literal_and_nothing_after_it(self):
        self.assertEqual(analyze_sql(self.NESTED)["filters"], [
            {"field": "name", "operator": "=",
             "value": "Aggregated Performance Index", "table": "QPO"}])

    def test_a_group_by_inside_a_wrapper_reads_only_its_own_columns(self):
        result = analyze_sql(
            "SELECT `w`.`n` FROM ( SELECT `tabQPO`.`name` AS `n` FROM `tabQPO` "
            "GROUP BY `tabQPO`.`name` ) AS `w`")
        self.assertEqual(result["group_by"],
                         [{"field": "name", "table": "QPO"}])

    def test_a_condition_wrapped_across_two_lines_still_parses(self):
        """Metabase pretty-prints its SQL, so the operator and its value often
        land on different lines. `\\s*` spans that; the clause is deliberately
        NOT joined into one line first, which would rewrite a string literal
        that legitimately contains a newline."""
        result = analyze_sql("SELECT COUNT(*) FROM `tabQPO`\n"
                             "WHERE `tabQPO`.`name` =\n"
                             "      'Aggregated Performance Index'")
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["filters"][0]["value"], "Aggregated Performance Index")


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


class TestDropPassthroughWrapper(unittest.TestCase):
    """The third rewrite: an outer wrapper that re-selects a finished query.

    Its proof is that the outer changes nothing — no clause of its own, no
    rename, no column dropped — so it returns exactly the inner query's rows and
    exactly its columns. Every test below removes one part of that proof and
    checks the wrapper survives, because a wrapper removed on a proof that does
    not hold is a query that answers something else and still runs.
    """

    # The shape, minus Metabase's verbosity: the inner is a complete query.
    INNER = ("SELECT `c`.`year` AS `y`, AVG(`c`.`value`) AS `avg` "
             "FROM `tabQPO` LEFT JOIN `tabQPO Child` c ON `tabQPO`.`name` = c.`parent` "
             "WHERE `tabQPO`.`name` = 'Index' GROUP BY `c`.`year`")
    WRAPPED = ("SELECT `w`.`y` AS `y`, `w`.`avg` AS `avg` FROM ( {inner} ) AS `w`{tail}")

    def wrap(self, inner=None, tail="", head=None):
        sql = self.WRAPPED.format(inner=inner or self.INNER, tail=tail)
        return sql if head is None else head + " FROM ( " + (inner or self.INNER) + " ) AS `w`"

    def assert_dropped(self, sql):
        self.assertEqual(drop_passthrough_wrapper(sql).split(),
                         self.INNER.split(),
                         "the wrapper was not removed, or something else was")

    def assert_kept(self, sql):
        self.assertEqual(drop_passthrough_wrapper(sql), sql,
                         "the wrapper was removed on a proof that does not hold")
        result = analyze_sql(sql)
        self.assertFalse(result["supported"], "an unprovable wrapper converted")
        self.assertIn("subquery", " | ".join(result["reasons"]))

    def test_the_shape_it_IS_meant_to_drop(self):
        """A guard on the guard: if this stopped dropping, every test below
        would pass for the wrong reason."""
        self.assert_dropped(self.wrap())
        self.assertTrue(analyze_sql(self.wrap())["supported"],
                        analyze_sql(self.wrap())["reasons"])

    def test_an_outer_WHERE_keeps_the_wrapper(self):
        """It would have to be ANDed with the inner one, over columns the
        wrapper renamed."""
        self.assert_kept(self.wrap(tail=" WHERE `w`.`avg` > 5"))

    def test_an_outer_LIMIT_keeps_the_wrapper(self):
        """Dropping it would count every row instead of that many — the fault a
        silently dropped LIMIT already was."""
        self.assert_kept(self.wrap(tail=" LIMIT 10"))

    def test_an_outer_GROUP_BY_keeps_the_wrapper(self):
        """That is a second aggregation over an aggregate."""
        self.assert_kept(self.wrap(tail=" GROUP BY `w`.`y`"))

    def test_an_outer_ORDER_BY_keeps_the_wrapper(self):
        """Ordering changes nothing about which rows come back, so this one is
        conservative rather than necessary — but the rule is "the outer does
        nothing at all", and a rule with an exception in it is not that rule.
        Metabase writes its ORDER BY inside the wrapper anyway."""
        self.assert_kept(self.wrap(tail=" ORDER BY `w`.`y` ASC"))

    def test_a_renaming_outer_keeps_the_wrapper(self):
        """`w`.`y` AS `year` is a rename. Nothing downstream reads these labels
        today, but this rule's claim is that the outer does nothing, and a
        rename is something."""
        self.assert_kept("SELECT `w`.`y` AS `year`, `w`.`avg` AS `avg` "
                         "FROM ( " + self.INNER + " ) AS `w`")

    def test_an_outer_that_drops_a_column_keeps_the_wrapper(self):
        """A narrowing projection answers a smaller question. Removing it would
        put a column back into the result, silently."""
        self.assert_kept("SELECT `w`.`avg` AS `avg` FROM ( " + self.INNER + " ) AS `w`")

    def test_an_outer_that_aggregates_is_not_this_rule(self):
        """That is lift_renaming_wrapper's shape, and the two must not overlap:
        this one leaves it alone entirely."""
        sql = ("SELECT `w`.`y` AS `y`, AVG(`w`.`v`) AS `avg` FROM ( "
               "SELECT `c`.`year` AS `y`, `c`.`value` AS `v` FROM `tabQPO` "
               "LEFT JOIN `tabQPO Child` c ON `tabQPO`.`name` = c.`parent` "
               ") AS `w` GROUP BY `w`.`y`")
        self.assertEqual(drop_passthrough_wrapper(sql), sql)
        # …and the query still converts, through the OTHER rule.
        self.assertTrue(analyze_sql(sql)["supported"], analyze_sql(sql)["reasons"])

    def test_an_item_qualified_by_something_else_keeps_the_wrapper(self):
        """A column from anywhere but the wrapper is one this rule has proved
        nothing about."""
        self.assert_kept("SELECT `w`.`y` AS `y`, `other`.`avg` AS `avg` "
                         "FROM ( " + self.INNER + " ) AS `w`")

    def test_an_inner_item_with_no_readable_name_keeps_the_wrapper(self):
        """`COUNT(*)` with no AS: what the database calls that column is not
        something to guess, so the two lists cannot be compared."""
        inner = ("SELECT `c`.`year` AS `y`, COUNT(*) FROM `tabQPO` "
                 "LEFT JOIN `tabQPO Child` c ON `tabQPO`.`name` = c.`parent` "
                 "GROUP BY `c`.`year`")
        self.assert_kept("SELECT `w`.`y` AS `y`, `w`.`n` AS `n` FROM ( "
                         + inner + " ) AS `w`")
        # Asserted on the helper directly, because today the comparison above
        # would reject this case anyway: an outer item may only be spelled
        # [A-Za-z_][\w ]*, so it can never name a column called `COUNT(*)`.
        # The contract is what matters — the helper must say "I do not know"
        # rather than invent a name — and it is what a later rule reading this
        # function, or a looser outer-item pattern, would rely on.
        self.assertIsNone(_produced_columns(inner))
        self.assertEqual(_produced_columns(self.INNER), ["y", "avg"])

    def test_a_bare_column_names_itself(self):
        """`SELECT `c`.`year`` with no AS produces a column called `year`, and
        that IS readable — so a wrapper re-selecting it drops."""
        inner = ("SELECT `c`.`year`, COUNT(*) AS `n` FROM `tabQPO` "
                 "LEFT JOIN `tabQPO Child` c ON `tabQPO`.`name` = c.`parent` "
                 "GROUP BY `c`.`year`")
        sql = "SELECT `w`.`year` AS `year`, `w`.`n` AS `n` FROM ( " + inner + " ) AS `w`"
        self.assertEqual(drop_passthrough_wrapper(sql).split(), inner.split())

    def test_an_item_without_AS_at_all_is_still_a_passthrough(self):
        """`SELECT `w`.`y`` is the same thing as `SELECT `w`.`y` AS `y``."""
        self.assert_dropped("SELECT `w`.`y`, `w`.`avg` FROM ( " + self.INNER + " ) AS `w`")

    def test_junk_is_not_rewritten(self):
        for sql in ("", "SELECT 1", "SELECT `w`.`y` FROM ( SELECT", "not sql at all"):
            self.assertEqual(drop_passthrough_wrapper(sql), sql)
        with self.assertRaises(TypeError):
            drop_passthrough_wrapper(None)


class TestTheReselectedReportEndToEnd(unittest.TestCase):
    """The real reported query, whole: an outer passthrough over an inner that
    joins, filters, groups and averages on its own."""

    COLUMNS = {
        "Quality Performance Outcomes": {"name": "String"},
        "Quality Performance Outcomes Performance Childtable":
            {"name": "String", "parent": "String", "year": "String", "value": "Decimal"},
    }

    def test_it_converts_in_full(self):
        result = operations_from_sql(analyze_sql(RESELECTED.read_text()), self.COLUMNS)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual(result["operations"], [
            {"type": "source",
             "table": {"type": "table", "data_source": "Site DB",
                       "table_name": "tabQuality Performance Outcomes"}},
            {"type": "join", "join_type": "left",
             "table": {"type": "table", "data_source": "Site DB",
                       "table_name": "tabQuality Performance Outcomes Performance Childtable"},
             "select_columns": [{"type": "column", "column_name": "parent"},
                                {"type": "column", "column_name": "value"},
                                {"type": "column", "column_name": "year"}],
             "join_condition": {"left_column": {"type": "column", "column_name": "name"},
                                "right_column": {"type": "column", "column_name": "parent"}}},
            {"type": "filter", "column": {"type": "column", "column_name": "name"},
             "operator": "=", "value": "Student Academic Performance Index (Overall)"},
            {"type": "summarize",
             "measures": [{"measure_name": "avg_of_value", "column_name": "value",
                           "data_type": "Decimal", "aggregation": "avg"}],
             "dimensions": [{"dimension_name": "year", "column_name": "year",
                             "data_type": "String"}]},
        ])

    def test_the_wrappers_alias_reaches_nothing(self):
        """`__mb_source` and the humanized `TabQuality …` alias are Metabase's
        own names. Either one arriving in an operation is a wrapper that was
        removed on paper and not in fact."""
        text = repr(operations_from_sql(analyze_sql(RESELECTED.read_text()),
                                        self.COLUMNS)["operations"])
        self.assertNotIn("__mb_source", text)
        self.assertNotIn("d700d9c7", text)
        self.assertNotIn("70767e69", text)


class TestACommentIsNotStripped(unittest.TestCase):
    """Known limitation, recorded where it will be found again.

    Nothing strips SQL comments. A comment line inside the outer SELECT list is
    read as part of an item, so a query that would otherwise convert refuses
    instead. It REFUSES — it does not convert wrongly — which is why this is
    recorded rather than fixed: Metabase's compiled SQL carries no comments, and
    the cost of being wrong here is a person seeing a puzzling refusal, not a
    chart with the wrong number in it.
    """

    def test_a_comment_makes_the_reselected_shape_refuse(self):
        commented = "-- a note somebody typed\n" + RESELECTED.read_text()
        self.assertFalse(analyze_sql(commented)["supported"])

    def test_and_the_same_query_without_it_converts(self):
        self.assertTrue(analyze_sql(RESELECTED.read_text())["supported"])


if __name__ == "__main__":
    unittest.main()
