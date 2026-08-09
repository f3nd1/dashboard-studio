"""A Metabase card's chart settings -> an Insights chart config.

The failure that matters here is not a crash. It is a chart that renders, reads
correctly, and puts the line on the wrong series — so the tests are mostly about
what does NOT get built, and the built config is asserted IN FULL.

The QIPI fixture is the real captured card (id 2424), including the detail that
makes it worth translating: the card-level display is `line`, and only `count`
carries an override to `bar`.
"""

import unittest

from dashboard_studio.integrations.metabase.chart_config import chart_config_from_card

QIPI_CARD = {
    "card_id": 2424,
    "display": "line",
    "series_settings": {
        "avg": {"color": "#E75454", "title": "Average of QIPI"},
        "count": {"display": "bar", "title": "Count of QA"},
    },
}
COUNT = {"measure_name": "count", "column_name": "count",
         "data_type": "Integer", "aggregation": "count"}
AVG = {"measure_name": "avg_of_qipi", "column_name": "qipi",
       "data_type": "Decimal", "aggregation": "avg"}
YEAR = {"dimension_name": "custom_proposed_date",
        "column_name": "custom_proposed_date",
        "data_type": "Date", "granularity": "year"}


def ops(measures=(COUNT, AVG), dimensions=(YEAR,)):
    return [{"type": "source", "table": {"table_name": "tabQuality Action"}},
            {"type": "summarize", "measures": list(measures),
             "dimensions": list(dimensions)}]


class TestTheRealQipiCard(unittest.TestCase):
    def test_it_converts_in_full(self):
        """Asserted whole. "The right keys are present" proves nothing when the
        failure mode is a chart that renders and says something else."""
        config, chart_type, reason = chart_config_from_card(QIPI_CARD, ops())
        self.assertIsNone(reason)
        self.assertEqual(chart_type, "Line")
        self.assertEqual(config, {
            "x_axis": {"dimension": YEAR},
            "y_axis": {"series": [
                {"measure": COUNT, "type": "bar", "align": "Left",
                 "name": "Count of QA"},
                {"measure": AVG, "type": "line", "align": "Left",
                 "name": "Average of QIPI"},
            ]},
        })

    def test_the_series_WITHOUT_a_display_inherits_the_cards(self):
        """`avg` carries only a colour and a title, so its type comes from the
        card's own `display: "line"`. Getting this backwards is the whole
        feature failing quietly."""
        config, _, _ = chart_config_from_card(QIPI_CARD, ops())
        types = {s["measure"]["measure_name"]: s["type"]
                 for s in config["y_axis"]["series"]}
        self.assertEqual(types, {"count": "bar", "avg_of_qipi": "line"})

    def test_every_series_goes_on_the_LEFT_axis(self):
        """Metabase stores `axis` only when overridden, and this card stores
        none — its two axes are Metabase's render-time Auto split. A Right here
        would be this converter's invention."""
        config, _, _ = chart_config_from_card(QIPI_CARD, ops())
        self.assertEqual([s["align"] for s in config["y_axis"]["series"]],
                         ["Left", "Left"])

    def test_the_measure_is_the_QUERYS_own(self):
        """Lifted from the summarize rather than rebuilt. A rebuilt measure that
        disagreed would chart a column the query does not produce."""
        config, _, _ = chart_config_from_card(QIPI_CARD, ops())
        self.assertEqual(config["y_axis"]["series"][1]["measure"], AVG)


class TestWhatIsNotBuilt(unittest.TestCase):
    """Every one of these falls back to Insights' default with a reason."""

    def assert_refused(self, card, operations, fragment):
        config, chart_type, reason = chart_config_from_card(card, operations)
        self.assertIsNone(config)
        self.assertIsNone(chart_type)
        self.assertIn(fragment, reason)

    def test_two_measures_sharing_an_aggregation_are_ambiguous(self):
        """Metabase names a series by its FUNCTION, so `AVG(a)` and `AVG(b)` are
        `avg` and `avg_2` there and `avg_of_a`/`avg_of_b` here. Nothing lines
        them up, and picking one would put the label on the wrong line."""
        second = dict(AVG, measure_name="avg_of_other", column_name="other")
        self.assert_refused(QIPI_CARD, ops(measures=(AVG, second)),
                            "which of them its display setting belongs to")

    def test_no_series_settings_at_all_changes_nothing(self):
        """Nothing to copy is not a chart to build — Insights' defaults already
        do this, and creating a chart to say so would add a record for nothing."""
        self.assert_refused({"display": "line", "series_settings": {}}, ops(),
                            "recorded no per-series display settings")

    def test_an_untranslated_card_display_falls_back(self):
        """`area`, `combo`, `scalar`, and whatever Metabase adds next. Insights'
        Series.type is 'line' | 'bar' and nothing else."""
        for display in ("area", "combo", "scalar", "table", ""):
            with self.subTest(display):
                self.assert_refused(dict(QIPI_CARD, display=display), ops(),
                                    "does not translate into a chart type")

    def test_an_untranslated_SERIES_display_falls_back(self):
        card = dict(QIPI_CARD, series_settings={"count": {"display": "area"}})
        self.assert_refused(card, ops(), "drew one series as 'area'")

    def test_two_groupings_have_no_single_X_axis(self):
        """A second dimension is a colour breakdown, and deciding which is which
        changes what the chart says."""
        self.assert_refused(QIPI_CARD, ops(dimensions=(YEAR, dict(YEAR, column_name="status"))),
                            "groups by 2 columns")

    def test_no_grouping_at_all(self):
        self.assert_refused(QIPI_CARD, ops(dimensions=()), "groups by 0 columns")

    def test_no_measures(self):
        self.assert_refused(QIPI_CARD, ops(measures=()), "no measures")

    def test_no_summarize_in_the_operations(self):
        self.assert_refused(QIPI_CARD, [{"type": "source"}], "no measures")

    def test_junk_instead_of_a_card(self):
        for card in (None, "", [], "not a dict", {}):
            with self.subTest(repr(card)):
                config, _, reason = chart_config_from_card(card, ops())
                self.assertIsNone(config)
                self.assertTrue(reason)


class TestItReadsMetabasesOwnSpelling(unittest.TestCase):
    def test_the_key_match_is_case_and_space_insensitive(self):
        card = dict(QIPI_CARD, series_settings={
            "AVG": {"title": "Average of QIPI"},
            " Count ": {"display": "Bar", "title": "Count of QA"}})
        config, _, reason = chart_config_from_card(card, ops())
        self.assertIsNone(reason)
        self.assertEqual([s["type"] for s in config["y_axis"]["series"]],
                         ["bar", "line"])

    def test_a_key_naming_no_measure_is_simply_not_applied(self):
        """`sum` on a query with no SUM. It names nothing, so it does nothing —
        and the series it cannot describe keeps the card's own display."""
        card = dict(QIPI_CARD, series_settings=dict(
            QIPI_CARD["series_settings"], sum={"display": "bar"}))
        config, _, reason = chart_config_from_card(card, ops())
        self.assertIsNone(reason)
        self.assertEqual(len(config["y_axis"]["series"]), 2)

    def test_a_series_with_no_title_gets_no_name_key(self):
        """Insights then falls back to the measure name. An empty string would
        be a label, and a blank one."""
        card = dict(QIPI_CARD, series_settings={"count": {"display": "bar"},
                                                "avg": {"title": "  "}})
        config, _, _ = chart_config_from_card(card, ops())
        self.assertNotIn("name", config["y_axis"]["series"][0])
        self.assertNotIn("name", config["y_axis"]["series"][1])


if __name__ == "__main__":
    unittest.main()
