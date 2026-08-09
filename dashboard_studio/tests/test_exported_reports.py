"""Listing and reading the server-side Metabase export.

The feature this replaces could not work: a browser `<input type=file>` opens
the CLIENT's filesystem, so it showed the user their own Mac's Downloads while
the exports sat on the bench. That is a browser security boundary, so the fix is
a server-side listing — which means this module reads files on the server by a
name the browser sent, and `site_config.json` (holding `metabase_api_key`) is
one directory above the folder it reads.

So the traversal tests here are not box-ticking. They are the reason the module
compares names against a listing instead of joining them onto a path.
"""

import pathlib
import sys
import tempfile
import unittest

from dashboard_studio.tests.fake_frappe import _make_fake_frappe, _ValidationError

SQL = "SELECT `academic_year`, COUNT(*) FROM `tabStudent Applicant`"
SIDECAR = ('{"card_id": 2424, "display": "line", '
           '"series_settings": {"count": {"display": "bar"}}}')


class _Base(unittest.TestCase):
    roles = {"Dashboard Studio Editor"}
    # A pair, a lone .sql, and a report whose name has no card id.
    files = {
        "Quality & Innovation Performance Index (QIPI)--2424.sql": SQL,
        "Quality & Innovation Performance Index (QIPI)--2424.json": SIDECAR,
        "Enrolment by year--1808.sql": SQL,
        "Hand written report.sql": SQL,
    }

    def setUp(self):
        self._saved = {k: v for k, v in sys.modules.items()
                       if k == "frappe" or k.startswith("dashboard_studio.")}
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        self.store = {}
        self.frappe = _make_fake_frappe(self.store, self.roles, ())
        sys.modules["frappe"] = self.frappe

        self._tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self._tmp.name)
        # The real layout: the export folder sits BESIDE the site directory,
        # and site_config.json — which holds the Metabase key — is inside it.
        (root / "site1").mkdir()
        (root / "site1" / "site_config.json").write_text(
            '{"metabase_api_key": "mb_secret_do_not_leak"}')
        self.folder = root / "metabase_sql"
        self.folder.mkdir()
        for name, text in self.files.items():
            (self.folder / name).write_text(text)
        self.frappe.get_site_path = lambda *a: str(root / "site1")
        self.frappe.conf = {}

        import dashboard_studio.api.exports as exports

        self.api = exports

    def tearDown(self):
        self._tmp.cleanup()
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    def refusal(self, fn, *args, **kwargs):
        with self.assertRaises(_ValidationError) as caught:
            fn(*args, **kwargs)
        return str(caught.exception)


