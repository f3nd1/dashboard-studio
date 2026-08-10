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
import re
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
# The fourth: a wrapper that COMPUTES its columns — a year label and a cast —
# which the outer then groups by and averages. Reported 2026-08-05, and it also
# has no comment header, for the reason above.
YEAR_LABEL = (pathlib.Path(__file__).resolve().parent / "fixtures"
              / "year_label_then_group.sql")
# The fifth: report 1680, the original flagship blocker. Its wrapper scales a
# rating by 5, and the outer CAST over an expression is dropped as an identity
# — it converts end to end now (ADR-017).
SCALE_FACTOR = (pathlib.Path(__file__).resolve().parent / "fixtures"
                / "scale_factor_wrapper.sql")
# The sixth: a 12-branch CASE mapping MONTH() to a month label, alongside a
# year label, the month number, an ORDER BY over all three and a cast. Reported
# 2026-08-07 as the case FOR reopening the declined CASE group, and it was the
# right call — this is a deterministic lookup, not the composite index of
# ADR-014.
MONTH_LABEL = (pathlib.Path(__file__).resolve().parent / "fixtures"
               / "month_label_lookup.sql")
# The seventh: card 2076 of the sole-41 survey family, captured VERBATIM off
# the live site by wrapper_residue.py after a reconstruction converted while
# the real card refused. The difference was one invisible character — the
# alias `Exit  Qn. 7` carries a DOUBLE space.
SATISFACTION = (pathlib.Path(__file__).resolve().parent / "fixtures"
                / "employee_satisfaction_2076.sql")

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


class TestOnlyWhereATableBelongs(unittest.TestCase):
    """A derived table may be swapped for its table only after FROM or JOIN.

    "This subquery returns exactly the rows of `tabX`" is a fact about a ROW
    SOURCE. Parentheses elsewhere mean something else, and the swap produced
    SQL that looked fine and answered a different question — the fault this
    project exists to refuse rather than ship.
    """

    SCALAR = ("SELECT COUNT(*) AS `n` FROM `tabQPO` "
              "WHERE `tabQPO`.`name` = ( SELECT `name` FROM `tabQPO Child` )")

    def test_a_scalar_subquery_in_a_WHERE_is_not_a_table(self):
        """The one that made this a bug rather than an oddity: this converted
        CLEANLY into a filter comparing `name` against the literal text
        "`tabQPO Child`", so the report returned no rows and said nothing."""
        self.assertEqual(unwrap_derived_tables(self.SCALAR), self.SCALAR)
        result = analyze_sql(self.SCALAR)
        self.assertFalse(result["supported"], "a query that returns no rows converted")
        self.assertIn("subquery", " | ".join(result["reasons"]))

    def test_the_filter_never_reaches_the_operations(self):
        """Asserted separately from the refusal: what mattered was not that a
        reason was missing, it was that a filter carrying a table name as its
        VALUE was written into a query somebody would then open."""
        columns = {"QPO": {"name": "String"}, "QPO Child": {"name": "String"}}
        result = operations_from_sql(analyze_sql(self.SCALAR), columns)
        self.assertEqual(result["operations"], [])

    def test_an_IN_subquery_is_not_a_table_either(self):
        sql = ("SELECT COUNT(*) AS `n` FROM `tabQPO` "
               "WHERE `tabQPO`.`name` IN ( SELECT `parent` FROM `tabQPO Child` )")
        self.assertEqual(unwrap_derived_tables(sql), sql)
        self.assertFalse(analyze_sql(sql)["supported"])

    def test_a_subquery_in_the_SELECT_list_is_not_a_table(self):
        sql = ("SELECT ( SELECT `name` FROM `tabQPO Child` ) AS `first`, COUNT(*) AS `n` "
               "FROM `tabQPO`")
        self.assertEqual(unwrap_derived_tables(sql), sql)
        self.assertFalse(analyze_sql(sql)["supported"])

    def test_after_FROM_and_after_JOIN_it_still_flattens(self):
        """A guard on the guard: if the position check were too strict, every
        test above would pass while the rule did nothing at all."""
        self.assertEqual(
            unwrap_derived_tables("FROM ( select * from `tabStudent Applicant` ) AS `w`"),
            "FROM `tabStudent Applicant` AS `w`")
        self.assertEqual(
            unwrap_derived_tables("LEFT JOIN ( select * from `tabPurchase Order` ) AS `p`"),
            "LEFT JOIN `tabPurchase Order` AS `p`")


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
                         ["source", "join", "join", "filter", "summarize",
                          "order_by", "order_by"])

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
                         ["source", "join", "join", "filter", "cast", "summarize",
                          "order_by", "order_by"])
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
    """A row limit was read and then silently ignored, so "top 10" converted
    into "all of them" — a different number, with no error. It then refused by
    name for want of anywhere to put it, and now it is translated: `Limit =
    { type: 'limit'; limit: number }`, from `query.types.ts` at v3.12.2."""

    def test_a_real_limit_is_carried_across(self):
        result = analyze_sql("SELECT `status`, COUNT(*) FROM `tabStudent Applicant` "
                             "GROUP BY `status` LIMIT 10")
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["limit"], 10)

    def test_two_different_limits_in_one_statement_refuse(self):
        """Which one bounds the result depends on where each sits, and that is
        not read here — so it is not guessed at either."""
        result = analyze_sql("SELECT `status`, COUNT(*) FROM `tabStudent Applicant` "
                             "GROUP BY `status` LIMIT 10 LIMIT 20")
        self.assertFalse(result["supported"])
        self.assertIn("different LIMITs", " | ".join(result["reasons"]))

    def test_metabases_export_cap_is_not_a_row_limit(self):
        result = analyze_sql("SELECT COUNT(*) FROM `tabStudent Applicant` LIMIT 1048575")
        self.assertTrue(result["supported"], result["reasons"])


