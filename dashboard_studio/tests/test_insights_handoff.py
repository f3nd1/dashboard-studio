"""Tests for the Insights handoff — creating a native Query from pasted SQL.

Three things carry weight here and each is asserted from both directions:

1. the refusals name what is wrong (missing Insights role above all, which is
   the one a real Dashboard Studio Editor is most likely to hit);
2. Studio never files a statement that writes;
3. the same SQL twice reuses the record instead of piling up duplicates.

MOCK-BASED for Frappe — no live Bench. The fake models Insights' v2 shape as
confirmed on the site: Insights Query with a plain `sql` field, `is_native_query`
and a `data_source` Link to "Site DB".
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
        table = self._store.setdefault(self._data["doctype"], {})
        # Insights Query is autoname: format:QRY-{####} — a generated name, NOT
        # the title. A fake that named records by title would have hidden that
        # the reuse key has to be the SQL.
        self._data["name"] = f"QRY-{1300 + len(table) + 1}"
        table[self._data["name"]] = dict(self._data)
        return self

    def save(self):
        self._store.setdefault(self._doctype, {})[self._data["name"]] = dict(self._data)
        return self


def _make_fake_frappe(store, roles, doctypes=("Insights Query",), sources=("Site DB",)):
    frappe = types.ModuleType("frappe")
    frappe.PermissionError = _PermissionError
    frappe.ValidationError = _ValidationError
    frappe._roles = set(roles)
    frappe._doctypes = set(doctypes)
    frappe._sources = set(sources)

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
        if doctype == "Insights Data Source":
            return name in frappe._sources
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
    doctypes = ("Insights Query",)
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
        return list(self.store.get("Insights Query", {}).values())


class TestCreate(_Base):
    def test_creates_a_native_query_against_site_db(self):
        result = self.api.create_insights_query(SQL, analysis=ANALYSIS)
        row = self.queries()[0]
        self.assertEqual(row["is_native_query"], 1)
        self.assertEqual(row["data_source"], "Site DB")
        self.assertEqual(row["sql"], SQL)
        self.assertEqual(row["title"], "Count of Student Applicant by agent")
        self.assertTrue(result["name"].startswith("QRY-"))
        self.assertFalse(result["reused"])

    def test_returns_both_links_because_only_one_is_certain(self):
        result = self.api.create_insights_query(SQL, analysis=ANALYSIS)
        self.assertIn(result["name"], result["insights_url"])
        self.assertEqual(result["desk_url"], "/app/insights-query/" + result["name"])

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
        self.assertEqual(self.queries()[0]["sql"], SQL)

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
        self.assertIn("Insights Query v3", message, "v3 must be named as the other case")

    def test_a_missing_site_db_source_is_named(self):
        self.frappe._sources = set()
        self.assertIn("Site DB", self.refusal(SQL))
        self.assertEqual(self.queries(), [])

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


# The column row of a real executed result: metadata first, then data rows.
COLUMNS = [
    [{"label": "student_category", "type": "String", "options": {}},
     {"label": "count", "type": "Integer", "options": {}}],
    ["Local", 42], ["International", 17],
]
# What a real chart looks like before Studio touches it — colours and label
# rotation a person already set, which must survive.
STYLED = {"rotateLabels": "45", "colors": ["#123456"], "title": "Hand-written title",
          "query": "QRY-1321"}


def _chart_store(results=COLUMNS, options=None, chart="CHART-1"):
    return {
        "Insights Query": {"QRY-1": {"name": "QRY-1", "chart": chart, "title": "Q"}},
        "Insights Chart": {"CHART-1": {"name": "CHART-1", "query": "QRY-1",
                                       "chart_type": "", "options": options or {}}},
        "Insights Query Result": ({"RES-1": {"name": "RES-1", "query": "QRY-1",
                                             "results": results}} if results is not None else {}),
    }


class _ChartBase(_Base):
    results = COLUMNS
    options = None
    chart = "CHART-1"

    def setUp(self):
        super().setUp()
        self.store.update(_chart_store(self.results, self.options, self.chart))

    def chart_doc(self):
        return self.store["Insights Chart"]["CHART-1"]

    def apply(self, **kwargs):
        return self.api.apply_insights_chart("QRY-1", **kwargs)

    def refused(self, **kwargs):
        with self.assertRaises(_ValidationError) as caught:
            self.apply(**kwargs)
        return str(caught.exception)


class TestApplyChart(_ChartBase):
    def test_sets_the_axes_from_the_real_executed_columns(self):
        result = self.apply()
        self.assertEqual((result["x_axis"], result["y_axis"]), ("student_category", "count"))
        options = __import__("json").loads(self.chart_doc()["options"])
        self.assertEqual(options["xAxis"], [{"column": "student_category"}],
                         "xAxis must be an ARRAY — confirmed from a real record")
        self.assertEqual(options["yAxis"],
                         [{"column": "count", "series_options": {"type": "bar"}}])
        self.assertEqual(self.chart_doc()["chart_type"], "Bar")

    def test_it_updates_the_existing_chart_and_never_inserts(self):
        self.apply()
        self.assertEqual(list(self.store["Insights Chart"]), ["CHART-1"],
                         "a second chart was created — Insights already made one")

    def test_a_persons_styling_survives(self):
        self.options = dict(STYLED)
        self.setUp()
        self.apply()
        options = __import__("json").loads(self.chart_doc()["options"])
        self.assertEqual(options["rotateLabels"], "45")
        self.assertEqual(options["colors"], ["#123456"])
        self.assertEqual(options["title"], "Hand-written title")

    def test_an_explicit_pair_is_honoured(self):
        result = self.apply(x_axis="count", y_axis="count")
        self.assertEqual((result["x_axis"], result["y_axis"]), ("count", "count"))

    def test_line_gets_its_own_series_type(self):
        self.apply(chart_type="line")
        options = __import__("json").loads(self.chart_doc()["options"])
        self.assertEqual(options["yAxis"][0]["series_options"], {"type": "line"})
        self.assertEqual(self.chart_doc()["chart_type"], "Line")

    def test_unconfirmed_series_types_are_left_for_insights_to_default(self):
        """Row and Scatter series names are not confirmed, so nothing is invented."""
        self.apply(chart_type="row")
        options = __import__("json").loads(self.chart_doc()["options"])
        self.assertEqual(options["yAxis"][0]["series_options"], {})
        self.assertEqual(self.chart_doc()["chart_type"], "Row")


class TestApplyChartRefusals(_ChartBase):
    def test_a_string_y_axis_is_refused_by_name(self):
        message = self.refused(y_axis="student_category")
        self.assertIn("student_category", message)
        self.assertIn("String", message)
        self.assertEqual(self.chart_doc()["chart_type"], "", "it wrote despite refusing")

    def test_no_numeric_column_at_all_is_refused_and_lists_the_types(self):
        self.results = [[{"label": "a", "type": "String"}, {"label": "b", "type": "Datetime"}],
                        ["x", "y"]]
        self.setUp()
        message = self.refused()
        self.assertIn("nothing", message)
        self.assertIn("a (String)", message)
        self.assertIn("b (Datetime)", message)

    def test_an_axis_the_query_never_returned_is_refused_with_the_real_labels(self):
        message = self.refused(x_axis="agent")
        self.assertIn("'agent' is not a column", message)
        self.assertIn("student_category", message)
        self.assertIn("count", message)

    def test_a_query_that_has_not_been_run_is_refused_not_executed(self):
        self.results = None
        self.setUp()
        message = self.refused()
        self.assertIn("has not been run", message)
        self.assertIn("press Run", message)

    def test_a_query_with_no_chart_link_is_refused(self):
        self.chart = ""
        self.setUp()
        self.assertIn("no chart linked", self.refused())

    def test_a_non_axis_chart_type_is_refused_by_name(self):
        message = self.refused(chart_type="Pie")
        self.assertIn("Pie", message)
        self.assertIn("Bar, Line, Row, Scatter", message)

    def test_one_column_only_leaves_nothing_for_the_x_axis(self):
        self.results = [[{"label": "count", "type": "Integer"}], [5]]
        self.setUp()
        self.assertIn("only one column", self.refused())

    def test_missing_insights_role_still_refuses_first(self):
        self.frappe._roles = {"Dashboard Studio Editor"}
        self.assertIn("Insights User", self.refused())


class TestPickAxes(_Base):
    """The choice itself, Frappe-free."""

    def cols(self, *pairs):
        return [{"label": label, "type": kind} for label, kind in pairs]

    def test_picks_the_first_numeric_as_y_and_another_as_x(self):
        x, y, reason = self.api.pick_axes(
            self.cols(("year", "String"), ("total", "Decimal"), ("n", "Integer")))
        self.assertEqual((x, y, reason), ("year", "total", None))

    def test_the_measure_is_never_also_the_x_axis(self):
        x, y, reason = self.api.pick_axes(self.cols(("total", "Decimal"), ("year", "String")))
        self.assertEqual((x, y), ("year", "total"))
        self.assertIsNone(reason)

    def test_a_duration_read_as_string_is_refused(self):
        """The Process Duration case: a computed column comes back String."""
        _, _, reason = self.api.pick_axes(
            self.cols(("applicant", "String"), ("process_duration", "String")))
        self.assertIn("nothing", reason)
        self.assertIn("process_duration (String)", reason)

    def test_an_all_null_column_reads_as_string_and_is_refused_by_name(self):
        _, _, reason = self.api.pick_axes(
            self.cols(("term", "String"), ("fee", "String")), y_axis="fee")
        self.assertIn("'fee' as String", reason)
        self.assertIn("empty, mixed, or a computed value", reason)

    def test_no_columns_at_all(self):
        _, _, reason = self.api.pick_axes([])
        self.assertIn("no result columns", reason)


class TestResultColumns(_Base):
    def test_reads_the_metadata_row_only(self):
        self.assertEqual(
            self.api.result_columns(COLUMNS),
            [{"label": "student_category", "type": "String"},
             {"label": "count", "type": "Integer"}],
        )

    def test_a_column_with_no_type_defaults_to_string(self):
        """ResultColumn.from_dict does the same — an unknown type IS String."""
        self.assertEqual(self.api.result_columns([[{"label": "x"}], ["v"]]),
                         [{"label": "x", "type": "String"}])

    def test_junk_is_survived_rather_than_crashed_on(self):
        self.assertEqual(self.api.result_columns(None), [])
        self.assertEqual(self.api.result_columns([]), [])
        self.assertEqual(self.api.result_columns(["not a row"]), [])
        self.assertEqual(self.api.result_columns([[{"label": ""}, "junk"]]), [])


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
        return self.queries()[0]["sql"]

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
