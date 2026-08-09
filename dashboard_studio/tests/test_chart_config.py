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

    def test_EMPTY_series_settings_still_builds_from_the_card_display(self):
        """Superseded by the display mapping (Fix 1): the chart TYPE alone is
        Metabase's own statement and picking it is the win — without this
        chart there is no chart at all, and somebody clicks it by hand 1700
        times. Series inherit the card display; no labels are invented."""
        config, chart_type, reason = chart_config_from_card(
            {"display": "line", "series_settings": {}}, ops())
        self.assertIsNone(reason)
        self.assertEqual(chart_type, "Line")
        self.assertEqual([s["type"] for s in config["y_axis"]["series"]],
                         ["line", "line"])
        self.assertNotIn("name", config["y_axis"]["series"][0])

    def test_settings_matching_NOTHING_abandon_the_chart(self):
        """The 34 corpus cards keyed by custom names (`teacher_1`). Building
        the chart anyway would silently drop every setting somebody stored —
        a chart that renders and is not the one they configured."""
        card = {"display": "line",
                "series_settings": {"teacher_1": {"display": "bar"},
                                    "teacher_2": {"title": "T2"}}}
        config, chart_type, reason = chart_config_from_card(card, ops())
        self.assertIsNone(config)
        self.assertIn("names this query does not produce", reason)
        self.assertIn("teacher_1", reason)

    def test_an_untranslated_card_display_falls_back(self):
        """`gauge`, `object`, `pivot`, `combo`, `area`, `map` — the ones the
        corpus scan counted and Fix 1 deliberately left unmapped — plus blank
        and whatever Metabase adds next."""
        for display in ("area", "combo", "gauge", "object", "pivot", "map", ""):
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


class TestTheUnchartableDatePartDetector(unittest.TestCase):
    """`date_part_grouping` — the corpus scan's half of the month-of-year fix.

    Mirrors `datePartGrouping` in studio_core.js. Both must agree, or the scan
    lists reports the page does not offer the fix for, and vice versa.
    """

    def summarize(self, dimensions):
        return {"type": "summarize", "measures": [COUNT], "dimensions": dimensions}

    def mutate(self, name, expression):
        return {"type": "mutate", "new_name": name,
                "expression": {"type": "expression", "expression": expression}}

    def test_a_month_grouping_is_found(self):
        from dashboard_studio.integrations.metabase.chart_config import date_part_grouping
        found = date_part_grouping([
            self.mutate("month_of_d", "month(d)"),
            self.summarize([{"column_name": "month_of_d", "data_type": "Integer"}])])
        self.assertEqual(found, {"part": "month", "dimension": "month_of_d",
                                 "column": "d"})

    def test_quarter_and_day_too(self):
        from dashboard_studio.integrations.metabase.chart_config import date_part_grouping
        for part in ("quarter", "day"):
            with self.subTest(part):
                found = date_part_grouping([
                    self.mutate(f"{part}_of_d", f"{part}(d)"),
                    self.summarize([{"column_name": f"{part}_of_d"}])])
                self.assertEqual(found["part"], part)

    def test_YEAR_is_never_reported(self):
        """Regrouping a year by year is a no-op, and offering it would loop.
        ADR-024 means a grouped YEAR is a granularity and produces no mutate at
        all — this asserts the exclusion directly rather than relying on that."""
        from dashboard_studio.integrations.metabase.chart_config import date_part_grouping
        self.assertIsNone(date_part_grouping([
            self.mutate("year_of_d", "year(d)"),
            self.summarize([{"column_name": "year_of_d"}])]))

    def test_a_mutate_that_is_not_GROUPED_BY_is_not_the_X_axis(self):
        """A date part computed but not grouped by is not the chart's axis, so
        rewriting the query would change a column nothing charts."""
        from dashboard_studio.integrations.metabase.chart_config import date_part_grouping
        self.assertIsNone(date_part_grouping([
            self.mutate("month_of_d", "month(d)"), self.summarize([])]))
        self.assertIsNone(date_part_grouping([
            self.mutate("month_of_d", "month(d)"),
            self.summarize([{"column_name": "something_else"}])]))

    def test_an_ARITHMETIC_mutate_is_not_a_date_part(self):
        from dashboard_studio.integrations.metabase.chart_config import date_part_grouping
        self.assertIsNone(date_part_grouping([
            self.mutate("x", "(avg_of_a + avg_of_b) / 2"),
            self.summarize([{"column_name": "x"}])]))

    def test_nothing_at_all(self):
        from dashboard_studio.integrations.metabase.chart_config import date_part_grouping
        for operations in ([], None, [{"type": "source"}]):
            self.assertIsNone(date_part_grouping(operations))