class TestOrderByAndLimitAreTranslated(unittest.TestCase):
    """Both were dropped or refused for want of somewhere to put them.

    `query.types.ts` at v3.12.2 has both: `OrderBy = { type: 'order_by' } &
    { column: Column; direction: 'asc' | 'desc' }` and `Limit = { type:
    'limit'; limit: number }`. The ORDER BY had been discarded in silence,
    which cost a chart its reading order, and the LIMIT refused, which blocked
    every "top N" report.

    They go together: the argument for dropping the ORDER BY safely was that a
    real LIMIT refused, so ordering could not decide which rows came back. The
    moment LIMIT is translated that argument is gone — which is why translating
    one without the other would have been the wrong half to ship.
    """

    SQL = ("SELECT `w`.`Year` AS `Year`, COUNT(*) AS `n` FROM ( "
           "SELECT `tabQuality Action`.`name` AS `name`, "
           "`tabQuality Action`.`custom_proposed_date` AS `Year` "
           "FROM `tabQuality Action` ) AS `w` GROUP BY `w`.`Year`")
    COLUMNS = {"Quality Action": {"name": "String", "custom_proposed_date": "Date"}}

    def operations(self, sql):
        result = operations_from_sql(analyze_sql(sql), self.COLUMNS)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        return result["operations"]

    def test_an_order_by_becomes_an_order_by_operation(self):
        operations = self.operations(self.SQL + " ORDER BY `w`.`Year` DESC")
        # `custom_proposed_date`, not `Year`: the wrapper renamed the column and
        # `lift_renaming_wrapper` folds that rename away, rewriting the ORDER BY
        # along with the GROUP BY. Ordering has to name the column that survives.
        self.assertEqual(operations[-1], {
            "type": "order_by",
            "column": {"type": "column", "column_name": "custom_proposed_date"},
            "direction": "desc"})

    def test_no_direction_written_means_ascending(self):
        """SQL's default, and Insights has no third state to carry "unstated"
        into — `direction` is 'asc' | 'desc'."""
        operations = self.operations(self.SQL + " ORDER BY `w`.`Year`")
        self.assertEqual(operations[-1]["direction"], "asc")

    def test_several_ordering_columns_keep_their_order(self):
        operations = self.operations(
            self.SQL + " ORDER BY `w`.`Year` DESC, `count` ASC")
        self.assertEqual([(op["column"]["column_name"], op["direction"])
                          for op in operations if op["type"] == "order_by"],
                         [("custom_proposed_date", "desc"), ("count", "asc")])

    def test_the_ordering_comes_after_the_summarize_that_defines_the_column(self):
        operations = self.operations(self.SQL + " ORDER BY `w`.`Year` DESC")
        kinds = [op["type"] for op in operations]
        self.assertLess(kinds.index("summarize"), kinds.index("order_by"))

    def test_ordering_by_a_column_the_query_does_not_PRODUCE_refuses(self):
        """After a summarize the result is its dimensions and measures and
        nothing else. Ordering by a source column that is gone by then is a
        query that fails the moment somebody opens it — the same fault as a
        join carrying a column it dropped."""
        result = operations_from_sql(
            analyze_sql(self.SQL + " ORDER BY `w`.`name` ASC"), self.COLUMNS)
        self.assertFalse(result["supported"])
        self.assertEqual(result["operations"], [])
        self.assertIn("ORDER BY 'name'", " | ".join(result["reasons"]))

    def test_ordering_by_an_expression_refuses(self):
        result = analyze_sql(self.SQL + " ORDER BY COUNT(*) DESC")
        self.assertFalse(result["supported"])
        self.assertIn("not a plain column", " | ".join(result["reasons"]))

    def test_a_row_limit_becomes_a_limit_operation(self):
        operations = self.operations(self.SQL + " LIMIT 10")
        self.assertEqual(operations[-1], {"type": "limit", "limit": 10})

    def test_the_limit_comes_after_the_ordering_that_decides_which_rows(self):
        """Order then cut. The other way round is a different ten rows."""
        kinds = [op["type"] for op
                 in self.operations(self.SQL + " ORDER BY `w`.`Year` DESC LIMIT 10")]
        self.assertLess(kinds.index("order_by"), kinds.index("limit"))

    def test_metabases_own_export_cap_is_still_not_translated(self):
        """Nobody asked for it and it is not part of the question. Putting it on
        every converted query would be noise that reads as a decision."""
        operations = self.operations(self.SQL + " LIMIT 1048575")
        self.assertNotIn("limit", [op["type"] for op in operations])

    def test_the_real_captures_carry_an_ordering_and_still_convert(self):
        self.assertIn("ORDER BY", YEAR_LABEL.read_text().upper())
        self.assertTrue(analyze_sql(YEAR_LABEL.read_text())["supported"])


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
            {"type": "order_by", "column": {"type": "column", "column_name": "year"},
             "direction": "asc"},
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


class TestAComputedWrapperBecomesOperations(unittest.TestCase):
    """The date/label family, end to end over the reported capture.

    Its wrapper computes rather than renames, so no rule could touch it until
    three facts were read off the live site: the expression language has
    functions (`year`, lowercase), a `mutate` may precede a `summarize` (query
    `s39rc7j648` stores `source -> mutate -> summarize`), and Insights accepts a
    numeric grouping (that same query's dimension is typed Integer).
    """

    COLUMNS = {"Quality Action": {
        "name": "String", "custom_proposed_date": "Date",
        "custom_aggregated_performance_index_api": "String"}}

    def operations(self):
        result = operations_from_sql(analyze_sql(YEAR_LABEL.read_text()), self.COLUMNS)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        return result["operations"]

    def test_it_converts_in_full(self):
        self.assertEqual(self.operations(), [
            {"type": "source",
             "table": {"type": "table", "data_source": "Site DB",
                       "table_name": "tabQuality Action"}},
            {"type": "cast",
             "column": {"type": "column",
                        "column_name": "custom_aggregated_performance_index_api"},
             "data_type": "Decimal"},
            # No mutate at all: the grouped `year(d)` mutate is PROMOTED to the
            # date column carrying a granularity, exactly the shape a flat
            # `GROUP BY YEAR(d)` produces. One consolidation point, so every
            # spelling that reduces to "grouped by year(col)" lands here — and
            # the dimension stays a Date, so it can be a chart's X axis.
            {"type": "summarize",
             "measures": [{"measure_name":
                           "avg_of_custom_aggregated_performance_index_api",
                           "column_name":
                           "custom_aggregated_performance_index_api",
                           "data_type": "Decimal", "aggregation": "avg"}],
             "dimensions": [{"dimension_name": "custom_proposed_date",
                             "column_name": "custom_proposed_date",
                             "data_type": "Date", "granularity": "year"}]},
            # The ORDER BY followed the promotion: ordering by the date orders
            # by the year exactly, which is the same equivalence that makes the
            # promotion itself safe.
            {"type": "order_by",
             "column": {"type": "column", "column_name": "custom_proposed_date"},
             "direction": "asc"},
        ])

    def test_the_wrapped_year_ends_up_IDENTICAL_to_the_flat_shape(self):
        """The consolidation claim, asserted directly: `CONCAT('', YEAR(d))`
        through a wrapper and a bare `GROUP BY YEAR(d)` must produce the same
        dimension, or the chart works for one spelling of the question and not
        the other."""
        flat = operations_from_sql(analyze_sql(
            "SELECT YEAR(`custom_proposed_date`) AS `Year`, "
            "AVG(`custom_aggregated_performance_index_api` * 1) AS `avg` "
            "FROM `tabQuality Action` GROUP BY YEAR(`custom_proposed_date`)"),
            self.COLUMNS)
        self.assertTrue(flat["supported"], " | ".join(flat["reasons"]))
        wrapped_dim = [op for op in self.operations()
                       if op["type"] == "summarize"][0]["dimensions"][0]
        flat_dim = [op for op in flat["operations"]
                    if op["type"] == "summarize"][0]["dimensions"][0]
        self.assertEqual(wrapped_dim, flat_dim)
        self.assertEqual(wrapped_dim["granularity"], "year")

    def test_the_CONCAT_wrapper_is_dropped_and_the_year_stays_a_date(self):
        """Metabase writes `CONCAT('', YEAR(d))` to make the year a text label
        so the chart axis is categorical. Insights charts a Date-with-
        granularity dimension natively, so both wrappers go — the CONCAT and
        the year() itself — and the values are the same years."""
        operations = self.operations()
        self.assertEqual([op for op in operations if op["type"] == "mutate"], [])
        self.assertNotIn("concat", repr(operations).lower())

    def test_the_wrappers_alias_reaches_nothing(self):
        text = repr(self.operations())
        self.assertNotIn("__mb_source", text)

    def test_a_date_part_Insights_does_not_have_refuses_by_name(self):
        """`year`, `month`, `quarter` and `day` are in the allowlist because
        `functions.py` at v3.12.2 defines each as the same one-argument
        extractor MySQL has. WEEK is not: MySQL's takes a mode argument that
        decides which day starts a week, and `week_of_year` takes none."""
        result = analyze_sql(YEAR_LABEL.read_text().replace("YEAR(", "WEEK("))
        self.assertFalse(result["supported"])
        self.assertIn("WEEK", " | ".join(result["reasons"]))

    def test_MONTH_QUARTER_and_DAY_all_translate(self):
        for sql_name, insights_name in [("MONTH", "month"), ("QUARTER", "quarter"),
                                        ("DAY", "day"), ("DAYOFMONTH", "day")]:
            with self.subTest(sql_name):
                result = operations_from_sql(
                    analyze_sql(YEAR_LABEL.read_text().replace("YEAR(", sql_name + "(")),
                    self.COLUMNS)
                self.assertTrue(result["supported"], " | ".join(result["reasons"]))
                mutate = [op for op in result["operations"]
                          if op["type"] == "mutate"][0]
                self.assertEqual(mutate["expression"]["expression"],
                                 f"{insights_name}(custom_proposed_date)")

    def test_DAYOFWEEK_refuses_because_Insights_NUMBERS_IT_DIFFERENTLY(self):
        """The one that would have been wrong quietly. Insights has a function
        called `day_of_week`, so the obvious translation looks available — but
        it returns ibis's `day_of_week.index()`, which counts 0 = Monday, and
        MySQL's DAYOFWEEK counts 1 = Sunday. Every row off by a day and a half,
        nothing failing."""
        result = analyze_sql(YEAR_LABEL.read_text().replace("YEAR(", "DAYOFWEEK("))
        self.assertFalse(result["supported"])
        reasons = " | ".join(result["reasons"])
        self.assertIn("DAYOFWEEK", reasons)
        self.assertIn("0 = Monday", reasons)

    def test_a_CONCAT_that_actually_concatenates_refuses(self):
        """`CONCAT('', x)` is Metabase making a value into text and is dropped.
        `CONCAT('FY', x)` builds a different label — "FY2024", not 2024 — and
        dropping that prefix would relabel every row silently."""
        result = analyze_sql(YEAR_LABEL.read_text().replace("CONCAT('',", "CONCAT('FY',"))
        self.assertFalse(result["supported"], "a prefix was dropped from every label")
        self.assertIn("CONCAT", " | ".join(result["reasons"]))

    def test_a_join_carries_the_column_the_computation_READS(self):
        """Not the name it produces: `Year` is created by the mutate and is a
        column of no table, while `custom_proposed_date` has to come across the
        join or the mutate has nothing to read."""
        sql = ("SELECT `w`.`Year` AS `Year`, AVG(`w`.`v`) AS `avg` FROM ( "
               "SELECT CONCAT('', YEAR(`c`.`d`)) AS `Year`, `c`.`v` AS `v` "
               "FROM `tabParent` LEFT JOIN `tabChild` c "
               "ON `tabParent`.`name` = c.`parent` ) AS `w` GROUP BY `w`.`Year`")
        columns = {"Parent": {"name": "String"},
                   "Child": {"name": "String", "parent": "String", "d": "Date",
                             "v": "Decimal"}}
        result = operations_from_sql(analyze_sql(sql), columns)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        carried = [c["column_name"] for c in result["operations"][1]["select_columns"]]
        self.assertIn("d", carried)
        self.assertNotIn("Year", carried)

    def test_a_CAST_that_also_renames_refuses(self):
        """`cast` converts a column in place — CastArgs is {column, data_type},
        with nowhere to put a new name."""
        result = analyze_sql(YEAR_LABEL.read_text().replace(
            "AS double) AS `custom_aggregated_performance_index_api`",
            "AS double) AS `renamed`"))
        self.assertFalse(result["supported"])
        self.assertIn("renaming", " | ".join(result["reasons"]))


