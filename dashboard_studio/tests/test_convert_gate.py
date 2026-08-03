"""The conversion flow, end to end, through the real endpoint.

The number-comparison gate that used to live here went to
archive/test_convert_gate_verification.py with the gate itself (ADR-008). What
remains is the load-bearing half: a query this cannot translate must REFUSE and
write nothing, because a partial conversion answers a different question.
"""

import sys
import types
import unittest

from dashboard_studio.tests.fake_frappe import (
    _make_fake_frappe,
    _PermissionError,
    _ValidationError,
)

SQL = ("SELECT `academic_year`, COUNT(*) FROM `tabStudent Applicant` "
       "WHERE `status` = 'Enrolled' GROUP BY `academic_year`")

# Frappe's own DocType metadata is where the types come from — and, for a join,
# the proof that both column names are real.
META = {
    "Student Applicant": [("status", "Select"), ("academic_year", "Data"),
                          ("fee", "Currency"), ("po", "Data"),
                          ("layout", "Section Break")],
    # `corrective_action` is DEFINED on the DocType and is NOT a column of the
    # table any more. That drift is what put a non-existent column into a join's
    # select_columns and failed the query the moment it was opened.
    "Purchase Order": [("ref", "Data"), ("amount", "Currency"),
                       ("corrective_action", "Text")],
}

# The columns the TABLES actually have. The two differ on purpose: Frappe's
# underscore columns are optional and are not on every table, which is how a
# conversion succeeded here and then failed in Insights with "Column
# '_comments' is not found in table".
UNCONDITIONAL = ["name", "owner", "creation", "modified", "modified_by",
                 "docstatus", "idx", "parent", "parentfield", "parenttype"]
TABLES = {
    "Student Applicant": UNCONDITIONAL + ["_user_tags", "_comments", "_assign",
                                          "_liked_by", "status", "academic_year",
                                          "fee", "po"],
    # No underscore columns at all — the live failure's shape.
    "Purchase Order": UNCONDITIONAL + ["ref", "amount"],
}


class _Base(unittest.TestCase):
    roles = {"Dashboard Studio Editor", "Insights User"}

    def setUp(self):
        self._saved = {k: v for k, v in sys.modules.items()
                       if k == "frappe" or k.startswith("dashboard_studio.")}
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        self.store = {"Insights Workbook": {"2": {"name": "2", "title": "EduTrust 2026"}}}
        self.frappe = _make_fake_frappe(self.store, self.roles, ("Insights Query v3",))
        sys.modules["frappe"] = self.frappe

        import dashboard_studio.api.convert as convert

        self.api = convert
        self.frappe._doctypes = {"Insights Query v3", "Student Applicant", "Purchase Order"}
        self.frappe.get_meta = lambda dt: types.SimpleNamespace(fields=[
            types.SimpleNamespace(fieldname=f, fieldtype=t) for f, t in META[dt]])
        self.frappe._table_columns = {k: list(v) for k, v in TABLES.items()}

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    def queries(self):
        return list(self.store.get("Insights Query v3", {}).values())

    def refusal(self, fn, *args, **kwargs):
        with self.assertRaises(_ValidationError) as caught:
            fn(*args, **kwargs)
        return str(caught.exception)


