"""scripts/insights_schema_check.py must run on the live site, and must not
write anything.

Same fake-Bench approach as test_metabase_table_inventory: the real script is
run against a stub `frappe` in both namespace shapes, because `bench console`
is an embedded IPython where globals() and locals() differ.

The assertions that matter are the two that make it safe to hand over: it
reports a stale Insights column list when there is one — that is the whole
point — and it calls nothing that writes.
"""

import contextlib
import io
import pathlib
import re
import sys
import types
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "insights_schema_check.py"

# Insights holds a column list that still has `corrective_action`; the table
# does not. That is the stale-schema case this script exists to find.
LIVE = ["name", "parent", "year", "trend"]
HELD = ["name", "parent", "year", "trend", "corrective_action"]


def make_frappe():
    """A stub frappe recording every call, so writes are provable by absence."""
    calls = []
    frappe = types.ModuleType("frappe")

    def get_all(doctype, filters=None, fields=None, limit=None, pluck=None, **kwargs):
        calls.append(("get_all", doctype))
        if doctype == "DocType":
            names = ["Insights Data Source v3", "Insights Table v3", "Insights Query v3"]
            return names if pluck else [{"name": n} for n in names]
        if doctype == "Insights Table v3":
            # Insights names these records by HASH and keys them by a `table`
            # FIELD. Matching on the record name reported "no record found" for
            # tables that plainly had one, on the live site.
            wanted = (filters or {}).get("table")
            if wanted == "tabQuality Performance Outcomes Performance Childtable":
                return [{"name": "5f3a9c11e2"}]
            return []
        if doctype == "Insights Data Source v3":
            return [{"name": "Site DB"}]
        return []

    def get_meta(doctype):
        calls.append(("get_meta", doctype))
        if doctype == "Insights Table v3":
            # The REAL shape, from the live site: sync/import configuration and
            # no per-column child table at all.
            return types.SimpleNamespace(fields=[
                types.SimpleNamespace(fieldname=name, fieldtype="Data", options=None)
                for name in ("table", "label", "data_source", "last_synced_on",
                             "row_limit", "stored", "sync_mode")])
        return types.SimpleNamespace(fields=[
            types.SimpleNamespace(fieldname="status", fieldtype="Data", options=None),
            types.SimpleNamespace(fieldname="last_synced", fieldtype="Datetime",
                                  options=None),
        ])

    class Doc:
        def __init__(self, doctype, name):
            self.doctype, self.name = doctype, name

        def get(self, key, default=None):
            return {"table": "tabQuality Performance Outcomes Performance Childtable",
                    "stored": 1, "last_synced_on": "2025-11-02 03:00:00",
                    "status": "Active", "last_synced": "2026-01-01"}.get(key, default)

    def get_doc(doctype, name=None):
        calls.append(("get_doc", doctype))
        return Doc(doctype, name)

    frappe.get_all = get_all
    frappe.get_meta = get_meta
    frappe.get_doc = get_doc
    frappe.db = types.SimpleNamespace(
        count=lambda doctype: 1,
        get_table_columns=lambda doctype: list(LIVE),
    )
    # Frappe caches the column list in redis; a stale entry there would make
    # everything reading through frappe.db agree with each other and be wrong.
    frappe.cache = types.SimpleNamespace(hget=lambda key, table: list(HELD))
    return frappe, calls


class TestInsightsSchemaCheck(unittest.TestCase):
    def run_script(self, namespace_split):
        frappe, calls = make_frappe()
        saved = sys.modules.get("frappe")
        sys.modules["frappe"] = frappe
        out = io.StringIO()
        try:
            source = SCRIPT.read_text()
            with contextlib.redirect_stdout(out):
                if namespace_split:
                    # bench console: globals() and locals() are different dicts.
                    exec(compile(source, str(SCRIPT), "exec"), {}, {})
                else:
                    exec(compile(source, str(SCRIPT), "exec"), {})
        finally:
            if saved is None:
                sys.modules.pop("frappe", None)
            else:
                sys.modules["frappe"] = saved
        return out.getvalue(), calls

    def test_runs_under_bench_consoles_split_namespaces(self):
        text, _ = self.run_script(True)
        self.assertIn("Insights DocTypes on this site", text)

    def test_runs_under_a_plain_module_level_exec(self):
        text, _ = self.run_script(False)
        self.assertIn("Insights DocTypes on this site", text)

    def test_no_blank_line_inside_an_indented_block(self):
        """IPython reading stdin ends a block at the first blank line, so a
        piped paste would stop halfway through the function."""
        lines = SCRIPT.read_text().splitlines()
        indented = re.compile(r"^\s+\S")
        bad = [i + 1 for i in range(1, len(lines) - 1)
               if not lines[i].strip()
               and indented.match(lines[i - 1]) and indented.match(lines[i + 1])]
        self.assertEqual(bad, [], f"blank line inside a block at {bad} breaks piped paste")

    def test_a_record_is_found_by_its_table_FIELD_not_its_name(self):
        """The first version matched on the record name and reported "no
        Insights record found" for tables that plainly had one — a false
        negative that reads as a finding."""
        text, _ = self.run_script(True)
        self.assertIn("Insights Table v3 '5f3a9c11e2'", text)
        self.assertNotIn("no record in any Insights DocType has table = "
                         "'tabQuality Performance Outcomes Performance Childtable'", text)
        self.assertIn("last_synced_on = 2025-11-02 03:00:00", text)

    def test_a_stale_frappe_cache_is_reported(self):
        """Everything reading through frappe.db shares that cache, so a stale
        entry makes the converter and the site agree with each other and both
        be wrong about the table."""
        text, _ = self.run_script(True)
        self.assertIn("redis CACHE DISAGREES", text)
        self.assertIn("corrective_action", text)

    def test_it_says_plainly_when_Insights_holds_no_column_list(self):
        """The live answer: no populated DocType has a per-column child table,
        so there is nothing here to resync — which is itself the finding."""
        text, _ = self.run_script(True)
        self.assertIn("Insights does not keep its column list in the database", text)

    def test_it_writes_nothing(self):
        _, calls = self.run_script(True)
        made = {name for name, _ in calls}
        self.assertEqual(made - {"get_all", "get_meta", "get_doc"}, set(),
                         "the script called something other than a read")
        source = SCRIPT.read_text()
        for forbidden in (".insert(", ".save(", ".delete(", "db.set_value",
                          "db.sql(", "frappe.enqueue", ".submit("):
            self.assertNotIn(forbidden, source,
                             f"{forbidden} is a write; this script is read-only")

    def test_an_unreadable_live_schema_is_reported_not_crashed(self):
        frappe, _ = make_frappe()
        def boom(doctype):
            raise RuntimeError("TableMissingError")
        frappe.db.get_table_columns = boom
        saved = sys.modules.get("frappe")
        sys.modules["frappe"] = frappe
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), {}, {})
        finally:
            sys.modules["frappe"] = saved if saved is not None else sys.modules.pop("frappe")
        self.assertIn("live schema UNREADABLE", out.getvalue())


if __name__ == "__main__":
    unittest.main()