class TestAScaleFactorWrapper(unittest.TestCase):
    """`rating * 5` — Metabase putting a 1-5 answer on a 0-100 scale.

    It needed NO new evidence: arithmetic in a mutate expression is what the
    first captured expression was, and mutate-before-summarize was settled by
    ADR-012. It is not the `* 1` of ADR-009 — `* 1` leaves every value alone,
    `* 5` changes them, so it is a computation rather than a cast.
    """

    SQL = ("SELECT `w`.`Q1` AS `Q1`, AVG(`w`.`Q1`) AS `avg` FROM ( "
           "SELECT `c`.`rating_1` * 5 AS `Q1` FROM `tabSurvey` "
           "LEFT JOIN `tabResponse` c ON `tabSurvey`.`name` = c.`parent` ) AS `w` "
           "GROUP BY `w`.`Q1`")
    COLUMNS = {"Survey": {"name": "String"},
               "Response": {"name": "String", "parent": "String",
                            "rating_1": "Integer"}}

    def operations(self, columns=None):
        result = operations_from_sql(analyze_sql(self.SQL), columns or self.COLUMNS)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        return result["operations"]

    def test_the_scale_factor_becomes_a_mutate_before_the_summarize(self):
        operations = self.operations()
        self.assertEqual([op["type"] for op in operations],
                         ["source", "join", "mutate", "summarize"])
        # `Q1` becomes `q1`: computed aliases are slugged with Insights' own
        # sanitize_name, which lowercases — the name Insights itself would
        # create on open, so the stored JSON and the engine now agree exactly.
        self.assertEqual(operations[2], {
            "type": "mutate", "new_name": "q1", "data_type": "Auto",
            "expression": {"type": "expression", "expression": "rating_1 * 5"}})

    def test_it_is_typed_from_the_column_it_reads(self):
        summarize = self.operations()[-1]
        self.assertEqual(summarize["measures"][0]["data_type"], "Decimal")
        self.assertEqual(summarize["dimensions"][0]["data_type"], "Decimal")

    def test_scaling_a_TEXT_column_refuses(self):
        """`'abc' * 5` is 0 in MySQL. Scaling text is a coercion nobody asked
        for — ADR-009's rule, and the reason `* 1` is allowed only as an
        explicit cast for an aggregate."""
        columns = {"Survey": {"name": "String"},
                   "Response": {"name": "String", "parent": "String",
                                "rating_1": "String"}}
        result = operations_from_sql(analyze_sql(self.SQL), columns)
        self.assertFalse(result["supported"])
        self.assertEqual(result["operations"], [])
        self.assertIn("coerces every value that is not a number to 0",
                      " | ".join(result["reasons"]))

    def test_the_join_carries_the_column_the_scale_reads(self):
        carried = [c["column_name"] for c in self.operations()[1]["select_columns"]]
        self.assertIn("rating_1", carried)
        self.assertNotIn("q1", carried)

    def test_two_columns_multiplied_together_refuses(self):
        """One column with numeric literals is the observed shape. `a * b` is
        expressible in the dialect but has not been seen, and typing it is a
        second question."""
        result = analyze_sql(self.SQL.replace("* 5", "* `c`.`rating_2`"))
        self.assertFalse(result["supported"])
        self.assertIn("rating_2", " | ".join(result["reasons"]))

    def test_the_real_capture_converts_in_full_at_last(self):
        """Report 1680, the original flagship, end to end. Its `* 5` wrapper
        lifted from ADR-013; the last blocker was the outer
        `CAST( AVG(a) + AVG(b) AS double ) / 2.0`, which is dropped now that
        `functions.py` shows there is no cast to translate it into and that
        widening a number to a float changes nothing."""
        columns = {"Survey Tracking": {"name": "String", "survey_name": "String"},
                   "Survey Tracking List of Surveys Childtable": {
                       "name": "String", "parent": "String", "survey_entry": "String"},
                   "Staff Onboarding Survey": {"name": "String", "qn_1": "Integer",
                                               "qn_5": "Integer"}}
        result = operations_from_sql(analyze_sql(SCALE_FACTOR.read_text()), columns)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        # The two scale-factor mutates now sit ABOVE the filter, so a filter
        # could name one. The expression mutate still follows the summarize
        # that defines the measure names it reads.
        self.assertEqual([op["type"] for op in result["operations"]],
                         ["source", "join", "join", "mutate", "mutate", "filter",
                          "summarize", "mutate"])
        self.assertEqual(result["operations"][-1]["expression"]["expression"],
                         "(avg_of_q1 + avg_of_q5) / 2.0")


