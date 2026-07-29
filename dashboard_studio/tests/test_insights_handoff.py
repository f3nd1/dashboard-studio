"""Tests for the Insights handoff — creating a native Query from pasted SQL.

Three things carry weight here and each is asserted from both directions:

1. the refusals name what is wrong (missing Insights role above all, which is
   the one a real Dashboard Studio Editor is most likely to hit);
2. Studio never files a statement that writes;
3. the same SQL twice reuses the record instead of piling up duplicates.

MOCK-BASED for Frappe — no live Bench. The fake models Insights **v3** as
confirmed live on the site: a query belongs to a Workbook and carries its SQL
inside an `operations` JSON array, and a chart's axes live in a `config` JSON.
The fixtures below are copied from real records, not invented — see REAL_CONFIG.
"""

import sys
import types
import unittest

SQL = "SELECT `agent`, COUNT(*) AS `count` FROM `tabStudent Applicant` GROUP BY `agent`"
ANALYSIS = {
    "supported": True,
    "doctypes": ["Student Applicant"],
    "group_by": ["agent"],
    "aggregations": [{"function": "COUNT", "argument": "*"}],
}


class _PermissionError(Exception):
    pass


class _ValidationError(Exception):
    pass


_PREFIX = {"Insights Query v3": "s39rc7j64", "Insights Chart v3": "tt51l7mma"}


class _FakeDoc:
    def __init__(self, data, store, doctype=None):
        object.__setattr__(self, "_data", dict(data))
        object.__setattr__(self, "_store", store)
        object.__setattr__(self, "_doctype", doctype or data.get("doctype"))

    def __getattr__(self, key):
        try:
            return self._data[key]
        except KeyError:
            raise AttributeError(key)

    # Assignment has to land in _data, not on the Python object: without this a
    # `doc.chart_type = "Bar"` would set an attribute the store never sees and
    # every write assertion would pass while writing nothing.
    def __setattr__(self, key, value):
        self._data[key] = value

    def get(self, key, default=None):
        return self._data.get(key, default)

    def insert(self):
        doctype = self._data["doctype"]
        table = self._store.setdefault(doctype, {})
        # Real v3 names, so nothing can quietly depend on the v2 "QRY-" prefix:
        # a Workbook is autoincrement (so "1", "2"), a query and a chart get a
        # random-looking hash ("s39rc7j648"). Named here, never by title, because
        # that is what forces the reuse key to be the SQL.
        self._data["name"] = (str(len(table) + 1) if doctype == "Insights Workbook"
                              else f"{_PREFIX.get(doctype, 'x')}{len(table) + 1}k7a2d")
        table[self._data["name"]] = dict(self._data)
        return self

    def save(self):
        self._store.setdefault(self._doctype, {})[self._data["name"]] = dict(self._data)
        return self


