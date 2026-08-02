"""MBQL 5 -> Insights v3 operations.

Fixtures follow the MBQL 5 schema read from Metabase's source: a stage carries
`source-table`, `filters` (plural), `aggregation`, `breakout` and `joins`, and a
field ref is `[:field opts id]` with the **options map at position 1**. The
first attempt at this converter read position 1 as the identifier — the legacy
layout — and so parsed nothing at all. Several tests below exist purely to keep
that from coming back.

Expected operations are written out in full rather than spot-checked. This
translator's failure mode is a query that runs fine and answers a different
question, so "the right keys are present" is not enough; the whole shape has to
match what Insights' own types describe.
"""

import unittest

from dashboard_studio.integrations.metabase.mbql import translate_card

METADATA = {
    "tables": {2201: {"name": "tabStudent Applicant"},
               2359: {"name": "tabPurchase Order"}},
    "fields": {
        11: {"name": "status", "data_type": "String"},
        12: {"name": "intake_year", "data_type": "String"},
        13: {"name": "fee", "data_type": "Decimal"},
        14: {"name": "applied_on", "data_type": "Date"},
        15: {"name": "po_ref", "data_type": "String"},
        21: {"name": "po_name", "data_type": "String"},
    },
    "table_columns": {2359: ["po_name", "supplier"]},
}


def field(field_id, opts=None):
    """An MBQL 5 field ref: [:field opts id] — opts FIRST."""
    return ["field", opts or {}, field_id]


def card(**stage):
    base = {"lib/type": "mbql.stage/mbql", "source-table": 2201}
    base.update(stage)
    return {"id": 1, "dataset_query": {
        "lib/type": "mbql/query", "database": 3, "stages": [base]}}


def run(**stage):
    return translate_card(card(**stage), METADATA)


class TestSupported(unittest.TestCase):
    def test_a_bare_source_table(self):
        result = run()
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"], [
            {"type": "source", "table": {"type": "table", "data_source": "Site DB",
                                         "table_name": "tabStudent Applicant"}}])

    def test_count_by_one_breakout_in_full(self):
        result = run(aggregation=[["count", {}]], breakout=[field(12)])
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"][1], {
            "type": "summarize",
            "measures": [{"measure_name": "count", "column_name": "count",
                          "data_type": "Integer", "aggregation": "count"}],
            "dimensions": [{"dimension_name": "intake_year", "column_name": "intake_year",
                            "data_type": "String"}],
        })

    def test_a_filter_becomes_a_filter_operation(self):
        result = run(filters=[["=", {}, field(11), "Enrolled"]])
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"][1], {
            "type": "filter",
            "column": {"type": "column", "column_name": "status"},
            "operator": "=", "value": "Enrolled"})

    def test_every_shared_comparison_operator(self):
        for mbql_op in ("=", "!=", ">", ">=", "<", "<="):
            result = run(filters=[[mbql_op, {}, field(13), 100]])
            self.assertTrue(result["supported"], f"{mbql_op}: {result['reasons']}")
            self.assertEqual(result["operations"][1]["operator"], mbql_op)

    def test_sum_of_a_numeric_column(self):
        result = run(aggregation=[["sum", {}, field(13)]], breakout=[field(12)])
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"][1]["measures"], [
            {"measure_name": "sum_of_fee", "column_name": "fee",
             "data_type": "Decimal", "aggregation": "sum"}])

    def test_distinct_maps_to_insights_count_distinct(self):
        """Counting distinct values of a TEXT column is ordinary, so the
        numeric requirement must not apply to it. The result is a count, so its
        data_type is Integer regardless of the column it read."""
        result = run(aggregation=[["distinct", {}, field(11)]])
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"][1]["measures"][0], {
            "measure_name": "count_distinct_of_status", "column_name": "status",
            "data_type": "Integer", "aggregation": "count_distinct"})

    def test_only_the_arithmetic_aggregations_demand_a_number(self):
        for tag in ("sum", "avg", "min", "max"):
            self.assertFalse(run(aggregation=[[tag, {}, field(11)]])["supported"],
                             f"{tag} of a String should refuse")
        for tag in ("distinct",):
            self.assertTrue(run(aggregation=[[tag, {}, field(11)]])["supported"],
                            f"{tag} of a String is legitimate")

    def test_a_date_breakout_is_a_dimension(self):
        result = run(aggregation=[["count", {}]], breakout=[field(14)])
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"][1]["dimensions"][0]["data_type"], "Date")

    def test_two_breakouts_become_two_dimensions(self):
        result = run(aggregation=[["count", {}]], breakout=[field(12), field(11)])
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual([d["column_name"] for d in result["operations"][1]["dimensions"]],
                         ["intake_year", "status"])

    def test_a_join_in_full(self):
        result = run(joins=[{
            "lib/type": "mbql/join", "alias": "PO", "strategy": "left-join",
            "stages": [{"source-table": 2359}],
            "conditions": [["=", {}, field(15), field(21)]]}])
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"][1], {
            "type": "join", "join_type": "left",
            "table": {"type": "table", "data_source": "Site DB",
                      "table_name": "tabPurchase Order"},
            "select_columns": [{"type": "column", "column_name": "po_name"},
                               {"type": "column", "column_name": "supplier"}],
            "join_condition": {
                "left_column": {"type": "column", "column_name": "po_ref"},
                "right_column": {"type": "column", "column_name": "po_name"}},
        })

    def test_a_join_with_no_strategy_defaults_to_left_as_metabase_does(self):
        result = run(joins=[{"lib/type": "mbql/join", "alias": "PO",
                             "stages": [{"source-table": 2359}],
                             "conditions": [["=", {}, field(15), field(21)]]}])
        self.assertEqual(result["operations"][1]["join_type"], "left")

    def test_operations_come_out_in_execution_order(self):
        result = run(
            joins=[{"lib/type": "mbql/join", "alias": "PO",
                    "stages": [{"source-table": 2359}],
                    "conditions": [["=", {}, field(15), field(21)]]}],
            filters=[["=", {}, field(11), "Enrolled"]],
            aggregation=[["count", {}]], breakout=[field(12)])
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual([op["type"] for op in result["operations"]],
                         ["source", "join", "filter", "summarize"],
                         "source, then join, then filter, then summarize")

    def test_keywords_may_arrive_colon_prefixed(self):
        """Serialisers differ on whether a Clojure keyword keeps its colon."""
        result = translate_card({"id": 1, "dataset_query": {"stages": [
            {"lib/type": ":mbql.stage/mbql", "source-table": 2201,
             "aggregation": [[":count", {}]]}]}}, METADATA)
        self.assertTrue(result["supported"], result["reasons"])


