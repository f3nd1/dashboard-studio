"""The conversion flow, and the gate that makes it safe to have at all.

The gate is the condition ADR-006 was reopened on: a converted query is not
trustworthy until a person has compared its number against the original. The
tests that matter most here are the ones asserting it CANNOT be skipped —
a mismatch must not clear the marker, and a refused translation must not write.
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
                          ("fee", "Currency"), ("po", "Data")],
    "Purchase Order": [("ref", "Data"), ("amount", "Currency")],
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
    """Pasted SQL reaches structured output, behind the gate."""

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

    def test_the_same_gate_applies(self):
        result = self.api.convert_sql(SQL, workbook="2")
        self.assertFalse(result["verified"])
        self.assertTrue(result["title"].startswith("[UNVERIFIED] "))
        self.assertTrue(self.queries()[0]["title"].startswith("[UNVERIFIED] "))

    def test_verifying_a_sql_conversion_uses_the_same_endpoint(self):
        made = self.api.convert_sql(SQL, workbook="2")
        self.assertIn("Metabase says 1234, Insights says 1200", self.refusal(
            self.api.verify_converted_query, made["name"], "1234", "1200"))
        self.api.verify_converted_query(made["name"], "1234", "1234")
        self.assertFalse(self.queries()[0]["title"].startswith("[UNVERIFIED] "))

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

    def test_a_supplied_title_is_used_and_still_carries_the_marker(self):
        result = self.api.convert_sql(SQL, title="Enrolled by intake year", workbook="2")
        self.assertEqual(result["title"], "[UNVERIFIED] Enrolled by intake year")
        self.assertEqual(self.queries()[0]["title"], "[UNVERIFIED] Enrolled by intake year")

    def test_a_blank_title_falls_back_to_the_table(self):
        for blank in (None, "", "   "):
            self.store.pop("Insights Query v3", None)
            self.assertEqual(self.api.convert_sql(SQL, title=blank, workbook="2")["title"],
                             "[UNVERIFIED] Student Applicant query")

    def test_verifying_clears_the_marker_from_a_supplied_title(self):
        made = self.api.convert_sql(SQL, title="Enrolled by intake year", workbook="2")
        self.api.verify_converted_query(made["name"], "12", "12")
        self.assertEqual(self.queries()[0]["title"], "Enrolled by intake year")

    def test_a_non_editor_cannot_convert_sql(self):
        self.frappe._roles = {"Dashboard Studio Viewer", "Insights User"}
        with self.assertRaises(_PermissionError):
            self.api.convert_sql(SQL, workbook="2")


class TestTheGate(_Base):
    """The condition ADR-006 was reopened on."""

    def convert(self):
        return self.api.convert_sql(SQL, workbook="2")

    def test_a_converted_query_is_marked_unverified_in_its_title(self):
        result = self.convert()
        self.assertTrue(result["title"].startswith("[UNVERIFIED] "))
        self.assertFalse(result["verified"])
        self.assertTrue(self.queries()[0]["title"].startswith("[UNVERIFIED] "),
                        "the marker must be ON THE RECORD, not only in the response — "
                        "it is what a person sees when they open it in Insights")

    def test_matching_numbers_clear_the_marker(self):
        made = self.convert()
        result = self.api.verify_converted_query(made["name"], "1234", "1234")
        self.assertTrue(result["verified"])
        self.assertFalse(result["already"])
        self.assertEqual(self.queries()[0]["title"], "Student Applicant query")

    def test_differing_numbers_refuse_AND_leave_the_marker(self):
        made = self.convert()
        message = self.refusal(
            self.api.verify_converted_query, made["name"], "1234", "1200")
        self.assertIn("Metabase says 1234, Insights says 1200", message)
        self.assertTrue(self.queries()[0]["title"].startswith("[UNVERIFIED] "),
                        "a mismatch cleared the marker — the gate is not a gate")

    def test_a_blank_number_is_not_a_match(self):
        made = self.convert()
        for pair in (("", "5"), ("5", ""), ("", "")):
            message = self.refusal(
                self.api.verify_converted_query, made["name"], pair[0], pair[1])
            self.assertIn("Enter the number", message)
        self.assertTrue(self.queries()[0]["title"].startswith("[UNVERIFIED] "))

    def test_formatting_differences_are_not_disagreements(self):
        for left, right in (("1,234", "1234"), ("1234", "1234.0"), ("0", "0.00")):
            matches, _ = self.api.verification_matches(left, right)
            self.assertTrue(matches, f"{left} vs {right} should agree")

    def test_a_genuinely_different_number_never_passes(self):
        for left, right in (("1234", "1235"), ("0", "1"), ("1,234", "12,34"),
                            ("12,34", "1234"), ("1.234", "1234")):
            matches, reason = self.api.verification_matches(left, right)
            self.assertFalse(matches, f"{left} vs {right} must not agree")
            self.assertIn("do not match", reason)

    def test_a_decimal_comma_is_not_a_thousands_separator(self):
        """"12,34" is 12.34 across most of Europe. Stripping every comma before
        parsing would read it as 1234 and let a hundredfold disagreement pass —
        inside the one function whose job is catching a disagreement."""
        self.assertFalse(self.api.verification_matches("12,34", "1234")[0])
        self.assertTrue(self.api.verification_matches("12,34", "12,34")[0])

    def test_non_numeric_answers_must_match_exactly(self):
        self.assertTrue(self.api.verification_matches("n/a", "n/a")[0])
        self.assertFalse(self.api.verification_matches("n/a", "N/A")[0])

    def test_verifying_twice_says_so_rather_than_pretending_it_rechecked(self):
        made = self.convert()
        self.api.verify_converted_query(made["name"], "5", "5")
        again = self.api.verify_converted_query(made["name"], "5", "5")
        self.assertTrue(again["already"])

    def test_the_marker_survives_a_long_title(self):
        result = self.api.convert_sql(SQL, title="Q" * 400, workbook="2")
        self.assertTrue(result["title"].startswith("[UNVERIFIED] "),
                        "clamping ate the marker")
        self.assertLessEqual(len(result["title"]), 140)

    def test_a_viewer_cannot_mark_something_verified(self):
        made = self.convert()
        self.frappe._roles = {"Dashboard Studio Viewer", "Insights User"}
        with self.assertRaises(_PermissionError):
            self.api.verify_converted_query(made["name"], "5", "5")


if __name__ == "__main__":
    unittest.main()