class TestSqlConversion(_Base):
    """Pasted SQL reaches structured output."""

    def test_it_is_a_builder_query_not_a_native_one(self):
        self.api.convert_sql(SQL, workbook="2")
        self.assertEqual(self.queries()[0]["is_builder_query"], 1)
        self.assertNotIn("is_native_query", self.queries()[0])

    def test_the_workbook_picker_defaults_to_studios_own(self):
        result = self.api.convert_sql(SQL)
        self.assertEqual([w["title"] for w in self.store["Insights Workbook"].values()
                          if w["name"] == result["workbook"]], ["Dashboard Studio"])

    def test_an_unknown_workbook_is_refused_before_anything_is_written(self):
        self.assertIn("no Insights workbook", self.refusal(
            self.api.convert_sql, SQL, workbook="999"))
        self.assertEqual(self.queries(), [])

    def test_it_writes_operations_not_raw_sql(self):
        self.api.convert_sql(SQL, workbook="2")
        stored = __import__("json").loads(self.queries()[0]["operations"])
        self.assertEqual([op["type"] for op in stored], ["source", "filter", "summarize"])
        self.assertNotIn("sql", [op["type"] for op in stored],
                         "it fell back to a raw SQL operation")
        self.assertEqual(stored[0]["table"]["table_name"], "tabStudent Applicant")

    def test_types_come_from_frappes_doctype_metadata(self):
        self.api.convert_sql(SQL, workbook="2")
        stored = __import__("json").loads(self.queries()[0]["operations"])
        self.assertEqual(stored[2]["dimensions"][0]["data_type"], "String")

    def test_a_long_title_is_clamped_rather_than_aborting_the_insert(self):
        """Insights Query v3.title is varchar(140) and Frappe refuses an
        over-long value with "Value too big", which aborts the whole insert."""
        result = self.api.convert_sql(SQL, title="Q" * 400, workbook="2")
        self.assertLessEqual(len(result["title"]), 140)
        self.assertEqual(self.queries()[0]["title"], result["title"])

    def test_no_marker_is_left_on_the_title(self):
        """ADR-008 removed the number check. A marker nobody can ever clear
        would be on every converted query, so it would distinguish nothing."""
        result = self.api.convert_sql(SQL, title="Enrolled by year", workbook="2")
        self.assertEqual(result["title"], "Enrolled by year")
        self.assertEqual(self.queries()[0]["title"], "Enrolled by year")

    def test_a_join_becomes_a_join_operation_with_types_from_both_doctypes(self):
        """End to end: pasted SQL with a join lands as a clickable Join Table
        operation, both columns validated against real DocType metadata."""
        self.api.convert_sql(
            "SELECT a.`academic_year`, COUNT(*) FROM `tabStudent Applicant` a "
            "LEFT JOIN `tabPurchase Order` b ON b.`ref` = a.`po` "
            "WHERE b.`amount` >= 100 GROUP BY a.`academic_year`", workbook="2")
        stored = __import__("json").loads(self.queries()[0]["operations"])
        self.assertEqual([op["type"] for op in stored],
                         ["source", "join", "filter", "summarize"])
        self.assertEqual(stored[1]["join_type"], "left")
        self.assertEqual(stored[1]["table"]["table_name"], "tabPurchase Order")
        self.assertEqual(stored[1]["join_condition"], {
            "left_column": {"type": "column", "column_name": "po"},
            "right_column": {"type": "column", "column_name": "ref"}})
        # `amount` is Purchase Order's, and typed from ITS metadata, not the
        # source table's — a string 100 here matches nothing.
        self.assertEqual(stored[2]["value"], 100.0)

    def test_a_join_carries_only_what_the_query_reads(self):
        """Two live failures came from carrying every column of the joined
        table: one the DocType defined and the table did not
        (`corrective_action`), and one the table had and Insights did not.
        Neither was referenced by the query that broke."""
        self.api.convert_sql(
            "SELECT COUNT(*) FROM `tabStudent Applicant` a "
            "LEFT JOIN `tabPurchase Order` b ON b.`ref` = a.`po`", workbook="2")
        stored = __import__("json").loads(self.queries()[0]["operations"])
        self.assertEqual([c["column_name"] for c in stored[1]["select_columns"]],
                         ["ref"])

    def test_a_column_the_query_DOES_read_is_carried(self):
        self.api.convert_sql(
            "SELECT COUNT(*) FROM `tabStudent Applicant` a "
            "LEFT JOIN `tabPurchase Order` b ON b.`ref` = a.`po` "
            "WHERE b.`amount` >= 100", workbook="2")
        stored = __import__("json").loads(self.queries()[0]["operations"])
        self.assertEqual([c["column_name"] for c in stored[1]["select_columns"]],
                         ["amount", "ref"])

    def test_the_conversion_refuses_rather_than_guessing_the_column_list(self):
        """No fallback to DocType fields. A guessed column list is exactly what
        produces a query that converts cleanly and fails on open."""
        self.frappe.db.get_table_columns = None
        self.frappe.db.get_db_table_columns = None
        message = self.refusal(self.api.convert_sql, SQL, workbook="2")
        self.assertIn("could not be read from the database", message)
        self.assertIn("not a safe substitute", message)
        self.assertEqual(self.queries(), [])

    def test_the_second_schema_API_is_used_when_the_first_is_missing(self):
        """The name has moved between Frappe versions; losing one must not
        downgrade to guessing."""
        self.frappe.db.get_table_columns = None
        self.api.convert_sql(SQL, workbook="2")
        stored = __import__("json").loads(self.queries()[0]["operations"])
        self.assertEqual(stored[0]["table"]["table_name"], "tabStudent Applicant")

    def test_an_optional_column_the_table_lacks_is_refused_here_not_in_insights(self):
        """Purchase Order has none of the underscore columns. Assuming it did
        produced a query that converted cleanly and then failed on open with
        "Column '_comments' is not found in table"."""
        message = self.refusal(
            self.api.convert_sql,
            "SELECT COUNT(*) FROM `tabPurchase Order` WHERE `_comments` = 'x'",
            workbook="2")
        self.assertIn("'_comments' is not a column of Purchase Order", message)
        self.assertEqual(self.queries(), [])

    def test_an_optional_column_the_table_DOES_have_still_works(self):
        self.api.convert_sql(
            "SELECT COUNT(*) FROM `tabStudent Applicant` WHERE `_comments` = 'x'",
            workbook="2")
        stored = __import__("json").loads(self.queries()[0]["operations"])
        self.assertEqual(stored[1]["column"]["column_name"], "_comments")

    def test_the_unconditional_columns_are_there_on_a_table_without_the_others(self):
        self.api.convert_sql(
            "SELECT COUNT(*) FROM `tabPurchase Order` WHERE `parent` = 'x'",
            workbook="2")
        stored = __import__("json").loads(self.queries()[0]["operations"])
        self.assertEqual(stored[1]["column"]["column_name"], "parent")

    def test_a_layout_field_is_not_a_column(self):
        """A Section Break has a fieldname and no column. Grouping by one is a
        query the database rejects."""
        message = self.refusal(
            self.api.convert_sql,
            "SELECT `layout`, COUNT(*) FROM `tabStudent Applicant` GROUP BY `layout`",
            workbook="2")
        self.assertIn("'layout' is not a column of Student Applicant", message)

    def test_a_join_on_a_column_that_does_not_exist_writes_nothing(self):
        message = self.refusal(self.api.convert_sql,
                               "SELECT COUNT(*) FROM `tabStudent Applicant` a "
                               "JOIN `tabPurchase Order` b ON b.`nonsense` = a.`po`",
                               workbook="2")
        self.assertIn("not a column of Purchase Order", message)
        self.assertEqual(self.queries(), [])

    def test_an_unparseable_join_condition_writes_nothing(self):
        message = self.refusal(self.api.convert_sql,
                               "SELECT COUNT(*) FROM `tabStudent Applicant` a "
                               "JOIN `tabPurchase Order` b ON b.`ref` = a.`po` "
                               "AND b.`amount` = a.`fee`", workbook="2")
        self.assertIn("single equality", message)
        self.assertEqual(self.queries(), [])

    def test_an_unknown_table_is_refused_before_anything_is_written(self):
        message = self.refusal(self.api.convert_sql,
                               "SELECT COUNT(*) FROM `tabNonsense`", workbook="2")
        self.assertIn("no DocType called 'Nonsense'", message)
        self.assertEqual(self.queries(), [])

    def test_empty_sql_is_refused(self):
        self.assertIn("Paste a SQL query", self.refusal(self.api.convert_sql, "   "))

    def test_a_supplied_title_is_used_as_given(self):
        result = self.api.convert_sql(SQL, title="Enrolled by intake year", workbook="2")
        self.assertEqual(result["title"], "Enrolled by intake year")
        self.assertEqual(self.queries()[0]["title"], "Enrolled by intake year")

    def test_a_blank_title_falls_back_to_the_table(self):
        for blank in (None, "", "   "):
            self.store.pop("Insights Query v3", None)
            self.assertEqual(self.api.convert_sql(SQL, title=blank, workbook="2")["title"],
                             "Student Applicant query")

    def test_a_non_editor_cannot_convert_sql(self):
        self.frappe._roles = {"Dashboard Studio Viewer", "Insights User"}
        with self.assertRaises(_PermissionError):
            self.api.convert_sql(SQL, workbook="2")


if __name__ == "__main__":
    unittest.main()