class TestADateDifferenceWrapper(unittest.TestCase):
    """`DATEDIFF(a, b)` — "how many days did this take", the duration family.

    The SHAPE is ADR-012's and needed nothing new. What it needed was the
    function's spelling, and that is three facts rather than one: a name, an
    argument order and a unit. All three came off two stored expressions on the
    live site, `date_diff(modified, creation, 'day')` — `modified` is always the
    later date and the values came back positive, so MySQL's `DATEDIFF(a, b) =
    a - b` carries across argument-for-argument.
    """

    SQL = ("SELECT `w`.`Days` AS `Days`, AVG(`w`.`Days`) AS `avg` FROM ( "
           "SELECT DATEDIFF(`c`.`completed_on`, `c`.`raised_on`) AS `Days` "
           "FROM `tabJob Requisition` "
           "LEFT JOIN `tabRequisition Stage` c "
           "ON `tabJob Requisition`.`name` = c.`parent` ) AS `w` "
           "GROUP BY `w`.`Days`")
    COLUMNS = {"Job Requisition": {"name": "String"},
               "Requisition Stage": {"name": "String", "parent": "String",
                                     "completed_on": "Date",
                                     "raised_on": "Date"}}

    def operations(self, columns=None):
        result = operations_from_sql(analyze_sql(self.SQL), columns or self.COLUMNS)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        return result["operations"]

    def test_the_difference_becomes_a_mutate_before_the_summarize(self):
        operations = self.operations()
        self.assertEqual([op["type"] for op in operations],
                         ["source", "join", "mutate", "summarize"])
        self.assertEqual(operations[2], {
            "type": "mutate", "new_name": "days", "data_type": "Auto",
            "expression": {"type": "expression",
                           "expression": "date_diff(completed_on, raised_on, 'day')"}})

    def test_the_arguments_keep_the_order_they_were_written_in(self):
        """The whole risk in this translation. `DATEDIFF(end, start)` is
        `end - start`; swapping them negates every value, and "days to
        complete: -14" is exactly the silently-wrong number this refuses on
        everywhere else."""
        expression = self.operations()[2]["expression"]["expression"]
        self.assertLess(expression.index("completed_on"), expression.index("raised_on"))

    def test_the_join_carries_BOTH_columns_the_difference_reads(self):
        """The regression this exists for. A computed entry used to name one
        source column, so the join brought `completed_on` across and dropped
        `raised_on` — a query that converted cleanly and would have failed the
        moment somebody opened it."""
        carried = [c["column_name"] for c in self.operations()[1]["select_columns"]]
        self.assertIn("completed_on", carried)
        self.assertIn("raised_on", carried)
        self.assertNotIn("Days", carried)

    def test_a_count_of_days_is_an_integer(self):
        summarize = self.operations()[-1]
        self.assertEqual(summarize["measures"][0]["data_type"], "Integer")
        self.assertEqual(summarize["dimensions"][0]["data_type"], "Integer")

    def test_a_difference_between_things_that_are_not_dates_refuses(self):
        """`date_diff` returns a count of days, which is only true of dates.
        Between two strings it is whatever the engine makes of them."""
        columns = {"Job Requisition": {"name": "String"},
                   "Requisition Stage": {"name": "String", "parent": "String",
                                         "completed_on": "Date",
                                         "raised_on": "String"}}
        result = operations_from_sql(analyze_sql(self.SQL), columns)
        self.assertFalse(result["supported"])
        self.assertEqual(result["operations"], [])
        reasons = " | ".join(result["reasons"])
        self.assertIn("raised_on", reasons)
        self.assertNotIn("completed_on", reasons)

    def test_the_SECOND_column_is_checked_as_well_as_the_first(self):
        """Same class of fault as the dropped join column: a check that reads
        only `columns[0]` passes everything about the second."""
        columns = {"Job Requisition": {"name": "String"},
                   "Requisition Stage": {"name": "String", "parent": "String",
                                         "completed_on": "String",
                                         "raised_on": "Date"}}
        result = operations_from_sql(analyze_sql(self.SQL), columns)
        self.assertFalse(result["supported"])
        self.assertIn("completed_on", " | ".join(result["reasons"]))

    def test_TIMESTAMPDIFF_refuses_by_name(self):
        """It puts the unit FIRST and subtracts the other way round, so
        translating it as a `date_diff` of its two columns would negate every
        value. It has been seen in no capture either — the vocabulary widens
        only to what has been observed."""
        result = analyze_sql(self.SQL.replace(
            "DATEDIFF(`c`.`completed_on`", "TIMESTAMPDIFF(DAY, `c`.`completed_on`"))
        self.assertFalse(result["supported"])
        self.assertIn("TIMESTAMPDIFF", " | ".join(result["reasons"]))

    def test_a_DATEDIFF_with_a_unit_argument_refuses(self):
        """Three arguments is somebody else's dialect, not MySQL's. Reading the
        first two and dropping the third would answer in days whatever unit was
        asked for."""
        result = analyze_sql(self.SQL.replace(
            "`c`.`raised_on`)", "`c`.`raised_on`, 'month')"))
        self.assertFalse(result["supported"])
        self.assertIn("3 arguments", " | ".join(result["reasons"]))

    def test_a_refused_computation_is_reported_ONCE(self):
        """A refused computation used to leave its alias undefined, so the
        grouping and the aggregate that read it each added "'Days' is not a
        column of Job Requisition or Requisition Stage" — one fault told three
        times, and two of them point at the join rather than at the
        computation."""
        columns = {"Job Requisition": {"name": "String"},
                   "Requisition Stage": {"name": "String", "parent": "String",
                                         "completed_on": "Date",
                                         "raised_on": "String"}}
        reasons = operations_from_sql(analyze_sql(self.SQL), columns)["reasons"]
        self.assertEqual(len(reasons), 1, reasons)
        self.assertNotIn("'Days' is not a column", reasons[0])

    def test_a_difference_from_a_literal_refuses(self):
        result = analyze_sql(self.SQL.replace("`c`.`raised_on`", "'2024-01-01'"))
        self.assertFalse(result["supported"])
        self.assertIn("not a column", " | ".join(result["reasons"]))


class TestACaseThatMapsValuesToLabels(unittest.TestCase):
    """The reopened CASE group, end to end over the reported capture.

    `case(condition, value, *args)` takes its pairs FLAT with an optional
    trailing else, and its body is `ibis.cases(*branches)` — no `else_` when the
    count is even, which is NULL, exactly as a SQL CASE with no ELSE returns
    NULL. Read from `functions.py` at v3.12.2, along with the comparison
    spelling: `status == 'Active'`, Python's `==` rather than SQL's `=`.

    This is NOT a reversal of ADR-014. That decision rested on a hand-rolled
    pivot and seven other gaps, not on the conditional being unavailable — a
    composite-index survey report still refuses, and should.
    """

    COLUMNS = {"Quality Action": {
        "name": "String", "custom_proposed_date": "Date",
        "custom_aggregated_performance_index_api": "String"}}

    def operations(self, sql=None):
        result = operations_from_sql(
            analyze_sql(sql or MONTH_LABEL.read_text()), self.COLUMNS)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        return result["operations"]

    def labelling(self, operations=None):
        # `Month Label` becomes `month_label`: computed aliases are slugged
        # with Insights' own sanitize_name, the name the engine creates anyway.
        return [op for op in (operations or self.operations())
                if op.get("new_name") == "month_label"][0]

    def test_the_reported_capture_converts_in_full(self):
        """Two mutates now, not three: the `year(d)` one is promoted into the
        dimension's granularity. The MONTH pair stays — month-of-year is a
        different question and keeps its numeric mutate on purpose."""
        self.assertEqual([op["type"] for op in self.operations()],
                         ["source", "mutate", "mutate", "cast",
                          "summarize", "order_by", "order_by", "order_by"])

    def test_the_twelve_branches_all_survive_in_order(self):
        expression = self.labelling()["expression"]["expression"]
        self.assertEqual(
            re.findall(r"month\(custom_proposed_date\) == (\d+), '([^']+)'", expression),
            [("1", "01-Jan"), ("2", "02-Feb"), ("3", "03-Mar"), ("4", "04-Apr"),
             ("5", "05-May"), ("6", "06-Jun"), ("7", "07-Jul"), ("8", "08-Aug"),
             ("9", "09-Sep"), ("10", "10-Oct"), ("11", "11-Nov"), ("12", "12-Dec")])

    def test_the_pairs_are_FLAT_not_tuples(self):
        """`case` takes them flat; `cases` is the one that takes tuples. Writing
        one shape into the other's name is a call that fails or, worse, reads a
        condition as a value."""
        expression = self.labelling()["expression"]["expression"]
        self.assertTrue(expression.startswith("case(month("), expression[:40])
        self.assertFalse(expression.startswith("case(("), expression[:40])

    def test_no_ELSE_means_no_trailing_value(self):
        """The capture has no ELSE, and a SQL CASE without one returns NULL.
        `case` with an even argument count calls `ibis.cases` with no `else_`,
        which is also NULL. An invented else would relabel every row that
        matches nothing."""
        expression = self.labelling()["expression"]["expression"]
        self.assertTrue(expression.rstrip().endswith("'12-Dec')"), expression[-30:])

    def test_an_ELSE_becomes_the_trailing_value(self):
        expression = self.labelling(self.operations(
            MONTH_LABEL.read_text().replace("END AS `Month Label`",
                                            "ELSE 'Unknown' END AS `Month Label`")
        ))["expression"]["expression"]
        self.assertTrue(expression.rstrip().endswith("'12-Dec', 'Unknown')"),
                        expression[-40:])

    def test_the_labelled_column_is_a_String_dimension(self):
        dimensions = {d["dimension_name"]: d["data_type"] for d in
                      [op for op in self.operations()
                       if op["type"] == "summarize"][0]["dimensions"]}
        self.assertEqual(dimensions,
                         {"custom_proposed_date": "Date", "month_label": "String",
                          "month_no": "Integer"})

    def test_the_mutate_comes_before_the_summarize_that_groups_by_it(self):
        kinds = [op["type"] for op in self.operations()]
        self.assertLess(max(i for i, k in enumerate(kinds) if k == "mutate"),
                        kinds.index("summarize"))

    def test_SQL_equality_becomes_the_dialects_double_equals(self):
        """`status == 'Active'` in `functions.py`'s own examples, not SQL's
        single `=`. A lone `=` would be an assignment, not a comparison."""
        expression = self.labelling()["expression"]["expression"]
        self.assertIn("== 1,", expression)
        self.assertIsNone(re.search(r"[^=]=\s*\d", expression), expression)


