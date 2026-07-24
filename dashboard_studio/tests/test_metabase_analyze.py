"""Tests for the conservative Metabase SQL analyzer.

Runs against the real reference/metabase/ samples: confirms the simple
count/group-by/filter queries parse into structured metric descriptions, and
that the complex duration query is correctly FLAGGED as unsupported (subquery)
rather than silently mistranslated.

Reference SQL is read read-only; nothing under reference/ is modified.
"""

import os
import unittest

from dashboard_studio.integrations.metabase.parser import analyze_sql, analyze_sql_file

REF = os.path.join(os.path.dirname(__file__), "..", "..", "reference", "metabase")


def _read(name):
    with open(os.path.join(REF, name), encoding="utf-8") as fh:
        return fh.read()


class TestAnalyzeSingleStatements(unittest.TestCase):
    def test_total_count(self):
        r = analyze_sql("SELECT COUNT(*) AS `count` FROM `tabStudent Applicant`;")
        self.assertTrue(r["supported"])
        self.assertEqual(r["doctypes"], ["Student Applicant"])
        self.assertEqual(r["aggregations"], [{"function": "COUNT", "argument": "*"}])
        self.assertEqual(r["filters"], [])
        self.assertEqual(r["group_by"], [])

    def test_conditional_count_parses_filter(self):
        r = analyze_sql(
            "SELECT COUNT(*) AS `count` FROM `tabStudent Applicant` "
            "WHERE `tabStudent Applicant`.`application_status` = 'Admitted';"
        )
        self.assertTrue(r["supported"])
        self.assertEqual(
            r["filters"],
            [{"field": "application_status", "operator": "=", "value": "Admitted"}],
        )

    def test_group_by_year(self):
        r = analyze_sql(
            "SELECT `tabStudent Applicant`.`academic_year` AS `academic_year`, COUNT(*) AS `count` "
            "FROM `tabStudent Applicant` GROUP BY `tabStudent Applicant`.`academic_year` "
            "ORDER BY `tabStudent Applicant`.`academic_year` ASC;"
        )
        self.assertTrue(r["supported"])
        self.assertEqual(r["group_by"], ["academic_year"])
        self.assertEqual(r["aggregations"], [{"function": "COUNT", "argument": "*"}])

    def test_single_join_supported(self):
        r = analyze_sql(
            "SELECT COUNT(*) AS `count` FROM `tabStudent Applicant` "
            "JOIN `tabStudent Admission UCC` ON `tabStudent Applicant`.`name` = `tabStudent Admission UCC`.`applicant` "
            "WHERE `tabStudent Applicant`.`application_status` = 'Admitted';"
        )
        self.assertTrue(r["supported"], r["reasons"])
        self.assertIsNotNone(r["join"])
        self.assertEqual(r["join"]["doctype"], "Student Admission UCC")

    def test_multiple_joins_flagged(self):
        r = analyze_sql(
            "SELECT COUNT(*) FROM `tabA` JOIN `tabB` ON `tabA`.`x`=`tabB`.`x` "
            "JOIN `tabC` ON `tabB`.`y`=`tabC`.`y`;"
        )
        self.assertFalse(r["supported"])
        self.assertTrue(any("multiple joins" in reason for reason in r["reasons"]))

    def test_or_clause_flagged_not_mangled(self):
        # OR cannot map to the engine's AND-only conditions; must be flagged,
        # never swallowed into a filter value.
        r = analyze_sql(
            "SELECT COUNT(*) FROM `tabStudent Applicant` "
            "WHERE `tabStudent Applicant`.`application_status` = 'Admitted' "
            "OR `tabStudent Applicant`.`application_status` = 'Approved';"
        )
        self.assertFalse(r["supported"])
        self.assertTrue(any("OR" in reason for reason in r["reasons"]), r["reasons"])
        self.assertEqual(r["filters"], [])

    def test_unparsable_where_condition_flagged_not_dropped(self):
        # A function call in WHERE doesn't fit the condition shape; dropping it
        # silently would migrate a metric that counts ALL rows. Must be flagged.
        r = analyze_sql("SELECT COUNT(*) FROM `tabX` WHERE LOWER(status) = 'admitted';")
        self.assertFalse(r["supported"])
        self.assertTrue(any("WHERE" in reason for reason in r["reasons"]), r["reasons"])

    def test_case_expression_flagged(self):
        r = analyze_sql(
            "SELECT SUM(CASE WHEN `tabStudent Applicant`.`application_status`='Admitted' "
            "THEN 1 ELSE 0 END) FROM `tabStudent Applicant`;"
        )
        self.assertFalse(r["supported"])
        self.assertIn("CASE expression", r["reasons"])


class TestAnalyzeReferenceFiles(unittest.TestCase):
    def test_admission_samples_mostly_supported_case_flagged(self):
        results = analyze_sql_file(_read("admission_dashboard_queries.sql"))
        self.assertGreaterEqual(len(results), 5)
        unsupported = [r for r in results if not r["supported"]]
        # Exactly one query in this file is complex: the "Admission success rate"
        # SUM(CASE WHEN ...) percentage. It must be flagged, not mistranslated;
        # every other (plain count / group-by / filter) query is supported.
        self.assertEqual(len(unsupported), 1, [r["reasons"] for r in unsupported])
        self.assertIn("CASE expression", unsupported[0]["reasons"])

    def test_duration_query_flagged_not_mistranslated(self):
        r = analyze_sql(_read("duration_from_counselling_to_admission.sql"))
        self.assertFalse(r["supported"])
        self.assertIn("subquery / nested SELECT", r["reasons"])


if __name__ == "__main__":
    unittest.main()