class TestListing(_Base):
    def test_it_finds_the_export_beside_the_site_directory(self):
        """Where `metabase_export_sql.py` actually writes: `out_dir =
        "metabase_sql"`, relative to the sites directory bench console runs in."""
        result = self.api.list_exported_reports()
        self.assertTrue(result["available"], result.get("problem"))
        self.assertEqual(result["directory"], str(self.folder))
        self.assertEqual(result["total"], 3)

    def test_a_configured_directory_wins(self):
        other = pathlib.Path(self._tmp.name) / "elsewhere"
        other.mkdir()
        (other / "Only one--9.sql").write_text(SQL)
        self.frappe.conf = {"dashboard_studio_sql_dir": str(other)}
        result = self.api.list_exported_reports()
        self.assertEqual(result["directory"], str(other))
        self.assertEqual([r["report"] for r in result["reports"]], ["Only one"])

    def test_searching_narrows_by_the_REPORT_name(self):
        """Typing "QIPI" has to find it — browsing 1775 raw filenames was the
        original complaint, and the card id is not what anybody remembers."""
        result = self.api.list_exported_reports("qipi")
        self.assertEqual([r["report"] for r in result["reports"]],
                         ["Quality & Innovation Performance Index (QIPI)"])

    def test_the_card_id_is_stripped_from_the_displayed_name(self):
        names = {r["report"] for r in self.api.list_exported_reports()["reports"]}
        self.assertIn("Enrolment by year", names)
        # A file with no `--NNNN` keeps its whole name rather than losing a word.
        self.assertIn("Hand written report", names)

    def test_it_says_which_reports_carry_chart_settings(self):
        by_name = {r["report"]: r["has_sidecar"]
                   for r in self.api.list_exported_reports()["reports"]}
        self.assertTrue(by_name["Quality & Innovation Performance Index (QIPI)"])
        self.assertFalse(by_name["Enrolment by year"])

    def test_reports_WITH_a_sidecar_come_first(self):
        """Those are the ones that produce a chart, which is why this list
        exists at all."""
        self.assertTrue(self.api.list_exported_reports()["reports"][0]["has_sidecar"])

    def test_a_missing_folder_says_so_plainly(self):
        self.frappe.conf = {"dashboard_studio_sql_dir": "/no/such/place"}
        result = self.api.list_exported_reports()
        self.assertFalse(result["available"])
        self.assertIn("/no/such/place", result["problem"])
        self.assertIn("metabase_export_sql.py", result["problem"])

    def test_an_EMPTY_folder_says_so_rather_than_looking_like_no_matches(self):
        """An empty search box with no explanation reads as "nothing matched"
        when the truth is "nothing was ever exported"."""
        empty = pathlib.Path(self._tmp.name) / "empty"
        empty.mkdir()
        self.frappe.conf = {"dashboard_studio_sql_dir": str(empty)}
        result = self.api.list_exported_reports()
        self.assertFalse(result["available"])
        self.assertIn("No .sql exports", result["problem"])
        self.assertIn(str(empty), result["problem"])

    def test_the_directory_is_always_reported(self):
        """A silently wrong folder returns a real list for the wrong files."""
        self.assertIn("directory", self.api.list_exported_reports())

    def test_a_long_list_is_capped_and_says_the_total(self):
        for i in range(80):
            (self.folder / f"Bulk report {i}--{i}.sql").write_text(SQL)
        result = self.api.list_exported_reports("Bulk")
        self.assertEqual(result["total"], 80)
        self.assertEqual(result["shown"], 50)
        self.assertEqual(len(result["reports"]), 50)


class TestReading(_Base):
    STEM = "Quality & Innovation Performance Index (QIPI)--2424"

    def test_it_returns_the_sql_and_the_sidecar_together(self):
        result = self.api.read_exported_report(self.STEM)
        self.assertEqual(result["sql"], SQL)
        self.assertEqual(result["card"]["card_id"], 2424)
        self.assertIsNone(result["card_problem"])

    def test_a_report_with_no_sidecar_still_reads(self):
        result = self.api.read_exported_report("Enrolment by year--1808")
        self.assertEqual(result["sql"], SQL)
        self.assertIsNone(result["card"])

    def test_an_unreadable_sidecar_does_not_stop_the_sql(self):
        (self.folder / "Broken--7.sql").write_text(SQL)
        (self.folder / "Broken--7.json").write_text("{not json")
        result = self.api.read_exported_report("Broken--7")
        self.assertEqual(result["sql"], SQL)
        self.assertIsNone(result["card"])
        self.assertIn("not readable JSON", result["card_problem"])

    def test_a_sidecar_that_is_not_an_object_is_refused(self):
        (self.folder / "Listy--8.sql").write_text(SQL)
        (self.folder / "Listy--8.json").write_text("[1, 2, 3]")
        result = self.api.read_exported_report("Listy--8")
        self.assertIsNone(result["card"])
        self.assertIn("not a settings object", result["card_problem"])

    def test_an_unknown_report_refuses(self):
        self.assertIn("no exported report called",
                      self.refusal(self.api.read_exported_report, "nope"))

    def test_a_file_too_large_to_be_a_report_is_not_read(self):
        (self.folder / "Huge--9.sql").write_text("x" * (2 * 1024 * 1024 + 1))
        self.assertIn("larger than a report should be",
                      self.refusal(self.api.read_exported_report, "Huge--9"))