class TestWhatACaseRefuses(unittest.TestCase):
    """Much narrower than `case` can express, because this becomes text a query
    engine evaluates. One column — or one date part of one — compared against
    one literal, producing one literal."""

    COLUMNS = TestACaseThatMapsValuesToLabels.COLUMNS

    def refusal(self, replacement, original="MONTH(`tabQuality Action`.`custom_proposed_date`) = 1"):
        result = analyze_sql(MONTH_LABEL.read_text().replace(original, replacement, 1))
        self.assertFalse(result["supported"], "expected a refusal")
        return " | ".join(result["reasons"])

    def test_a_compound_condition_refuses(self):
        """One comparison per branch. A compound one is expressible in the
        dialect and has not been read from anything."""
        self.assertIn("CASE WHEN", self.refusal(
            "MONTH(`tabQuality Action`.`custom_proposed_date`) = 1 AND `name` = 'x'"))

    def test_IS_NULL_refuses(self):
        self.assertIn("CASE WHEN", self.refusal(
            "`tabQuality Action`.`custom_proposed_date` IS NULL"))

    def test_LIKE_inside_a_branch_refuses(self):
        """It is already refused as a filter operator; a CASE is not a way in."""
        self.assertIn("CASE WHEN", self.refusal(
            "`tabQuality Action`.`name` LIKE 'UCC%'"))

    def test_comparing_two_columns_refuses(self):
        self.assertIn("not a plain number or a quoted label", self.refusal(
            "MONTH(`tabQuality Action`.`custom_proposed_date`) = `tabQuality Action`.`name`"))

    def test_a_date_part_Insights_numbers_differently_refuses_here_too(self):
        """The allowlist is the same table the standalone date parts use, so
        DAYOFWEEK's 0-Monday-against-1-Sunday problem cannot be walked around by
        putting it inside a CASE."""
        self.assertIn("not a column or a date part", self.refusal(
            "DAYOFWEEK(`tabQuality Action`.`custom_proposed_date`) = 1"))

    def test_a_COLUMN_as_the_result_refuses(self):
        """A literal is what has been read. A branch returning a column is a
        different capability and would need its own proof."""
        self.assertIn("not a plain number or a quoted label", self.refusal(
            "`tabQuality Action`.`name`", "'01-Jan'"))

    def test_a_COMPUTED_result_refuses(self):
        self.assertIn("not a plain number or a quoted label", self.refusal(
            "1 + 1", "'01-Jan'"))

    def test_branches_returning_different_types_refuse(self):
        """A column holds one type. A branch returning a number and another
        returning a label are two columns wearing one name."""
        self.assertIn("a column holds one type",
                      self.refusal("1", "'01-Jan'"))

    def test_the_simple_CASE_form_refuses(self):
        """`CASE x WHEN 1 THEN …` compares x against each value; `CASE WHEN …`
        evaluates each condition. Reading one as the other changes what every
        branch tests."""
        sql = MONTH_LABEL.read_text().replace(
            "CASE\n        WHEN MONTH(`tabQuality Action`.`custom_proposed_date`) = 1",
            "CASE MONTH(`tabQuality Action`.`custom_proposed_date`)\n        WHEN 1")
        result = analyze_sql(sql)
        self.assertFalse(result["supported"])
        self.assertIn("simple form", " | ".join(result["reasons"]))

    def test_a_label_carrying_a_QUOTE_refuses(self):
        """The boundary that matters. This expression is a string somebody else
        evaluates; a literal that cannot terminate itself early cannot become
        code."""
        self.assertIn("not a plain number or a quoted label",
                      self.refusal("'01-Jan'', evil('", "'01-Jan'"))

    def test_a_label_carrying_a_BACKSLASH_refuses(self):
        self.assertIn("not a plain number or a quoted label",
                      self.refusal(r"'01\\Jan'", "'01-Jan'"))

    def test_a_CASE_somewhere_the_reader_never_looks_still_refuses(self):
        """The global marker is what catches those, and it still fires — a
        translated CASE stops tripping it only because the lift removes its text
        from the statement first."""
        result = analyze_sql(
            "SELECT COUNT(*) AS `n` FROM `tabStudent Applicant` "
            "WHERE CASE WHEN `status` = 'A' THEN 1 ELSE 0 END = 1")
        self.assertFalse(result["supported"])
        self.assertIn("CASE expression", " | ".join(result["reasons"]))

    def test_the_composite_index_report_is_STILL_refused(self):
        """ADR-014 is not reversed by this. That decision rested on a
        hand-rolled pivot and seven other gaps, not on the conditional being
        unavailable."""
        sql = ("SELECT AVG(`w`.`score`) AS `avg` FROM ( SELECT CASE "
               "WHEN LOWER(TRIM(`c`.`response`)) = 'strongly agree' THEN 5 "
               "WHEN LOWER(TRIM(`c`.`response`)) = 'agree' THEN 4 END AS `score` "
               "FROM `tabSurvey` LEFT JOIN `tabEntry` c "
               "ON `tabSurvey`.`name` = c.`parent` ) AS `w`")
        result = analyze_sql(sql)
        self.assertFalse(result["supported"])
        self.assertIn("not a column or a date part", " | ".join(result["reasons"]))