def _make_fake_frappe(store, roles, doctypes=("Insights Query v3",), sources=("Site DB",)):
    frappe = types.ModuleType("frappe")
    frappe.PermissionError = _PermissionError
    frappe.ValidationError = _ValidationError
    frappe._roles = set(roles)
    frappe._doctypes = set(doctypes)
    frappe._sources = set(sources)           # Insights Data Source v3
    frappe._v2_sources = {"Site DB", "Query Store"}   # the v2 table, still there

    def only_for(needed, message=None):
        if isinstance(needed, str):
            needed = (needed,)
        if not (set(needed) & frappe._roles):
            raise _PermissionError(f"need one of {needed}")

    def whitelist(*a, **k):
        def deco(fn):
            return fn

        return deco

    def get_all(doctype, filters=None, fields=None, limit=None, **kwargs):
        rows = list(store.get(doctype, {}).values())
        for key, value in (filters or {}).items():
            rows = [r for r in rows if r.get(key) == value]
        return [dict(r) for r in rows][: limit or None]

    def exists(doctype, name):
        if doctype == "DocType":
            return name in frappe._doctypes
        # Both generations of the data-source table exist on a v3 site and both
        # hold a row called "Site DB". Modelled as two separate sets so a guard
        # reading the wrong one is a test failure rather than a coincidence.
        if doctype == "Insights Data Source v3":
            return name in frappe._sources
        if doctype == "Insights Data Source":
            return name in frappe._v2_sources
        return name in store.get(doctype, {})

    frappe.only_for = only_for
    frappe.whitelist = whitelist
    frappe.get_all = get_all
    class _DoesNotExistError(Exception):
        pass

    def get_doc(doctype, name=None):
        # Two signatures, like the real thing: a payload dict to insert, or
        # (doctype, name) to fetch. The fake modelled only the first, so the
        # first call that read a record back blew up rather than being wrong.
        if isinstance(doctype, dict):
            return _FakeDoc(doctype, store)
        data = store.get(doctype, {}).get(name)
        if data is None:
            raise _DoesNotExistError(f"{doctype} {name} not found")
        return _FakeDoc(data, store, doctype)

    frappe.DoesNotExistError = _DoesNotExistError
    frappe.get_doc = get_doc
    frappe.as_json = lambda value: __import__("json").dumps(value)
    frappe.get_roles = lambda: list(frappe._roles)
    frappe.parse_json = __import__("json").loads
    frappe.throw = lambda msg: (_ for _ in ()).throw(_ValidationError(msg))
    frappe.db = types.SimpleNamespace(exists=exists)
    return frappe


class _Base(unittest.TestCase):
    roles = {"Dashboard Studio Editor", "Insights User"}
    doctypes = ("Insights Query v3",)
    sources = ("Site DB",)

    def setUp(self):
        self._saved = {
            k: v for k, v in sys.modules.items()
            if k == "frappe" or k.startswith("dashboard_studio.")
        }
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        self.store = {}
        self.frappe = _make_fake_frappe(self.store, self.roles, self.doctypes, self.sources)
        sys.modules["frappe"] = self.frappe
        import dashboard_studio.api.insights as insights

        self.api = insights

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    def refusal(self, *args, **kwargs):
        with self.assertRaises(_ValidationError) as caught:
            self.api.create_insights_query(*args, **kwargs)
        return str(caught.exception)

    def queries(self):
        return list(self.store.get("Insights Query v3", {}).values())

    def stored_sql(self, index=0):
        """The SQL as v3 really holds it: inside the operations array."""
        return self.api.operation_sql(
            __import__("json").loads(self.queries()[index]["operations"]))

    def workbooks(self):
        return list(self.store.get("Insights Workbook", {}).values())


