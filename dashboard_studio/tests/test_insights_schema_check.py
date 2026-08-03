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
            # Named as Insights would name it, for one of the tables the script
            # asks about — otherwise the comparison never runs and every
            # assertion below passes without exercising anything.
            return [{"name": "tabQuality Performance Outcomes Performance Childtable"}]
        if doctype == "Insights Data Source v3":
            return [{"name": "Site DB"}]
        return []

    def get_meta(doctype):
        calls.append(("get_meta", doctype))
        if doctype == "Insights Table v3":
            return types.SimpleNamespace(fields=[
                types.SimpleNamespace(fieldname="table", fieldtype="Data", options=None),
                types.SimpleNamespace(fieldname="columns", fieldtype="Table",
                                      options="Insights Table Column"),
            ])
        return types.SimpleNamespace(fields=[
            types.SimpleNamespace(fieldname="status", fieldtype="Data", options=None),
            types.SimpleNamespace(fieldname="last_synced", fieldtype="Datetime",
                                  options=None),
        ])

    class Doc:
        def __init__(self, doctype, name):
            self.doctype, self.name = doctype, name

        def get(self, key, default=None):
            if key == "columns":
                return [types.SimpleNamespace(
                    name=c, get=lambda k, c=c: c if k == "column" else None)
                    for c in HELD]
            if key == "modified":
                return "2026-01-01 00:00:00"
            return {"status": "Active", "last_synced": "2026-01-01"}.get(key, default)

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

    def test_it_reports_a_column_Insights_has_and_the_table_does_not(self):
        """The whole point: the converter validates against the live schema, so
        this is the gap it cannot see from there."""
        text, _ = self.run_script(True)
        self.assertIn("IN INSIGHTS, NOT IN THE TABLE: ['corrective_action']", text)
        self.assertIn("this is the stale-schema case", text)

    def test_it_names_the_doctypes_and_their_shape(self):
        """Discovery, not assumption — the output is what a real check would be
        built against, so the names and field shapes have to be in it."""
        text, _ = self.run_script(True)
        self.assertIn("Insights Table v3", text)
        self.assertIn("columns", text)
        self.assertIn("Insights Table Column", text)

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