class TestAnInlineGroupByExpression(unittest.TestCase):
    """The FLAT shape, as against the wrapped one `lift_renaming_wrapper` takes.

    Metabase compiles the same question both ways. Wrapped, the expression is a
    named column in a subquery. Flat, the function sits inline in the SELECT
    list, the GROUP BY and the ORDER BY at once — three refusals with one cause.

    Position, not vocabulary: only calls `_computed_column` already accepts are
    lifted, so the allowlist is exactly what it was.
    """

    COLUMNS = {"Quality Action": {"name": "String", "custom_proposed_date": "Date",
                                  "score": "Decimal"}}
    SQL = ("SELECT MONTH(`tabQuality Action`.`custom_proposed_date`) AS "
           "`custom_proposed_date`, AVG(`tabQuality Action`.`score`) AS `avg`, "
           "COUNT(*) AS `count` FROM `tabQuality Action` "
           "GROUP BY MONTH(`tabQuality Action`.`custom_proposed_date`) "
           "ORDER BY MONTH(`tabQuality Action`.`custom_proposed_date`) ASC")

    def operations(self, sql=None):
        result = operations_from_sql(analyze_sql(sql or self.SQL), self.COLUMNS)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        return result["operations"]

    def test_it_converts_in_full(self):
        self.assertEqual([op["type"] for op in self.operations()],
                         ["source", "mutate", "summarize", "order_by"])

    def test_the_three_references_resolve_to_ONE_mutate(self):
        """The SELECT item, the GROUP BY and the ORDER BY are the same function
        on the same column. Two mutates would be two columns holding the same
        number, and the summarize would group by one of them."""
        mutates = [op for op in self.operations() if op["type"] == "mutate"]
        self.assertEqual(len(mutates), 1)
        self.assertEqual(mutates[0]["expression"]["expression"],
                         "month(custom_proposed_date)")

    def test_the_same_expression_twice_in_one_GROUP_BY_is_one_mutate(self):
        """Odd but legal SQL. Two identical mutates would be two columns
        holding the same number, and the summarize would group by both."""
        operations = self.operations(self.SQL.replace(
            "GROUP BY MONTH(`tabQuality Action`.`custom_proposed_date`) ",
            "GROUP BY MONTH(`tabQuality Action`.`custom_proposed_date`), "
            "MONTH(`tabQuality Action`.`custom_proposed_date`) "))
        self.assertEqual(len([op for op in operations if op["type"] == "mutate"]), 1)

    def test_a_YEAR_beside_it_becomes_a_GRANULARITY_not_a_second_mutate(self):
        """ADR-024: YEAR in a GROUP BY is the date column with
        `granularity: "year"`, which stays chartable. MONTH cannot be, so it
        keeps its mutate — the two live side by side."""
        operations = self.operations(self.SQL.replace(
            "GROUP BY MONTH(`tabQuality Action`.`custom_proposed_date`) ",
            "GROUP BY MONTH(`tabQuality Action`.`custom_proposed_date`), "
            "YEAR(`tabQuality Action`.`custom_proposed_date`) "))
        self.assertEqual(
            [op["new_name"] for op in operations if op["type"] == "mutate"],
            ["month_of_custom_proposed_date"])
        dimensions = [op for op in operations
                      if op["type"] == "summarize"][0]["dimensions"]
        self.assertIn({"dimension_name": "custom_proposed_date",
                       "column_name": "custom_proposed_date",
                       "data_type": "Date", "granularity": "year"}, dimensions)

    def test_the_grouping_and_the_ordering_both_name_it(self):
        operations = self.operations()
        summarize = [op for op in operations if op["type"] == "summarize"][0]
        self.assertEqual([d["column_name"] for d in summarize["dimensions"]],
                         ["month_of_custom_proposed_date"])
        self.assertEqual(operations[-1]["column"]["column_name"],
                         "month_of_custom_proposed_date")

    def test_the_new_name_is_NOT_the_one_metabase_gave_it(self):
        """Metabase names the item after the column it reads —
        `MONTH(`d`) AS `d`` — and a mutate creating `d` from `d` either reads
        itself or shadows the source."""
        mutate = [op for op in self.operations() if op["type"] == "mutate"][0]
        self.assertEqual(mutate["new_name"], "month_of_custom_proposed_date")
        self.assertNotEqual(mutate["new_name"], "custom_proposed_date")

    def test_a_generated_name_that_collides_with_a_real_column_refuses(self):
        columns = {"Quality Action": dict(self.COLUMNS["Quality Action"],
                                          month_of_custom_proposed_date="Integer")}
        result = operations_from_sql(analyze_sql(self.SQL), columns)
        self.assertFalse(result["supported"])
        self.assertIn("cannot be told apart", " | ".join(result["reasons"]))

    def test_a_function_off_the_allowlist_still_refuses_by_name(self):
        """Lifting is about POSITION. DAYOFWEEK numbers the days differently
        from MySQL and WEEK takes a mode argument; neither becomes acceptable
        by moving."""
        for name in ("DAYOFWEEK", "WEEK", "TRIM"):
            with self.subTest(name):
                result = analyze_sql(self.SQL.replace("MONTH(", name + "("))
                self.assertFalse(result["supported"])
                self.assertIn(name, " | ".join(result["reasons"]))

    def test_a_wrapped_query_is_still_the_wrappers_business(self):
        """The inline lift runs AFTER the wrapper rules, so the shape they
        already handle is untouched."""
        self.assertTrue(analyze_sql(YEAR_LABEL.read_text())["supported"])

    def test_grouping_by_a_plain_column_is_unchanged(self):
        operations = self.operations(
            "SELECT `custom_proposed_date`, COUNT(*) AS `n` FROM `tabQuality Action` "
            "GROUP BY `custom_proposed_date`")
        self.assertEqual([op["type"] for op in operations], ["source", "summarize"])


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


class TestTwoYearMutatesDoNotCollide(unittest.TestCase):
    """Regression: "Duplicate column name 'custom_proposed_date'", live.

    `regrouped_month_card.sql` is the month-label fixture after the regroup
    button substituted MONTH( -> YEAR( everywhere — so `Year` (the CONCAT
    lift) and `Month No` are BOTH exactly `year(custom_proposed_date)`.
    Promoting both made the summarize emit the same column twice, which
    converts cleanly and fails the moment the query runs.

    Two dimensions that reduce to the same date-at-same-granularity are the
    same dimension, and choosing which alias survives would be a guess — so a
    shared column promotes NEITHER, and the numeric mutates stay.
    """

    FIXTURE = (pathlib.Path(__file__).resolve().parent / "fixtures"
               / "regrouped_month_card.sql")
    COLUMNS = TestACaseThatMapsValuesToLabels.COLUMNS

    def operations(self):
        result = operations_from_sql(analyze_sql(self.FIXTURE.read_text()),
                                     self.COLUMNS)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        return result["operations"]

    def test_no_dimension_appears_twice(self):
        dimensions = [op for op in self.operations()
                      if op["type"] == "summarize"][0]["dimensions"]
        names = [d["dimension_name"] for d in dimensions]
        self.assertEqual(len(names), len(set(names)), names)

    def test_neither_shared_candidate_is_promoted(self):
        """Refused, not collapsed: picking `Year` over `Month No` (or the
        reverse) would guess which grouping the user meant."""
        operations = self.operations()
        mutated = {op["new_name"] for op in operations if op["type"] == "mutate"}
        self.assertIn("year", mutated)
        self.assertIn("month_no", mutated)
        dimensions = [op for op in operations
                      if op["type"] == "summarize"][0]["dimensions"]
        self.assertEqual([d.get("granularity") for d in dimensions],
                         [None, None, None])

    def test_a_SINGLE_year_mutate_in_another_column_still_promotes(self):
        """The collision rule is per COLUMN — one year(a) beside two year(b)s
        still promotes the a one."""
        from dashboard_studio.integrations.metabase.sql_ops import (
            _promote_year_mutates,
        )
        operations = [
            {"type": "mutate", "new_name": "YA",
             "expression": {"type": "expression", "expression": "year(a)"}},
            {"type": "mutate", "new_name": "YB1",
             "expression": {"type": "expression", "expression": "year(b)"}},
            {"type": "mutate", "new_name": "YB2",
             "expression": {"type": "expression", "expression": "year(b)"}},
            {"type": "summarize", "measures": [],
             "dimensions": [
                 {"dimension_name": "YA", "column_name": "YA",
                  "data_type": "Integer"},
                 {"dimension_name": "YB1", "column_name": "YB1",
                  "data_type": "Integer"},
                 {"dimension_name": "YB2", "column_name": "YB2",
                  "data_type": "Integer"}]},
        ]
        _promote_year_mutates(operations, {"T": {"a": "Date", "b": "Date"}})
        dimensions = operations[-1]["dimensions"]
        self.assertEqual(
            [(d["column_name"], d.get("granularity")) for d in dimensions],
            [("a", "year"), ("YB1", None), ("YB2", None)])