class TestCreate(_Base):
    def test_creates_a_native_query_with_a_real_v3_operations_array(self):
        result = self.api.create_insights_query(SQL, analysis=ANALYSIS)
        row = self.queries()[0]
        self.assertEqual(row["is_native_query"], 1)
        self.assertEqual(row["use_live_connection"], 1)
        self.assertEqual(row["title"], "Count of Student Applicant by agent")
        self.assertEqual(
            __import__("json").loads(row["operations"]),
            [{"type": "sql", "raw_sql": SQL, "data_source": "Site DB"}],
            "the SQL must be inside operations — v3 has no sql field",
        )
        self.assertFalse(result["reused"])

    def test_the_query_belongs_to_a_workbook_created_on_first_use(self):
        """workbook is a REQD Link in v3 — there is no query without one."""
        result = self.api.create_insights_query(SQL)
        self.assertEqual(len(self.workbooks()), 1)
        self.assertEqual(self.workbooks()[0]["title"], "Dashboard Studio")
        self.assertEqual(self.queries()[0]["workbook"], result["workbook"])

    def test_a_second_query_reuses_the_same_workbook(self):
        self.api.create_insights_query(SQL)
        self.api.create_insights_query(SQL.replace("agent", "nationality"))
        self.assertEqual(len(self.workbooks()), 1, "a workbook per query litters the sidebar")
        self.assertEqual(len({q["workbook"] for q in self.queries()}), 1)

    def test_the_insights_url_carries_the_workbook_as_well_as_the_query(self):
        """The v3 route needs both; the v2 path loads an empty shell."""
        result = self.api.create_insights_query(SQL, analysis=ANALYSIS)
        self.assertEqual(
            result["insights_url"],
            f"/insights/workbook/{result['workbook']}/query/{result['name']}",
        )
        self.assertEqual(result["desk_url"], "/app/insights-query-v3/" + result["name"])

    def test_an_explicit_title_wins_over_the_derived_one(self):
        self.api.create_insights_query(SQL, title="  Agent intake  ", analysis=ANALYSIS)
        self.assertEqual(self.queries()[0]["title"], "Agent intake")

    def test_analysis_may_arrive_as_a_json_string(self):
        """frappe.call serialises dict args — the endpoint must cope."""
        import json

        self.api.create_insights_query(SQL, analysis=json.dumps(ANALYSIS))
        self.assertEqual(self.queries()[0]["title"], "Count of Student Applicant by agent")

    def test_a_trailing_semicolon_is_stripped_not_refused(self):
        self.api.create_insights_query(SQL + " ;")
        self.assertEqual(self.stored_sql(), SQL)

    # ---------------------------------------------------------------- reuse
    def test_the_same_sql_twice_reuses_the_record(self):
        first = self.api.create_insights_query(SQL, analysis=ANALYSIS)
        second = self.api.create_insights_query(SQL, analysis=ANALYSIS)
        self.assertEqual(len(self.queries()), 1)
        self.assertEqual(first["name"], second["name"])
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"], "a second click must say it reused, not pretend it made one")

    def test_different_sql_makes_a_second_record(self):
        self.api.create_insights_query(SQL, analysis=ANALYSIS)
        self.api.create_insights_query(SQL.replace("agent", "nationality"))
        self.assertEqual(len(self.queries()), 2)


class TestRefusals(_Base):
    def test_write_only_statements_are_refused_by_name(self):
        for statement in (
            "DELETE FROM `tabStudent Applicant`",
            "UPDATE `tabStudent Applicant` SET agent = 'x'",
            "DROP TABLE `tabStudent Applicant`",
            "INSERT INTO `tabStudent Applicant` (name) VALUES ('x')",
        ):
            message = self.refusal(statement)
            self.assertIn("will not file a statement that writes", message)
        self.assertEqual(self.queries(), [], "a refused statement was still written")

    def test_a_second_statement_is_refused(self):
        message = self.refusal(SQL + "; DELETE FROM `tabUser`")
        self.assertIn("more than one statement", message)
        self.assertEqual(self.queries(), [])

    def test_a_with_query_is_allowed(self):
        self.api.create_insights_query("WITH x AS (SELECT 1) SELECT * FROM x")
        self.assertEqual(len(self.queries()), 1)

    def test_empty_sql_is_refused(self):
        self.assertIn("no SQL to send", self.refusal("   "))

    def test_missing_insights_role_names_the_role(self):
        """The check the user asked for: not a raw permission error."""
        self.frappe._roles = {"Dashboard Studio Editor"}
        message = self.refusal(SQL)
        self.assertIn("Insights User", message)
        self.assertIn("Insights Admin", message)
        self.assertIn("does not get it automatically", message)
        self.assertEqual(self.queries(), [])

    def test_insights_admin_alone_is_enough(self):
        self.frappe._roles = {"Dashboard Studio Editor", "Insights Admin"}
        self.api.create_insights_query(SQL)
        self.assertEqual(len(self.queries()), 1)

    def test_insights_not_installed_names_the_version_problem(self):
        self.frappe._doctypes = set()
        message = self.refusal(SQL)
        self.assertIn("not installed", message)
        self.assertIn("Insights Query v3", message, "v3 must be named as what is missing")

    def test_a_v2_only_site_is_refused_rather_than_written_to(self):
        """The unsound guard: v3 ships the v2 DocTypes too, so presence proves
        nothing. Testing for the v2 name passed on v3 and wrote an orphan."""
        self.frappe._doctypes = {"Insights Query", "Insights Chart"}
        message = self.refusal(SQL)
        self.assertIn("older than v3", message)
        self.assertEqual(self.queries(), [])
        self.assertEqual(self.store.get("Insights Query", {}), {},
                         "it fell back to writing a v2 record")

    def test_a_missing_site_db_source_is_named(self):
        self.frappe._sources = set()
        self.assertIn("Site DB", self.refusal(SQL))
        self.assertEqual(self.queries(), [])

    def test_the_site_db_check_reads_the_v3_table_not_the_v2_one(self):
        """Both tables hold a row called "Site DB", so reading the v2 one passed
        by coincidence. Here only v3's is missing — and v3 is the table a query's
        data_source is resolved against, so this has to refuse."""
        self.frappe._sources = set()
        self.frappe._v2_sources = {"Site DB", "Query Store"}
        self.assertIn("Site DB", self.refusal(SQL))
        self.assertEqual(self.queries(), [])

    def test_deleting_the_v2_records_does_not_break_creating_a_query(self):
        """What happens after the v2 cleanup: the v2 tables are empty, v3 is
        untouched. Reading the v2 table here would refuse every create and blame
        a data source that was fine."""
        self.frappe._v2_sources = set()
        self.api.create_insights_query(SQL, analysis=ANALYSIS)
        self.assertEqual(len(self.queries()), 1)

    def test_a_non_editor_is_refused_before_anything_else(self):
        """DS write role first, and still a 403 rather than a message."""
        self.frappe._roles = {"Dashboard Studio Viewer", "Insights User"}
        with self.assertRaises(_PermissionError):
            self.api.create_insights_query(SQL)
        self.assertEqual(self.queries(), [])


