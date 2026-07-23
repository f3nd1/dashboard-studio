import unittest

from dashboard_studio.integrations.metabase.parser import discover_frappe_doctypes


class TestMetabaseParser(unittest.TestCase):
    def test_discovers_unique_doctypes(self):
        sql = "SELECT * FROM `tabStudent Applicant` JOIN `tabStudent Admission UCC` ON 1=1"
        self.assertEqual(
            discover_frappe_doctypes(sql),
            ["Student Applicant", "Student Admission UCC"],
        )


if __name__ == "__main__":
    unittest.main()