class TestTheSurveyTrackingFamily(unittest.TestCase):
    """The sole-41 subquery family — RECONSTRUCTED from the captured residues,
    not captured itself, and labelled so on purpose.

    wrapper_residue.py's output (cards 2032/1795/2076/1820) showed one family:
    `tabSurvey Tracking` LEFT JOIN its child table ON name=parent, LEFT JOIN a
    survey DocType ON survey_entry=name, inner `col * 5` scale factors, WHERE
    on the FROM table, outer aggregation. Two blockers, both settled from
    source rather than the residue text:

    - `_PROJECTED` required a column's first character to be a letter, so an
      operand projecting `1_3_months` (a real column on `tabEnd of Course
      Survey`) could never be proven an identity and the whole card refused as
      "subquery". Backticks are what make a digit-leading name an identifier
      rather than a literal, so the backticked branch now admits it — and the
      bare-literal guard (`SELECT 1` is not a projection) stays.

    - An EXPRESSION reading such a column refuses BY NAME: Insights evaluates
      a mutate's expression as Python (`ibis_utils.py` at v3.12.2 —
      `ast.parse` plus columns injected as variables), and a Python name
      cannot start with a digit, so `1_3_months * 5` is a SyntaxError the
      moment the query opens. The same column is fine in every JSON position:
      join select_columns, filter rules, summarize measures.
    """

    COLUMNS = {
        "Survey Tracking": {"name": "String", "department": "String",
                            "survey_type": "String"},
        "Survey Tracking List of Surveys Childtable": {
            "name": "String", "parent": "String", "survey_entry": "String"},
        "End of Course Survey": {"name": "String", "1_3_months": "Integer",
                                 "2k_4k": "Integer"},
    }

    def family(self, item, inner_item):
        return (
            "SELECT `__mb`.`department` AS `department`, " + item + " FROM ( "
            "SELECT `tabSurvey Tracking`.`department` AS `department`, "
            + inner_item + " FROM "
            "( SELECT * FROM `tabSurvey Tracking` ) AS `tabSurvey Tracking` "
            "LEFT JOIN ( SELECT * FROM `tabSurvey Tracking List of Surveys "
            "Childtable` ) AS `Child` "
            "ON `Child`.`parent` = `tabSurvey Tracking`.`name` "
            "LEFT JOIN ( SELECT `1_3_months` AS `1_3_months`, `2k_4k`, `name` "
            "FROM `tabEnd of Course Survey` ) AS `tabEnd of Course Survey` "
            "ON `Child`.`survey_entry` = `tabEnd of Course Survey`.`name` "
            "WHERE `tabSurvey Tracking`.`survey_type` = 'Exit' ) AS `__mb` "
            "GROUP BY `__mb`.`department`")

    def test_a_digit_led_projection_is_an_identity(self):
        """The operand that never unwrapped, isolated."""
        sql = ("SELECT `w`.`1_3_months` FROM ( SELECT `1_3_months` AS "
               "`1_3_months`, `2k_4k` FROM `tabEnd of Course Survey` ) AS `w`")
        self.assertNotIn("( SELECT", unwrap_derived_tables(sql)[len("SELECT"):])

    def test_a_bare_literal_is_still_NOT_a_projection(self):
        """The guard the letter-first rule existed for. `SELECT 1` reads as a
        literal, not a column called 1, and the wrapper stays."""
        sql = "SELECT `w`.`x` FROM ( SELECT 1 FROM `tabX` ) AS `w`"
        self.assertIn("( SELECT 1 FROM", unwrap_derived_tables(sql))

    def test_the_family_with_a_DIRECT_aggregate_converts_whole(self):
        """AVG over the digit column itself: every position it reaches is JSON
        (measure, join select_columns), so nothing evaluates its name."""
        sql = self.family("AVG(`__mb`.`1_3_months`) AS `avg`",
                          "`tabEnd of Course Survey`.`1_3_months` AS `1_3_months`")
        result = operations_from_sql(analyze_sql(sql), self.COLUMNS)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual([op["type"] for op in result["operations"]],
                         ["source", "join", "join", "filter", "summarize"])
        measure = [op for op in result["operations"]
                   if op["type"] == "summarize"][0]["measures"][0]
        self.assertEqual(measure["column_name"], "1_3_months")
        self.assertEqual(measure["measure_name"], "avg_of_1_3_months")

    def test_a_SCALE_FACTOR_on_a_digit_column_refuses_by_name(self):
        """`1_3_months * 5` would be a Python SyntaxError inside Insights."""
        sql = self.family("AVG(`__mb`.`q1`) AS `avg`",
                          "`tabEnd of Course Survey`.`1_3_months` * 5 AS `q1`")
        result = operations_from_sql(analyze_sql(sql), self.COLUMNS)
        self.assertFalse(result["supported"])
        self.assertEqual(result["operations"], [])
        self.assertTrue(any("cannot be written in a Python expression" in reason
                            for reason in result["reasons"]), result["reasons"])
        self.assertTrue(any("Aggregating or filtering the column directly is fine"
                            in reason for reason in result["reasons"]))

    def test_a_LETTER_named_scale_factor_still_converts(self):
        """The guard must not catch the ordinary ADR-013 case."""
        columns = dict(self.COLUMNS)
        columns["End of Course Survey"] = dict(columns["End of Course Survey"],
                                               overall="Integer")
        sql = self.family("AVG(`__mb`.`q1`) AS `avg`",
                          "`tabEnd of Course Survey`.`overall` * 5 AS `q1`")
        result = operations_from_sql(analyze_sql(sql), columns)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertIn({"type": "mutate", "new_name": "q1", "data_type": "Auto",
                       "expression": {"type": "expression",
                                      "expression": "overall * 5"}},
                      result["operations"])

    def test_the_2076_shape_converts_end_to_end(self):
        """The cleanest capture's described shape: letter-named survey columns,
        `col * 5` pair, OR filter on the FROM table, ADR-011 outer expression.
        Reconstructed; the live check on the real card is the user's step."""
        columns = {"Survey Tracking": self.COLUMNS["Survey Tracking"],
                   "Survey Tracking List of Surveys Childtable":
                       self.COLUMNS["Survey Tracking List of Surveys Childtable"],
                   "Staff Survey": {"name": "String", "communication": "Integer",
                                    "clarity": "Integer"}}
        sql = (
            "SELECT `__mb`.`department` AS `department`, "
            "CAST(AVG(`__mb`.`q1`) + AVG(`__mb`.`q2`) AS double) / 2.0 AS `index` "
            "FROM ( SELECT `tabSurvey Tracking`.`department` AS `department`, "
            "`tabStaff Survey`.`communication` * 5 AS `q1`, "
            "`tabStaff Survey`.`clarity` * 5 AS `q2` FROM `tabSurvey Tracking` "
            "LEFT JOIN `tabSurvey Tracking List of Surveys Childtable` AS `Child` "
            "ON `Child`.`parent` = `tabSurvey Tracking`.`name` "
            "LEFT JOIN `tabStaff Survey` "
            "ON `Child`.`survey_entry` = `tabStaff Survey`.`name` "
            "WHERE `tabSurvey Tracking`.`survey_type` = 'Employee Satisfaction' "
            "OR `tabSurvey Tracking`.`survey_type` = 'ESI' ) AS `__mb` "
            "GROUP BY `__mb`.`department` ORDER BY `__mb`.`department` ASC")
        result = operations_from_sql(analyze_sql(sql), columns)
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        kinds = [op["type"] for op in result["operations"]]
        self.assertEqual(kinds, ["source", "join", "join", "mutate", "mutate",
                                 "filter_group", "summarize", "mutate",
                                 "order_by"])
        final = result["operations"][-2]
        self.assertEqual(final["expression"]["expression"],
                         "(avg_of_q1 + avg_of_q2) / 2.0")