class TestTitle(_Base):
    """query_title degrades on purpose — the queries most worth sending to
    Insights are the ones the DS parser could not translate."""

    def test_full_analysis(self):
        self.assertEqual(
            self.api.query_title(ANALYSIS), "Count of Student Applicant by agent"
        )

    def test_one_doctype_no_group_by(self):
        self.assertEqual(
            self.api.query_title({"doctypes": ["Student Applicant"]}), "Student Applicant query"
        )

    def test_a_join_names_both_tables(self):
        self.assertEqual(
            self.api.query_title({"doctypes": ["Employee", "Student Applicant"]}),
            "Employee + Student Applicant query",
        )

    def test_nothing_parsed_still_gives_a_title(self):
        self.assertEqual(self.api.query_title(None), "Imported SQL query")
        self.assertEqual(self.api.query_title({"supported": False}), "Imported SQL query")


if __name__ == "__main__":
    unittest.main()


# THE REAL v3 CHART CONFIG, read back from chart tt51l7mma3 on the live site
# (chart_type "Line", query tt49ok7a2d). Every assertion below measures against
# this rather than against a shape anybody reasoned their way to.
REAL_CONFIG = {
    "x_axis": {
        "dimension": {"column_name": "academic_year", "data_type": "String",
                      "dimension_name": "academic_year"}
    },
    "y_axis": {
        "series": [{
            "measure": {"aggregation": "count", "column_name": "count",
                        "data_type": "Integer", "measure_name": "count"},
            "type": "line",
        }]
    },
}

# A Metabase card's result_metadata, as describe_card returns it. This is the
# only source of per-column types on v3: nothing persists a query's result, so
# there is nothing to read back after the person presses Run.
CARD_COLUMNS = [
    {"name": "academic_year", "display_name": "Academic Year", "base_type": "type/Text"},
    {"name": "count", "display_name": "Count", "base_type": "type/BigInteger"},
]

QUERY = "s39rc7j648"


def _chart_store(chart_config=None):
    store = {
        "Insights Workbook": {"2": {"name": "2", "title": "Dashboard Studio"}},
        "Insights Query v3": {QUERY: {"name": QUERY, "workbook": "2", "title": "Q"}},
    }
    if chart_config is not None:
        store["Insights Chart v3"] = {
            "tt51l7mma3": {"name": "tt51l7mma3", "query": QUERY, "workbook": "2",
                           "chart_type": "", "config": chart_config}
        }
    return store


