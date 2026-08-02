"""Tests for the verification gate, removed with it (ADR-008).

Kept because they encode reasoning that is not obvious from the code — that a
mismatch must NOT clear the marker, that "12,34" is not 1234, and that
verifying twice says so rather than pretending it rechecked.

Nothing runs these.
"""

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


