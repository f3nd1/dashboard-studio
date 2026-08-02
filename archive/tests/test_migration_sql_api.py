"""Tests for the paste-SQL analysis endpoint.

Connects the Metabase parser to the migration flow: pasted SQL becomes a
structured description plus identity mapping suggestions a human then confirms.

Runs against the REAL reference SQL in reference/metabase/ (read-only) so the
supported and unsupported paths are exercised on genuine queries, not invented
ones. MOCK-BASED for Frappe itself — no live Bench.
"""

import os
import sys
import types
import unittest

REF = os.path.join(os.path.dirname(__file__), "..", "..", "reference", "metabase")


class _PermissionError(Exception):
    pass


class _ValidationError(Exception):
    pass


def _read(name):
    with open(os.path.join(REF, name), encoding="utf-8") as fh:
        return fh.read()


def _make_fake_frappe():
    frappe = types.ModuleType("frappe")
    frappe.PermissionError = _PermissionError
    frappe._roles = set()

    def only_for(roles, message=None):
        if isinstance(roles, str):
            roles = (roles,)
        if not (set(roles) & frappe._roles):
            raise _PermissionError(f"need one of {roles}")

    def whitelist(*a, **k):
        def deco(fn):
            return fn

        return deco

    def throw(msg):
        raise _ValidationError(msg)

    frappe.only_for = only_for
    frappe.whitelist = whitelist
    frappe.throw = throw
    frappe.get_doc = lambda *a, **k: None
    frappe.get_all = lambda *a, **k: []
    frappe.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
    return frappe


class TestAnalyzeMigrationSql(unittest.TestCase):
    def setUp(self):
        self._saved = {
            k: v for k, v in sys.modules.items()
            if k == "frappe" or k.startswith("dashboard_studio.api")
        }
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)
        self.frappe = _make_fake_frappe()
        sys.modules["frappe"] = self.frappe
        import dashboard_studio.api.migration as migration

        self.migration = migration
        self.frappe._roles = {"Dashboard Studio Editor"}

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    def test_role_is_enforced(self):
        self.frappe._roles = {"Some Other Role"}
        with self.assertRaises(_PermissionError):
            self.migration.analyze_migration_sql("SELECT COUNT(*) FROM `tabX`")

    def test_blank_sql_is_rejected(self):
        for bad in ("", "   ", None):
            with self.assertRaises(_ValidationError):
                self.migration.analyze_migration_sql(bad)

    def test_supported_query_yields_identity_suggestions(self):
        out = self.migration.analyze_migration_sql(
            "SELECT `tabStudent Applicant`.`academic_year` AS `academic_year`, COUNT(*) AS `count` "
            "FROM `tabStudent Applicant` GROUP BY `tabStudent Applicant`.`academic_year`"
        )
        self.assertTrue(out["analysis"]["supported"], out["analysis"]["reasons"])
        self.assertEqual(out["analysis"]["group_by"], ["academic_year"])
        self.assertEqual(
            out["suggested_mappings"],
            [{
                "external_table": "tabStudent Applicant",
                "target_doctype": "Student Applicant",
                "mapping_status": "Suggested",
            }],
        )

    def test_unsupported_query_yields_no_suggestions(self):
        # An unsupported query must not quietly seed mappings.
        out = self.migration.analyze_migration_sql(
            "SELECT COUNT(*) FROM `tabStudent Applicant` "
            "WHERE `tabStudent Applicant`.`status` = 'A' OR `tabStudent Applicant`.`status` = 'B'"
        )
        self.assertFalse(out["analysis"]["supported"])
        self.assertEqual(out["suggested_mappings"], [], "no suggestions from unsupported SQL")
        self.assertTrue(out["analysis"]["reasons"])

    # ---- against the real reference SQL ----
    def test_real_admissions_query_is_supported(self):
        sql = [
            block for block in _read("admission_dashboard_queries.sql").split(";")
            if "GROUP BY" in block and "academic_year" in block
        ][0]
        out = self.migration.analyze_migration_sql(sql)
        self.assertTrue(out["analysis"]["supported"], out["analysis"]["reasons"])
        self.assertEqual(
            [m["target_doctype"] for m in out["suggested_mappings"]], ["Student Applicant"]
        )

    def test_real_duration_query_is_flagged_with_no_suggestions(self):
        out = self.migration.analyze_migration_sql(
            _read("duration_from_counselling_to_admission.sql")
        )
        self.assertFalse(out["analysis"]["supported"])
        self.assertIn("subquery / nested SELECT", out["analysis"]["reasons"])
        self.assertEqual(out["suggested_mappings"], [])


if __name__ == "__main__":
    unittest.main()