class _ChartBase(_Base):
    existing_chart = None      # None -> the query has no chart yet, as in real v3

    def setUp(self):
        super().setUp()
        self.store.update(_chart_store(self.existing_chart))

    def charts(self):
        return list(self.store.get("Insights Chart v3", {}).values())

    def config(self, index=0):
        return __import__("json").loads(self.charts()[index]["config"])

    def apply(self, **kwargs):
        kwargs.setdefault("columns", CARD_COLUMNS)
        return self.api.apply_insights_chart(QUERY, **kwargs)

    def refused(self, **kwargs):
        with self.assertRaises(_ValidationError) as caught:
            self.apply(**kwargs)
        return str(caught.exception)


class TestApplyChart(_ChartBase):
    def test_writes_exactly_the_real_config_shape(self):
        result = self.apply(chart_type="line")
        self.assertEqual((result["x_axis"], result["y_axis"]), ("academic_year", "count"))
        expected = __import__("copy").deepcopy(REAL_CONFIG)
        # The one key that differs from the real record on purpose: that chart
        # was a GUI summary, where "count" is the aggregation. A native query has
        # already aggregated, so summing an already-grouped column is identity
        # while counting it would plot 1 per group.
        expected["y_axis"]["series"][0]["measure"]["aggregation"] = "sum"
        self.assertEqual(self.config(), expected)
        self.assertEqual(self.charts()[0]["chart_type"], "Line")

    def test_creates_the_chart_because_v3_does_not(self):
        """v2 made one in after_insert; v3 makes none, so this has to."""
        self.assertEqual(self.charts(), [])
        result = self.apply()
        self.assertEqual(len(self.charts()), 1)
        self.assertEqual(self.charts()[0]["query"], QUERY)
        self.assertEqual(self.charts()[0]["workbook"], "2", "a chart needs its workbook")
        self.assertEqual(result["chart"], self.charts()[0]["name"])

    def test_a_second_call_updates_that_chart_instead_of_adding_another(self):
        self.apply()
        first = self.charts()[0]["name"]
        self.apply(chart_type="line")
        self.assertEqual(len(self.charts()), 1, "a second chart would compete with the first")
        self.assertEqual(self.charts()[0]["name"], first)
        self.assertEqual(self.charts()[0]["chart_type"], "Line")

    def test_an_existing_chart_is_updated_not_duplicated(self):
        self.existing_chart = "{}"
        self.setUp()
        self.apply()
        self.assertEqual(len(self.charts()), 1)
        self.assertEqual(self.charts()[0]["name"], "tt51l7mma3")

    def test_bar_gets_its_own_series_type(self):
        self.apply(chart_type="bar")
        self.assertEqual(self.config()["y_axis"]["series"][0]["type"], "bar")
        self.assertEqual(self.charts()[0]["chart_type"], "Bar")

    def test_an_explicit_pair_is_honoured(self):
        result = self.apply(x_axis="academic_year", y_axis="count")
        self.assertEqual((result["x_axis"], result["y_axis"]), ("academic_year", "count"))

    def test_columns_may_arrive_as_a_json_string(self):
        import json

        self.apply(columns=json.dumps(CARD_COLUMNS))
        self.assertEqual(self.config()["x_axis"]["dimension"]["column_name"], "academic_year")

    def test_the_url_it_returns_is_the_v3_route(self):
        result = self.apply()
        self.assertEqual(result["insights_url"], f"/insights/workbook/2/query/{QUERY}")


