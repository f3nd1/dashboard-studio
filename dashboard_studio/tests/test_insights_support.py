"""The Insights plumbing the converter depends on.

What survived the scope cut from test_insights_handoff.py: the title clamp, the
installed-and-permitted check, and workbook resolution. The SQL-path tests went
to archive/tests/ with the code they covered.
"""

import sys
import unittest

from dashboard_studio.tests.fake_frappe import _make_fake_frappe, _PermissionError, _ValidationError


class _Base(unittest.TestCase):
    roles = {"Dashboard Studio Editor", "Insights User"}

    def setUp(self):
        self._saved = {k: v for k, v in sys.modules.items()
                       if k == "frappe" or k.startswith("dashboard_studio.")}
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        self.store = {}
        self.frappe = _make_fake_frappe(self.store, self.roles, ("Insights Query v3",))
        sys.modules["frappe"] = self.frappe

        import dashboard_studio.api.insights as insights

        self.api = insights

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    def workbooks(self):
        return list(self.store.get("Insights Workbook", {}).values())

    def refusal(self, fn, *args, **kwargs):
        with self.assertRaises(_ValidationError) as caught:
            fn(*args, **kwargs)
        return str(caught.exception)


class TestTitleClamp(_Base):
    """Frappe refuses an over-long Data value and ABORTS the insert rather than
    trimming, so a cosmetic title once took a whole conversion with it."""

    def test_a_title_at_the_limit_is_left_alone(self):
        exact = "x" * 140
        self.assertEqual(self.api.clamp_title(exact), exact)

    def test_an_over_long_title_is_trimmed_and_marked(self):
        clamped = self.api.clamp_title("y" * 400)
        self.assertEqual(len(clamped), 140)
        self.assertTrue(clamped.endswith("…"), "no marker that the title was cut")

    def test_whitespace_is_collapsed_not_counted(self):
        self.assertEqual(self.api.clamp_title("  lots   of\n space  "), "lots of space")
        self.assertEqual(self.api.clamp_title(None), "")


class TestRequireInsights(_Base):
    def test_a_v2_only_site_is_refused(self):
        """v3 ships the v2 DocTypes too, so testing for the v2 name passes on v3
        and writes an orphan. The guard must name v3 specifically."""
        self.frappe._doctypes = {"Insights Query", "Insights Chart"}
        message = self.refusal(self.api._require_insights)
        self.assertIn("older than v3", message)

    def test_a_missing_insights_role_names_the_role(self):
        self.frappe._roles = {"Dashboard Studio Editor"}
        message = self.refusal(self.api._require_insights)
        self.assertIn("Insights User", message)
        self.assertIn("does not get it automatically", message)

    def test_the_site_db_check_reads_the_v3_table_not_the_v2_one(self):
        """Both tables hold a row called "Site DB", so reading the v2 one passed
        by coincidence — and would start refusing the moment the v2 records were
        deleted, blaming a data source that was fine."""
        self.frappe._sources = set()
        self.frappe._v2_sources = {"Site DB", "Query Store"}
        self.assertIn("Site DB", self.refusal(self.api._require_insights))

    def test_a_healthy_v3_site_passes(self):
        self.api._require_insights()


class TestWorkbookChoice(_Base):
    def setUp(self):
        super().setUp()
        self.store["Insights Workbook"] = {
            "2": {"name": "2", "title": "EduTrust 2026"},
            "3": {"name": "3", "title": "Finance"},
        }

    def test_a_named_workbook_is_used(self):
        self.assertEqual(self.api._resolve_workbook("3"), "3")

    def test_blank_falls_back_to_the_studio_workbook_and_creates_it(self):
        for value in ("", "   ", None):
            name = self.api._resolve_workbook(value)
            made = [w for w in self.workbooks() if w["title"] == "Dashboard Studio"]
            self.assertEqual(len(made), 1, f"{value!r} did not fall back to the default")
            self.assertEqual(name, made[0]["name"])

    def test_an_unknown_workbook_is_refused(self):
        """It arrives from the browser, and `workbook` is a Link Frappe would
        accept as a dangling reference."""
        self.assertIn("no Insights workbook '999'",
                      self.refusal(self.api._resolve_workbook, "999"))

    def test_listing_names_the_default_and_the_real_ones(self):
        listed = self.api.list_insights_workbooks()
        self.assertEqual(listed["default_title"], "Dashboard Studio")
        self.assertEqual({w["title"] for w in listed["workbooks"]},
                         {"EduTrust 2026", "Finance"})

    def test_listing_needs_a_read_role(self):
        self.frappe._roles = {"Insights User"}
        with self.assertRaises(_PermissionError):
            self.api.list_insights_workbooks()


if __name__ == "__main__":
    unittest.main()