class TestTheEmployeeSatisfactionCapture(unittest.TestCase):
    """Card 2076 VERBATIM, the capture that disproved the reconstruction.

    The reconstruction above converts and the real card refused, and the
    difference was one invisible character: Metabase's compiled alias
    `Exit  Qn. 7` carries a DOUBLE space. The lift normalised each item's
    whitespace before reading its alias, so the renames map held the
    single-space spelling while the outer SELECT still referenced the
    double-space one — an unmapped reference, a decline, and a refusal
    naming "subquery" for a space nobody could see.

    Two fixes, both visible here: the alias is read from the item's RAW
    text, and every computed alias is slugged with Insights' own
    `sanitize_name` transform before it can reach expression text — these
    are the compiler's working names, and a measure name built from the raw
    spelling (`avg_of_Exit  Qn. 7`) is a Python SyntaxError the moment
    Insights evaluates the ADR-011 expression that reads it.
    """

    COLUMNS = {
        "Survey Tracking": {"name": "String", "survey_name": "String"},
        "Survey Tracking List of Surveys Childtable": {
            "name": "String", "parent": "String", "survey_entry": "String"},
        "Exit Interview Survey": {"name": "String", "rate_7": "Integer",
                                  "rate_12": "Integer"},
        "Staff Survey": {"name": "String", "rating_7": "Integer",
                         "rating_12": "Integer"},
        "Staff Onboarding Survey": {"name": "String", "qn_1": "Integer",
                                    "qn_5": "Integer"},
    }

    def result(self):
        return operations_from_sql(analyze_sql(SATISFACTION.read_text()),
                                   self.COLUMNS)

    def test_the_real_card_converts_end_to_end(self):
        result = self.result()
        self.assertTrue(result["supported"], " | ".join(result["reasons"]))
        self.assertEqual(
            [op["type"] for op in result["operations"]],
            ["source", "join", "join", "join", "join",
             "mutate", "mutate", "mutate", "mutate", "mutate", "mutate",
             "filter_group", "summarize", "mutate", "mutate", "mutate",
             "order_by"])

    def test_the_six_working_columns_are_slugged_in_full(self):
        """`Qn. 1` -> `qn__1`: the dot and the space each become `_`, which is
        exactly what Insights' own apply_mutate would have renamed them to —
        so the stored JSON and the engine agree byte for byte. The double
        space in `Exit  Qn. 7` survives as a double underscore, DIFFERENT
        from `Exit Qn.12`'s single one: the slug keeps the two apart."""
        mutates = [op for op in self.result()["operations"]
                   if op["type"] == "mutate"][:6]
        self.assertEqual(mutates, [
            {"type": "mutate", "new_name": "staff_onboarding_qn__1",
             "data_type": "Auto", "expression": {
                 "type": "expression", "expression": "qn_1 * 5"}},
            {"type": "mutate", "new_name": "staff_onboarding_qn__5",
             "data_type": "Auto", "expression": {
                 "type": "expression", "expression": "qn_5 * 5"}},
            {"type": "mutate", "new_name": "staff_survey_qn__7",
             "data_type": "Auto", "expression": {
                 "type": "expression", "expression": "rating_7 * 5"}},
            {"type": "mutate", "new_name": "staff_survey_qn__12",
             "data_type": "Auto", "expression": {
                 "type": "expression", "expression": "rating_12 * 5"}},
            {"type": "mutate", "new_name": "exit__qn__7",
             "data_type": "Auto", "expression": {
                 "type": "expression", "expression": "rate_7 * 5"}},
            {"type": "mutate", "new_name": "exit_qn_12",
             "data_type": "Auto", "expression": {
                 "type": "expression", "expression": "rate_12 * 5"}},
        ])

    def test_the_averages_read_the_slugged_measures(self):
        operations = self.result()["operations"]
        summarize = [op for op in operations if op["type"] == "summarize"][0]
        self.assertEqual(
            [m["measure_name"] for m in summarize["measures"]],
            ["avg_of_staff_onboarding_qn__1", "avg_of_staff_onboarding_qn__5",
             "avg_of_staff_survey_qn__7", "avg_of_staff_survey_qn__12",
             "avg_of_exit__qn__7", "avg_of_exit_qn_12"])
        self.assertEqual(
            [(op["new_name"], op["expression"]["expression"])
             for op in operations[operations.index(summarize) + 1:]
             if op["type"] == "mutate"],
            [("Staff Onboarding Average (Obj. 5)",
              "(avg_of_staff_onboarding_qn__1 + avg_of_staff_onboarding_qn__5)"
              " / 2.0"),
             ("Staff Survey Average (Obj.5)",
              "(avg_of_staff_survey_qn__7 + avg_of_staff_survey_qn__12) / 2.0"),
             ("Exit Average (Obj.5)",
              "(avg_of_exit__qn__7 + avg_of_exit_qn_12) / 2.0")])

    def test_every_expression_parses_as_python(self):
        """The whole point of the slug: Insights runs `ast.parse` over every
        expression with columns injected as Python variables, so an
        expression that does not parse is a query that fails on open."""
        import ast
        for op in self.result()["operations"]:
            if op["type"] == "mutate":
                ast.parse(op["expression"]["expression"])

    def test_the_CHOSEN_labels_are_not_slugged(self):
        """`Staff Onboarding Average (Obj. 5)` is the name a person typed into
        Metabase and the name they read in Insights' operation list. It never
        reaches expression text — nothing downstream reads it — so it keeps
        its raw spelling; only the wrapper's internal working names slug."""
        names = [op["new_name"] for op in self.result()["operations"]
                 if op["type"] == "mutate"][6:]
        self.assertEqual(names, ["Staff Onboarding Average (Obj. 5)",
                                 "Staff Survey Average (Obj.5)",
                                 "Exit Average (Obj.5)"])

    def test_the_OR_filter_survives_as_a_filter_group(self):
        group = [op for op in self.result()["operations"]
                 if op["type"] == "filter_group"][0]
        self.assertEqual(group["logical_operator"], "Or")
        self.assertEqual([f["value"] for f in group["filters"]],
                         ["Exit Interview Survey", "Staff Survey"])

    def test_two_aliases_reducing_to_one_slug_refuse_by_both_names(self):
        """`Qn. 1` and `Qn 1` both slug to `qn__1`/`qn_1`? No — to different
        names. But `Qn.1` and `Qn_1` DO collide, and silently merging two
        different columns into one is a query answering a different
        question."""
        sql = SATISFACTION.read_text().replace(
            "`qn_5` * 5 AS `Staff Onboarding Qn. 5`",
            "`qn_5` * 5 AS `Staff Onboarding Qn__1`")
        result = analyze_sql(sql)
        self.assertFalse(result["supported"])
        joined = " | ".join(result["reasons"])
        self.assertIn("Staff Onboarding Qn. 1", joined)
        self.assertIn("Staff Onboarding Qn__1", joined)
        self.assertIn("cannot be told apart", joined)

    def test_a_KEYWORD_named_column_refuses(self):
        """The generalised ADR-032 guard: `class * 5` is a SyntaxError just as
        `1_3_months * 5` is — `isidentifier` alone passes keywords, which is
        why the guard checks both."""
        columns = {doctype: dict(fields) for doctype, fields
                   in self.COLUMNS.items()}
        columns["Staff Onboarding Survey"]["class"] = "Integer"
        sql = SATISFACTION.read_text().replace(
            "`TabStaff Onboarding Survey - Survey Entry`.`qn_1` * 5",
            "`TabStaff Onboarding Survey - Survey Entry`.`class` * 5")
        result = operations_from_sql(analyze_sql(sql), columns)
        self.assertFalse(result["supported"])
        self.assertTrue(any("cannot be written in a Python expression" in r
                            for r in result["reasons"]), result["reasons"])