class TestApplyChartRefusals(_ChartBase):
    def test_without_columns_it_refuses_rather_than_guessing_a_data_type(self):
        """The v3 gap: no persisted result, so no types unless a card supplied
        them. v3 accepts any config and then draws nothing, so a guess is worse
        here than it was under v2."""
        message = self.refused(columns=None)
        self.assertIn("no column types", message)
        self.assertIn("Set them in Insights", message)
        self.assertEqual(self.charts(), [], "it wrote a chart despite refusing")

    def test_a_string_y_axis_is_refused_by_name(self):
        message = self.refused(y_axis="academic_year")
        self.assertIn("academic_year", message)
        self.assertIn("String", message)
        self.assertEqual(self.charts(), [])

    def test_a_numeric_x_axis_is_refused_because_a_dimension_cannot_be_one(self):
        message = self.refused(x_axis="count")
        self.assertIn("'count' is a Integer", message)
        self.assertIn("text, dates or times", message)

    def test_no_numeric_column_at_all_is_refused_and_lists_the_types(self):
        message = self.refused(columns=[
            {"name": "a", "base_type": "type/Text"},
            {"name": "b", "base_type": "type/DateTime"}])
        self.assertIn("nothing to", message)
        self.assertIn("a (String)", message)
        self.assertIn("b (Datetime)", message)

    def test_an_axis_the_query_never_returns_is_refused_with_the_real_names(self):
        message = self.refused(x_axis="agent")
        self.assertIn("'agent' is not a column", message)
        self.assertIn("academic_year", message)

    def test_a_non_axis_chart_type_is_refused_by_name(self):
        message = self.refused(chart_type="Donut")
        self.assertIn("Donut", message)
        self.assertIn("Bar, Line", message)

    def test_no_dimension_column_leaves_nothing_for_the_x_axis(self):
        message = self.refused(columns=[{"name": "count", "base_type": "type/BigInteger"}])
        self.assertIn("no column Insights can use as an X axis", message)

    def test_missing_insights_role_still_refuses_first(self):
        self.frappe._roles = {"Dashboard Studio Editor"}
        self.assertIn("Insights User", self.refused())


class TestAxisColumns(_Base):
    """Metabase base_type -> v3 data_type, Frappe-free."""

    def types(self, *base_types):
        return [c["data_type"] for c in self.api.axis_columns(
            [{"name": f"c{i}", "base_type": b} for i, b in enumerate(base_types)])]

    def test_the_families_that_matter(self):
        self.assertEqual(
            self.types("type/Text", "type/BigInteger", "type/Float", "type/DateTime",
                       "type/Date", "type/Time"),
            ["String", "Integer", "Decimal", "Datetime", "Date", "Time"])

    def test_an_unknown_base_type_degrades_to_string(self):
        """Safe direction: String is refused as a measure, allowed as a dimension."""
        self.assertEqual(self.types("type/Boolean", "type/MongoBSONID", ""),
                         ["String", "String", "String"])

    def test_junk_is_skipped_rather_than_crashed_on(self):
        self.assertEqual(self.api.axis_columns(None), [])
        self.assertEqual(self.api.axis_columns(["not a column", {"name": ""}, {}]), [])


class TestPickAxes(_Base):
    """The choice itself, Frappe-free."""

    def cols(self, *pairs):
        return [{"name": name, "data_type": kind} for name, kind in pairs]

    def test_picks_the_first_numeric_as_y_and_a_dimension_as_x(self):
        x, y, reason = self.api.pick_axes(
            self.cols(("year", "String"), ("total", "Decimal"), ("n", "Integer")))
        self.assertEqual((x, y, reason), ("year", "total", None))

    def test_the_measure_is_never_also_the_x_axis(self):
        x, y, reason = self.api.pick_axes(self.cols(("total", "Decimal"), ("year", "String")))
        self.assertEqual((x, y), ("year", "total"))
        self.assertIsNone(reason)

    def test_a_duration_read_as_string_is_refused(self):
        """The Process Duration case: a computed column has no numeric type."""
        _, _, reason = self.api.pick_axes(
            self.cols(("applicant", "String"), ("process_duration", "String")))
        self.assertIn("nothing to", reason)
        self.assertIn("process_duration (String)", reason)

    def test_a_named_string_y_axis_is_refused_by_name(self):
        _, _, reason = self.api.pick_axes(
            self.cols(("term", "String"), ("fee", "String")), y_axis="fee")
        self.assertIn("'fee' is a String", reason)
        self.assertIn("wrong without saying so", reason)

    def test_a_date_x_axis_is_fine(self):
        x, y, reason = self.api.pick_axes(self.cols(("day", "Date"), ("n", "Integer")))
        self.assertEqual((x, y, reason), ("day", "n", None))

    def test_no_columns_at_all_names_the_v3_reason(self):
        _, _, reason = self.api.pick_axes([])
        self.assertIn("no column types", reason)