class TestTheSimpleChartFamilies(unittest.TestCase):
    """scalar/smartscalar -> Number, pie -> Donut, funnel -> Funnel,
    table -> Table, row -> Row. Every requirement is `chart.ts`'s own
    validation at v3.12.2, so a config this refuses is one Insights would
    reject on open — and the config shapes are asserted IN FULL, because a
    chart that renders and says something else is the failure mode here.
    """

    def build(self, display, measures=(COUNT,), dimensions=()):
        return chart_config_from_card({"display": display},
                                      ops(measures=measures,
                                          dimensions=dimensions))

    def test_a_scalar_becomes_a_Number_in_full(self):
        config, chart_type, reason = self.build("scalar", measures=(COUNT, AVG))
        self.assertIsNone(reason)
        self.assertEqual(chart_type, "Number")
        self.assertEqual(config, {"number_columns": [COUNT, AVG],
                                  "number_column_options": [{}, {}],
                                  "comparison": False, "sparkline": False})

    def test_smartscalar_is_a_Number_too(self):
        self.assertEqual(self.build("smartscalar")[1], "Number")

    def test_a_GROUPED_scalar_falls_back_rather_than_dropping_the_grouping(self):
        """`addNumberChartOperation` summarizes by date_column alone, so a
        Number chart of a grouped query answers a smaller question."""
        config, _, reason = self.build("scalar", dimensions=(YEAR,))
        self.assertIsNone(config)
        self.assertIn("would drop the grouping", reason)

    def test_a_pie_becomes_a_Donut_in_full(self):
        config, chart_type, reason = self.build("pie", measures=(COUNT,),
                                                dimensions=(YEAR,))
        self.assertIsNone(reason)
        self.assertEqual(chart_type, "Donut")
        self.assertEqual(config, {"label_column": YEAR, "value_column": COUNT})

    def test_a_funnel_is_the_same_shape_named_Funnel(self):
        config, chart_type, reason = self.build("funnel", measures=(COUNT,),
                                                dimensions=(YEAR,))
        self.assertIsNone(reason)
        self.assertEqual(chart_type, "Funnel")
        self.assertEqual(config, {"label_column": YEAR, "value_column": COUNT})

    def test_a_pie_with_two_measures_falls_back(self):
        """`DonutChartConfig` has exactly one value_column slot; picking one of
        two measures would chart half the question."""
        config, _, reason = self.build("pie", measures=(COUNT, AVG),
                                       dimensions=(YEAR,))
        self.assertIsNone(config)
        self.assertIn("exactly one label column and one value", reason)

    def test_a_table_becomes_a_Table_in_full(self):
        config, chart_type, reason = self.build("table", measures=(COUNT, AVG),
                                                dimensions=(YEAR,))
        self.assertIsNone(reason)
        self.assertEqual(chart_type, "Table")
        self.assertEqual(config, {"rows": [YEAR], "columns": [],
                                  "values": [COUNT, AVG]})

    def test_an_UNGROUPED_table_falls_back(self):
        """`chart.ts` demands non-empty rows — "Rows are required" — so this
        config would fail validation the moment the chart opened."""
        config, _, reason = self.build("table")
        self.assertIsNone(config)
        self.assertIn("groups by nothing", reason)

    def test_a_row_card_is_a_Row_chart_with_UNTYPED_series(self):
        """Metabase hides the per-series display control for row cards (its
        series.ts admits only line/area/bar/combo), so a stored display there
        is a leftover Metabase itself does not render — and Insights' Row
        renderer supplies the series type. Writing one would be inventing."""
        config, chart_type, reason = chart_config_from_card(
            {"display": "row",
             "series_settings": {"count": {"display": "bar", "title": "N"}}},
            ops(measures=(COUNT,), dimensions=(YEAR,)))
        self.assertIsNone(reason)
        self.assertEqual(chart_type, "Row")
        self.assertNotIn("type", config["y_axis"]["series"][0])
        # …but the LABEL still applies: Metabase renders titles on row cards.
        self.assertEqual(config["y_axis"]["series"][0]["name"], "N")

    def test_series_settings_do_not_reach_a_simple_chart(self):
        """They describe axis series — type and axis side — and a Number has
        neither, so entries here are neither applied nor a reason to refuse."""
        config, chart_type, reason = chart_config_from_card(
            {"display": "scalar",
             "series_settings": {"count": {"display": "bar"}}},
            ops(measures=(COUNT,), dimensions=()))
        self.assertIsNone(reason)
        self.assertEqual(chart_type, "Number")
        self.assertNotIn("series", repr(config))
