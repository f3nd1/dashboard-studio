"""describe_card: what a real Metabase card yields, and what it refuses.

The fixture below is the MBQL 5 shape confirmed live against UCC's Metabase
(v1.62.5.1) — including the inline SQL comment a real card carried, because the
comment is exactly the kind of thing a text-based reader trips over and a JSON
reader should not notice at all.
"""

import unittest

from dashboard_studio.integrations.metabase.card import describe_card, referenced_tables

NATIVE_CARD = {
    "id": 2774,
    "name": "Applicants per Country",
    "display": "bar",
    "query_type": "native",
    "dataset_query": {
        "lib/type": "mbql/query",
        "database": 2,
        "lib.convert/converted?": True,
        "stages": [{
            "lib/type": "mbql.stage/native",
            "native": "-- applicants by country\nSELECT country, COUNT(*) AS count\n"
                      "FROM `tabStudent Applicant` GROUP BY country",
        }],
    },
    "visualization_settings": {
        "graph.dimensions": ["country"],
        "graph.metrics": ["count"],
        "graph.x_axis.title_text": "Country",
    },
    "result_metadata": [
        {"name": "country", "display_name": "Country", "base_type": "type/Text"},
        {"name": "count", "display_name": "Count", "base_type": "type/BigInteger"},
    ],
}


def card(**overrides):
    """A copy of the real card with the named keys replaced."""
    import copy

    out = copy.deepcopy(NATIVE_CARD)
    out.update(overrides)
    return out


def stage(**overrides):
    """The same card with its single native stage altered."""
    out = card()
    out["dataset_query"]["stages"][0].update(overrides)
    return out


class TestSupportedCard(unittest.TestCase):
    def test_reads_the_sql_from_the_mbql5_stage(self):
        result = describe_card(NATIVE_CARD)
        self.assertTrue(result["supported"], result["reasons"])
        self.assertIn("SELECT country", result["sql"])
        # The card's own comment survives verbatim — nothing is stripped here.
        self.assertTrue(result["sql"].startswith("-- applicants by country"))

    def test_title_display_and_axes_come_from_the_card(self):
        result = describe_card(NATIVE_CARD)
        self.assertEqual(result["title"], "Applicants per Country")
        self.assertEqual(result["chart_type"], "bar")
        self.assertEqual(result["x_axis"], "country")
        self.assertEqual(result["y_axis"], "count")

    def test_columns_are_returned_untranslated(self):
        result = describe_card(NATIVE_CARD)
        self.assertEqual(
            result["columns"][1],
            {"name": "count", "display_name": "Count", "base_type": "type/BigInteger"},
        )

    def test_pie_and_scalar_map_to_studios_own_vocabulary(self):
        pie = card(display="pie", visualization_settings={
            "pie.dimension": "country", "pie.metric": "count"})
        self.assertEqual(describe_card(pie)["chart_type"], "donut")
        self.assertEqual(describe_card(pie)["x_axis"], "country")
        self.assertEqual(describe_card(card(display="scalar"))["chart_type"], "number")

    def test_axis_naming_a_column_the_card_does_not_return_is_dropped_not_imported(self):
        stale = card(visualization_settings={
            "graph.dimensions": ["renamed_column"], "graph.metrics": ["count"]})
        result = describe_card(stale)
        self.assertTrue(result["supported"], result["reasons"])
        self.assertEqual(result["x_axis"], "")      # dropped, so Step 2 asks
        self.assertEqual(result["y_axis"], "count")


class TestRefusals(unittest.TestCase):
    def assert_refused(self, subject, fragment):
        result = describe_card(subject)
        self.assertFalse(result["supported"], "expected a refusal")
        joined = " | ".join(result["reasons"])
        self.assertIn(fragment, joined)
        return joined

    def test_gui_question_has_no_sql_to_take(self):
        self.assert_refused(stage(**{"lib/type": "mbql.stage/mbql"}), "GUI-built question")

    def test_multi_stage_query_is_refused_rather_than_truncated(self):
        subject = card()
        subject["dataset_query"]["stages"].append({"lib/type": "mbql.stage/mbql"})
        joined = self.assert_refused(subject, "runs in 2 stages")
        self.assertIn("cannot be translated", joined)

    def test_template_tags_are_refused(self):
        self.assert_refused(
            stage(**{"template-tags": {"start": {"name": "start"}}}), "Metabase variables")

    def test_placeholder_syntax_without_a_tags_dict_is_still_refused(self):
        self.assert_refused(
            stage(native="SELECT * FROM t WHERE d > {{#123-other-card}}"), "{{…}}")

    def test_unmapped_display_is_named(self):
        self.assert_refused(card(display="waterfall"), "'waterfall'")

    def test_missing_result_metadata_is_refused(self):
        self.assert_refused(card(result_metadata=None), "no stored column list")

    def test_legacy_dataset_query_shape_is_named_not_guessed(self):
        legacy = card(dataset_query={"type": "native", "native": {"query": "SELECT 1"}})
        self.assert_refused(legacy, "no 'stages'")

    def test_empty_sql_on_a_native_stage(self):
        self.assert_refused(stage(native="  "), "its SQL is empty")

    def test_refusals_never_leak_a_half_translation(self):
        result = describe_card(stage(**{"lib/type": "mbql.stage/mbql"}))
        self.assertEqual(result["sql"], "")

    def test_non_dict_input_is_a_programming_error_not_a_refusal(self):
        with self.assertRaises(TypeError):
            describe_card("2774")