class TestChartConfig(_Base):
    """The config builder against the real record, with nothing else in the way."""

    def test_matches_the_real_record_key_for_key(self):
        built = self.api.chart_config("academic_year", "count", "String", "Integer", "line")
        self.assertEqual(sorted(built), ["x_axis", "y_axis"])
        self.assertEqual(sorted(built["x_axis"]["dimension"]),
                         sorted(REAL_CONFIG["x_axis"]["dimension"]))
        self.assertEqual(sorted(built["y_axis"]["series"][0]["measure"]),
                         sorted(REAL_CONFIG["y_axis"]["series"][0]["measure"]))

    def test_the_names_repeat_the_column_as_the_real_record_does(self):
        built = self.api.chart_config("year", "total", "String", "Decimal", "bar")
        self.assertEqual(built["x_axis"]["dimension"]["dimension_name"], "year")
        self.assertEqual(built["y_axis"]["series"][0]["measure"]["measure_name"], "total")

    def test_a_native_measure_is_summed_not_counted(self):
        built = self.api.chart_config("year", "total", "String", "Decimal", "bar")
        self.assertEqual(built["y_axis"]["series"][0]["measure"]["aggregation"], "sum")


class TestSqlOperations(_Base):
    def test_round_trips(self):
        operations = self.api.sql_operations(SQL)
        self.assertEqual(operations,
                         [{"type": "sql", "raw_sql": SQL, "data_source": "Site DB"}])
        self.assertEqual(self.api.operation_sql(operations), SQL)

    def test_a_gui_composed_pipeline_has_no_sql_to_read(self):
        """The real v3 queries on the site are source+summarize, not sql."""
        self.assertIsNone(self.api.operation_sql(
            [{"type": "source", "table": {}}, {"type": "summarize"}]))
        self.assertIsNone(self.api.operation_sql([]))
        self.assertIsNone(self.api.operation_sql(None))


# The shape that was wrongly refused live: a block comment, a blank line, then
# WITH … SELECT. Trimmed from the real commission query.
COMMENTED_SQL = """/* Recruitment-agent commission earned from submitted student payments.
   Date basis: Payment Entry posting_date; one row per agent. */

WITH payment_schedule_count AS (
  SELECT `parent`, COUNT(*) AS `n` FROM `tabPayment Schedule` GROUP BY `parent`
)
SELECT `agent`, SUM(`amount`) AS `commission`
FROM `tabPayment Entry` JOIN payment_schedule_count USING (`parent`)
GROUP BY `agent`"""


