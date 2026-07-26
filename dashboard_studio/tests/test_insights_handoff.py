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
    def __init__(self, data, store):
        object.__setattr__(self, "_data", dict(data))
        object.__setattr__(self, "_store", store)

    def __getattr__(self, key):
        try:
            return self._data[key]
        except KeyError:
            raise AttributeError(key)

    def insert(self):
        table = self._store.setdefault(self._data["doctype"], {})
        # Insights Query is autoname: format:QRY-{####} — a generated name, NOT
        # the title. A fake that named records by title would have hidden that
        # the reuse key has to be the SQL.
        self._data["name"] = f"QRY-{1300 + len(table) + 1}"
        table[self._data["name"]] = dict(self._data)
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
    frappe.get_doc = lambda payload: _FakeDoc(payload, store)
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