class TestRefusals(unittest.TestCase):
    def assert_refused(self, result, fragment):
        self.assertFalse(result["supported"], "expected a refusal")
        self.assertEqual(result["operations"], [],
                         "a refused translation still handed back operations")
        joined = " | ".join(result["reasons"])
        self.assertIn(fragment, joined)
        return joined

    def test_the_ratio_shape_that_this_converter_exists_to_refuse(self):
        """Delivery Rate: [:* [:/ [:count-where …] [:count]] 100]."""
        result = run(aggregation=[["*", {}, ["/", {}, ["count-where", {}], ["count", {}]], 100]])
        self.assert_refused(result, "compound or custom expression")

    def test_a_custom_column_is_refused(self):
        self.assert_refused(run(expressions={"margin": ["-", {}, field(13), 1]}),
                            "a custom column")

    def test_a_row_limit_is_refused_because_it_changes_the_number(self):
        self.assert_refused(run(limit=10), "a row limit")

    def test_a_sort_is_refused(self):
        self.assert_refused(run(**{"order-by": [["asc", {}, field(12)]]}), "a sort")

    def test_an_explicit_column_selection_is_refused(self):
        self.assert_refused(run(fields=[field(11)]), "an explicit column selection")

    def test_a_question_built_on_another_question_is_refused(self):
        self.assert_refused(run(**{"source-card": 1474}), "built on another question")

    def test_a_multi_stage_query_is_refused(self):
        subject = card(aggregation=[["count", {}]])
        subject["dataset_query"]["stages"].append({"lib/type": "mbql.stage/mbql"})
        self.assert_refused(translate_card(subject, METADATA), "runs in 2 stages")

    def test_a_native_card_is_sent_to_the_sql_path(self):
        subject = {"id": 1, "dataset_query": {"stages": [
            {"lib/type": "mbql.stage/native", "native": "SELECT 1"}]}}
        self.assert_refused(translate_card(subject, METADATA), "send it through the SQL path")

    def test_a_date_bucket_is_refused_rather_than_grouped_raw(self):
        """Insights has `granularity`, but its values were not read from source.
        Grouping by the raw timestamp instead would be a different chart."""
        result = run(aggregation=[["count", {}]],
                     breakout=[field(14, {"temporal-unit": "month"})])
        self.assert_refused(result, "date bucket")

    def test_an_unknown_field_id_is_refused_not_skipped(self):
        self.assert_refused(run(filters=[["=", {}, field(999), "x"]]),
                            "Metabase field 999")

    def test_an_unknown_table_is_refused(self):
        subject = card()
        subject["dataset_query"]["stages"][0]["source-table"] = 8888
        self.assert_refused(translate_card(subject, METADATA), "Metabase table 8888")

    def test_a_string_column_cannot_be_summed(self):
        self.assert_refused(run(aggregation=[["sum", {}, field(11)]]),
                            "only a number can be sum'd")

    def test_a_numeric_breakout_is_refused(self):
        self.assert_refused(run(aggregation=[["count", {}]], breakout=[field(13)]),
                            "groups only by")

    def test_an_unsupported_filter_operator_is_named(self):
        self.assert_refused(run(filters=[["contains", {}, field(11), "x"]]),
                            "filter 'contains' is not a simple comparison")

    def test_a_field_to_field_filter_is_refused(self):
        self.assert_refused(run(filters=[["=", {}, field(11), field(12)]]),
                            "compares two fields")

    def test_a_multi_condition_join_is_refused(self):
        self.assert_refused(run(joins=[{
            "lib/type": "mbql/join", "alias": "PO", "stages": [{"source-table": 2359}],
            "conditions": [["=", {}, field(15), field(21)], ["=", {}, field(11), field(21)]]}]),
            "2 conditions")

    def test_a_join_selecting_specific_columns_is_refused(self):
        self.assert_refused(run(joins=[{
            "lib/type": "mbql/join", "alias": "PO", "stages": [{"source-table": 2359}],
            "fields": [field(21)],
            "conditions": [["=", {}, field(15), field(21)]]}]),
            "selects specific columns")

    def test_a_join_whose_columns_are_unknown_is_refused(self):
        metadata = dict(METADATA, table_columns={})
        subject = card(joins=[{"lib/type": "mbql/join", "alias": "PO",
                               "stages": [{"source-table": 2359}],
                               "conditions": [["=", {}, field(15), field(21)]]}])
        self.assert_refused(translate_card(subject, metadata), "columns of joined table")

    def test_grouping_with_no_aggregate_is_refused(self):
        self.assert_refused(run(breakout=[field(12)]), "groups without aggregating")

    def test_a_legacy_mbql_card_is_refused_rather_than_misparsed(self):
        """The shape the first attempt was written against. It must not appear
        to work — a legacy field ref is [:field id opts], so reading it as MBQL 5
        would take the id as an options map."""
        legacy = {"id": 1, "dataset_query": {
            "type": "query",
            "query": {"source-table": 2201, "aggregation": [["count"]]}}}
        self.assert_refused(translate_card(legacy, METADATA), "no 'stages'")

    def test_non_dict_input_is_a_programming_error(self):
        with self.assertRaises(TypeError):
            translate_card("1474", METADATA)


class TestPositionalLayout(unittest.TestCase):
    """The reversal that killed the first attempt, asserted directly."""

    def test_the_options_map_is_at_position_one_not_the_identifier(self):
        result = run(filters=[["=", {}, ["field", {"base-type": "type/Text"}, 11], "Enrolled"]])
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["operations"][1]["column"]["column_name"], "status")

    def test_a_legacy_positional_field_ref_does_not_silently_resolve(self):
        """['field', 11, None] is the LEGACY order. Read as MBQL 5 its
        identifier is None, which must refuse rather than resolve to anything."""
        result = run(filters=[["=", {}, ["field", 11, None], "Enrolled"]])
        self.assertFalse(result["supported"])
        self.assertIn("not in the metadata", " | ".join(result["reasons"]))


if __name__ == "__main__":
    unittest.main()