class TestLeadingComments(_Base):
    """The guard reads a comment/string mask now, not raw text."""

    def created(self, sql):
        self.api.create_insights_query(sql)
        return self.stored_sql()

    # ------------------------------------------------------- must be ACCEPTED
    def test_the_exact_query_shape_that_was_refused_live(self):
        stored = self.created(COMMENTED_SQL)
        self.assertEqual(stored, COMMENTED_SQL,
                         "the comment must be stored with the query, not stripped from it")

    def test_a_semicolon_inside_the_comment_is_not_a_second_statement(self):
        """The live comment contains 'posting_date;' — prose, not SQL."""
        self.assertIn(";", COMMENTED_SQL.split("*/")[0], "fixture no longer covers this")
        self.created(COMMENTED_SQL)   # refuses if the mask is not applied

    def test_a_leading_line_comment_is_skipped(self):
        stored = self.created("-- what this counts\nSELECT 1 FROM `tabUser`")
        self.assertTrue(stored.startswith("-- what this counts"))

    def test_several_comments_and_blank_lines_before_the_statement(self):
        self.created("/* one */\n\n-- two\n\n/* three */\nSELECT 1 FROM `tabUser`")

    def test_a_semicolon_inside_a_string_literal_is_not_a_separator(self):
        self.created("SELECT ';' AS `sep` FROM `tabUser`")

    def test_no_comment_at_all_still_works_unchanged(self):
        self.assertEqual(self.created(SQL), SQL)

    def test_a_trailing_semicolon_is_still_stripped_after_a_comment(self):
        stored = self.created("/* note */ SELECT 1 FROM `tabUser`;")
        self.assertEqual(stored, "/* note */ SELECT 1 FROM `tabUser`")

    def test_double_dash_without_whitespace_is_arithmetic_not_a_comment(self):
        """MySQL's real rule. Treating it as a comment is the unsafe direction."""
        self.created("SELECT 1--2 AS `n` FROM `tabUser`")

    # -------------------------------------------------------- must be REFUSED
    def test_a_write_hidden_behind_a_comment_is_still_refused(self):
        message = self.refusal("/* looks safe */ DELETE FROM `tabUser`")
        self.assertIn("will not file a statement that writes", message)
        self.assertIn("DELETE", message, "the refusal must name the real first word")
        self.assertEqual(self.queries(), [])

    def test_a_write_behind_a_line_comment_is_still_refused(self):
        self.assertIn("will not file a statement that writes",
                      self.refusal("-- harmless\nDROP TABLE `tabUser`"))

    def test_a_comment_open_inside_a_string_cannot_swallow_a_second_statement(self):
        """THE bypass this mask exists to stop.

        A stripper that is not quote-aware sees the /* inside the string, treats
        the rest as an unterminated comment, and the ; and the DROP vanish.
        """
        message = self.refusal("SELECT '/*' AS `a` FROM `tabUser`; DROP TABLE `tabUser`")
        self.assertIn("more than one statement", message)
        self.assertEqual(self.queries(), [])

    def test_an_unterminated_block_comment_is_refused_not_swallowed(self):
        message = self.refusal("/* note that never closes\nSELECT 1 FROM `tabUser`")
        self.assertIn("never closed", message)

    def test_an_unterminated_comment_cannot_hide_a_write(self):
        self.assertIn("never closed", self.refusal("/* x ; DELETE FROM `tabUser`"))

    def test_an_executable_comment_is_treated_as_code_not_skipped(self):
        """/*! … */ RUNS in MySQL, so skipping it would skip real SQL."""
        message = self.refusal("/*!40001 SELECT 1 */ DELETE FROM `tabUser`")
        self.assertIn("will not file a statement that writes", message)

    def test_an_unterminated_string_is_refused(self):
        self.assertIn("never closed", self.refusal("SELECT 'oops FROM `tabUser`"))

    def test_a_comment_with_no_statement_after_it_says_so(self):
        message = self.refusal("/* just a note */")
        self.assertIn("only a comment", message)


class TestMaskSql(_Base):
    """The mask itself — same length in, same length out, so offsets line up."""

    def test_length_is_preserved(self):
        for text in (COMMENTED_SQL, SQL, "SELECT '/*' FROM t", "-- x\nSELECT 1"):
            masked, error = self.api._mask_sql(text)
            self.assertIsNone(error, text)
            self.assertEqual(len(masked), len(text), text)

    def test_comment_bodies_are_blanked_and_code_is_not(self):
        masked, _ = self.api._mask_sql("/* drop */ SELECT 1")
        self.assertNotIn("drop", masked)
        self.assertIn("SELECT 1", masked)

    def test_string_contents_are_blanked_but_the_quotes_remain(self):
        masked, _ = self.api._mask_sql("SELECT 'a;b' FROM t")
        self.assertNotIn(";", masked)
        self.assertEqual(masked.count("'"), 2)

    def test_a_doubled_quote_does_not_end_the_string(self):
        masked, error = self.api._mask_sql("SELECT 'it''s; fine' FROM t")
        self.assertIsNone(error)
        self.assertNotIn(";", masked)

    def test_a_backslash_escaped_quote_does_not_end_the_string(self):
        masked, error = self.api._mask_sql("SELECT 'a\\'; b' FROM t")
        self.assertIsNone(error)
        self.assertNotIn(";", masked)

    def test_backticked_identifiers_survive_a_backslash(self):
        masked, error = self.api._mask_sql("SELECT `a\\` FROM t")
        self.assertIsNone(error)