class TestReferencedTables(unittest.TestCase):
    """Which tables a read-only DB login must be granted SELECT on.

    Error direction matters more than precision here: a surplus table costs one
    extra GRANT, a missing one silently breaks a dashboard. Every assertion
    below is written with that asymmetry in mind.
    """

    TABLE_NAMES = {2201: "tabStudent Applicant", 2359: "tabPurchase Order"}

    def test_a_native_card_names_its_tables_from_the_sql(self):
        tables, unresolved = referenced_tables(NATIVE_CARD)
        self.assertEqual(tables, {"tabStudent Applicant"})
        self.assertEqual(unresolved, [])

    def test_a_native_card_with_a_join_names_both(self):
        subject = stage(native="SELECT * FROM `tabStudent Applicant` a "
                               "JOIN `tabPurchase Order` b ON b.name = a.po")
        tables, _ = referenced_tables(subject)
        self.assertEqual(tables, {"tabStudent Applicant", "tabPurchase Order"})

    def test_a_gui_card_resolves_ids_through_the_table_list(self):
        gui = card(dataset_query={"lib/type": "mbql/query", "database": 3, "stages": [
            {"lib/type": "mbql.stage/mbql", "source-table": 2201}]})
        tables, unresolved = referenced_tables(gui, self.TABLE_NAMES)
        self.assertEqual(tables, {"tabStudent Applicant"})
        self.assertEqual(unresolved, [])

    def test_a_join_nested_inside_its_own_stages_is_still_found(self):
        """MBQL 5 puts a join's source inside the join's own stages. A walk of
        the documented nesting would miss it; the scan cannot."""
        gui = card(dataset_query={"lib/type": "mbql/query", "database": 3, "stages": [
            {"lib/type": "mbql.stage/mbql", "source-table": 2201,
             "joins": [{"lib/type": "mbql/join", "alias": "PO",
                        "stages": [{"source-table": 2359}]}]}]})
        tables, unresolved = referenced_tables(gui, self.TABLE_NAMES)
        self.assertEqual(tables, {"tabStudent Applicant", "tabPurchase Order"})
        self.assertEqual(unresolved, [])

    def test_an_unknown_table_id_is_reported_never_dropped(self):
        gui = card(dataset_query={"lib/type": "mbql/query", "database": 3, "stages": [
            {"lib/type": "mbql.stage/mbql", "source-table": 9999}]})
        tables, unresolved = referenced_tables(gui, self.TABLE_NAMES)
        self.assertEqual(tables, set())
        self.assertIn("table id 9999", unresolved[0])

    def test_a_card_built_on_another_card_says_so(self):
        gui = card(dataset_query={"lib/type": "mbql/query", "database": 3, "stages": [
            {"lib/type": "mbql.stage/mbql", "source-card": 1474}]})
        tables, unresolved = referenced_tables(gui, self.TABLE_NAMES)
        self.assertEqual(tables, set())
        self.assertIn("built on card 1474", unresolved[0])

    def test_native_sql_naming_no_frappe_table_is_reported(self):
        tables, unresolved = referenced_tables(stage(native="SELECT 1"))
        self.assertEqual(tables, set())
        self.assertIn("no `tab", unresolved[0])

    def test_a_query_with_no_source_at_all_is_reported(self):
        gui = card(dataset_query={"lib/type": "mbql/query", "database": 3, "stages": [{}]})
        _, unresolved = referenced_tables(gui, self.TABLE_NAMES)
        self.assertIn("no source-table", unresolved[0])

    def test_without_a_table_list_gui_cards_resolve_to_nothing_loudly(self):
        gui = card(dataset_query={"lib/type": "mbql/query", "database": 3, "stages": [
            {"lib/type": "mbql.stage/mbql", "source-table": 2201}]})
        tables, unresolved = referenced_tables(gui)
        self.assertEqual(tables, set())
        self.assertEqual(len(unresolved), 1)

    def test_non_dict_input_is_a_programming_error(self):
        with self.assertRaises(TypeError):
            referenced_tables("2774")


if __name__ == "__main__":
    unittest.main()