class TestItCannotLeaveTheFolder(_Base):
    """The one that matters. `site_config.json` is one directory up and holds
    `metabase_api_key`, so a traversal here is a credential disclosure.

    The module never joins a caller's string onto the folder — it compares
    against the folder's own listing — so these are unreachable by construction.
    Asserted anyway, because the next person to touch it may not know that.
    """

    ESCAPES = [
        "../site1/site_config",
        "../../site1/site_config",
        "..%2F..%2Fsite1%2Fsite_config",
        "/etc/passwd",
        "../site1/site_config.json",
        "subdir/../../site1/site_config",
        "....//site1/site_config",
        "",
        ".",
        "..",
        None,
    ]

    def test_no_path_escapes_the_export_folder(self):
        for name in self.ESCAPES:
            with self.subTest(repr(name)):
                message = self.refusal(self.api.read_exported_report, name)
                self.assertIn("no exported report called", message)
                self.assertNotIn("metabase_api_key", message)
                self.assertNotIn("mb_secret_do_not_leak", message)

    def test_an_absolute_path_to_a_REAL_file_still_refuses(self):
        """The file exists and is readable by this process. It is still not an
        exported report, so it is still not readable through here."""
        secret = pathlib.Path(self._tmp.name) / "site1" / "site_config.json"
        self.assertTrue(secret.is_file())
        self.refusal(self.api.read_exported_report, str(secret))
        self.refusal(self.api.read_exported_report, str(secret.with_suffix("")))

    def test_a_symlink_out_of_the_folder_is_not_followed_into_a_read(self):
        """A `.sql` symlink pointing at site_config would be listed by `glob`,
        so this pins that the exports folder's own contents are the boundary —
        if this ever fails, the listing itself needs a resolve() check."""
        secret = pathlib.Path(self._tmp.name) / "site1" / "site_config.json"
        link = self.folder / "sneaky--1.sql"
        try:
            link.symlink_to(secret)
        except OSError:
            self.skipTest("symlinks not available here")
        message = self.refusal(self.api.read_exported_report, "sneaky--1")
        self.assertIn("no exported report called", message)
        self.assertNotIn("mb_secret_do_not_leak", message)
        # And it is not offered in the list either.
        listed = [r["stem"] for r in self.api.list_exported_reports()["reports"]]
        self.assertNotIn("sneaky--1", listed)

    def test_a_symlinked_SIDECAR_is_not_read_either(self):
        """Same hole, the other file. A `.json` symlink would be parsed and
        returned as `card`, which is the same disclosure by another door."""
        secret = pathlib.Path(self._tmp.name) / "site1" / "site_config.json"
        (self.folder / "paired--2.sql").write_text(SQL)
        try:
            (self.folder / "paired--2.json").symlink_to(secret)
        except OSError:
            self.skipTest("symlinks not available here")
        result = self.api.read_exported_report("paired--2")
        self.assertEqual(result["sql"], SQL)
        self.assertIsNone(result["card"])

    def test_the_reader_never_joins_a_path_at_all(self):
        """The structural guarantee, asserted against the AST rather than the
        text — the first version of this grepped for "folder /" and matched the
        module docstring explaining why there is no "folder /". A check that
        cannot survive its own documentation is one somebody deletes.

        `pathlib` joins with `/`, so a Div anywhere in `read_exported_report`
        is a path being built; the safe version only ever compares."""
        import ast
        tree = ast.parse(pathlib.Path(self.api.__file__).read_text())
        reader = next(n for n in tree.body
                      if isinstance(n, ast.FunctionDef)
                      and n.name == "read_exported_report")
        joins = [ast.unparse(n) for n in ast.walk(reader)
                 if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)]
        self.assertEqual(joins, [], "read_exported_report builds a path")
        calls = [ast.unparse(n.func) for n in ast.walk(reader)
                 if isinstance(n, ast.Call)]
        for forbidden in ("open", "os.path.join", "folder.joinpath"):
            self.assertNotIn(forbidden, calls)


class TestItWritesNothing(_Base):
    def test_the_source_has_no_write_path(self):
        source = pathlib.Path(self.api.__file__).read_text()
        for forbidden in (".insert(", ".save(", ".delete(", "write_text",
                          "db.sql(", "db.set_value", "requests.", "unlink",
                          "mkdir", "rmtree"):
            self.assertNotIn(forbidden, source,
                             f"exports.py can write or execute: {forbidden}")

    def test_reading_creates_no_document(self):
        self.api.list_exported_reports("qipi")
        self.api.read_exported_report(TestReading.STEM)
        self.assertEqual(self.store, {})

    def test_both_endpoints_check_the_role(self):
        source = pathlib.Path(self.api.__file__).read_text()
        self.assertEqual(source.count("frappe.only_for(DS_WRITE_ROLES)"), 2)
        self.assertEqual(source.count("@frappe.whitelist()"), 2)


if __name__ == "__main__":
    unittest.main()
