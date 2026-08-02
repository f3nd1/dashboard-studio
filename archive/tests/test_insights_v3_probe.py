"""scripts/insights_v3_probe.py must run however somebody starts it.

The first live run of that script died before printing anything::

    NameError: name 'REPORT' is not defined      (in check())
    NameError: name 'traceback' is not defined   (handling the first)

Cause: ``bench console`` is an *embedded* IPython shell (InteractiveShellEmbed
inside frappe's console() frame), so ``globals()`` and ``locals()`` are two
DIFFERENT dicts. A bare ``exec(open(...).read())`` there writes top-level names
into locals, while every function it defines captures globals as its
``__globals__`` — so a helper reading a module-level name looks in a dict that
name was never written to. ``frappe`` resolved only by luck: frappe's own
console module imports it, so it happened to be in those globals.

These tests run the real script against a fake Bench in both namespace shapes.
The split-namespace one is the regression test for that live failure; the
blank-line one covers the piped form, which IPython ends at the first blank line
inside an indented block.
"""

import contextlib
import io
import json
import pathlib
import re
import sys
import types
import unittest

PROBE = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "insights_v3_probe.py"


class Field(dict):
    __getattr__ = dict.get


class Meta:
    def __init__(self, fields):
        self.fields = [Field(f) for f in fields]


V3_META = {
    "Insights Query v3": [
        {"fieldname": "title", "fieldtype": "Data"},
        {"fieldname": "workbook", "fieldtype": "Link", "options": "Insights Workbook",
         "reqd": 1},
        {"fieldname": "operations", "fieldtype": "JSON"},
    ],
    "Insights Chart v3": [
        {"fieldname": "chart_type", "fieldtype": "Data"},
        {"fieldname": "config", "fieldtype": "JSON"},
    ],
}

FULL = {
    "__meta__": V3_META,
    "Insights Query": [{"name": "QRY-1310", "title": "Applicants", "is_native_query": 1,
                        "data_source": "Site DB", "chart": "CHART-9", "modified": "x"}],
    "Insights Query Result": [{"name": "RES-1", "query": "QRY-1310"}],
    "Insights Data Source": [{"name": "Site DB"}],
    "Insights Query v3": [{"name": "QRYV3-1", "title": "hand built", "workbook": "WB-1",
                           "modified": "x", "operations": json.dumps(
                               [{"type": "sql", "raw_sql": "SELECT 1",
                                 "data_source": "Site DB"}])}],
    "Insights Chart v3": [{"name": "CHV3-1", "title": "c", "chart_type": "Bar",
                           "query": "QRYV3-1", "workbook": "WB-1", "modified": "x",
                           "config": json.dumps({"x_axis": {"dimension": {
                               "column_name": "country", "data_type": "String"}}})}],
    "Insights Workbook": [{"name": "WB-1"}],
    "Insights Data Source v3": [{"name": "Site DB v3"}],
}
ALL_DOCTYPES = list(FULL) + ["Insights Dashboard", "Insights Chart",
                             "Insights Dashboard v3"]


def make_frappe(store, doctypes, *, break_count=False):
    """Just enough of frappe for the probe's read-only calls."""
    module = types.ModuleType("frappe")
    module.get_installed_apps = lambda: ["frappe", "insights", "dashboard_studio"]
    module.get_attr = lambda path: {"frappe.__version__": "15.44.0",
                                    "insights.__version__": "3.12.2",
                                    "dashboard_studio.__version__": "0.0.1"}[path]

    class DB:
        def exists(self, doctype, name=None):
            return name in doctypes if doctype == "DocType" else bool(store.get(doctype))

        def count(self, doctype):
            if break_count:
                raise RuntimeError("simulated: table missing")
            return len(store.get(doctype, []))

    module.db = DB()

    def get_all(doctype, filters=None, fields=None, limit=None, order_by=None, **kw):
        if doctype == "DocType":
            rows = [{"name": n} for n in doctypes]
            like = (filters or {}).get("name")
            if like:
                needle = like[1].replace("%", "").lower()
                rows = [r for r in rows if needle in r["name"].lower()]
            return rows
        rows = list(store.get(doctype, []))
        for key, value in (filters or {}).items():
            rows = [r for r in rows if r.get(key) == value]
        return [{k: r.get(k) for k in (fields or r)} for r in rows][: limit or None]

    module.get_all = get_all
    module.get_meta = lambda doctype: Meta(store.get("__meta__", {}).get(doctype, []))
    return module


def run_probe(frappe_module, *, split):
    """Run the real script and return everything it printed.

    ``split=True`` is the ``bench console`` shape: exec with separate globals and
    locals, and with NO ambient ``frappe`` in either — the script must import it
    itself rather than lean on whatever the caller's module happened to import.
    """
    sys.modules["frappe"] = frappe_module
    code = compile(PROBE.read_text(), str(PROBE), "exec")
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            if split:
                exec(code, {"__name__": "frappe.commands.utils"}, {})   # noqa: S102
            else:
                exec(code, {"__name__": "__probe__"})                   # noqa: S102
    finally:
        sys.modules.pop("frappe", None)
    return buffer.getvalue()


class TestRunsHoweverItIsStarted(unittest.TestCase):
    def test_bench_console_exec_from_an_open_file(self):
        """The live failure: separate globals and locals."""
        out = run_probe(make_frappe(FULL, ALL_DOCTYPES), split=True)
        self.assertNotIn("NameError", out)
        self.assertIn("8. The v2 queries", out, "did not reach the last check")

    def test_plain_module_level_exec(self):
        out = run_probe(make_frappe(FULL, ALL_DOCTYPES), split=False)
        self.assertNotIn("NameError", out)
        self.assertIn("8. The v2 queries", out)

    def test_no_blank_line_inside_an_indented_block(self):
        """IPython reading from stdin ends a block at the first blank line."""
        lines = PROBE.read_text().splitlines()
        indented = re.compile(r"^\s+\S")
        bad = [i + 1 for i in range(1, len(lines) - 1)
               if not lines[i].strip()
               and indented.match(lines[i - 1]) and indented.match(lines[i + 1])]
        self.assertEqual(bad, [], f"blank line inside a block at {bad} breaks piped paste")


class TestReportsWhatItFinds(unittest.TestCase):
    def setUp(self):
        self.out = run_probe(make_frappe(FULL, ALL_DOCTYPES), split=True)

    def test_prints_the_operations_array_whole(self):
        self.assertIn('"raw_sql": "SELECT 1"', self.out)

    def test_prints_the_chart_config_whole(self):
        self.assertIn('"column_name": "country"', self.out)

    def test_names_the_both_generations_problem(self):
        self.assertIn("BOTH generations ship together", self.out)

    def test_a_failing_check_does_not_stop_the_rest(self):
        out = run_probe(make_frappe(FULL, ALL_DOCTYPES, break_count=True), split=True)
        self.assertIn("FAILED - see traceback above", out)
        self.assertIn("1 native v3 queries", out, "check 5 stopped running")
        self.assertIn("8. The v2 queries", out, "check 8 stopped running")

    def test_asks_for_what_it_could_not_find_on_its_own(self):
        bare = dict(FULL, **{"Insights Query v3": [], "Insights Chart v3": []})
        out = run_probe(make_frappe(bare, ALL_DOCTYPES), split=True)
        self.assertIn("NEEDS A HAND-BUILT NATIVE QUERY", out)
        self.assertIn("NEEDS A HAND-BUILT CHART WITH AXES", out)

    def test_a_v2_only_site_reports_cleanly(self):
        gone = ("v3", "Workbook")
        store = {k: v for k, v in FULL.items() if not any(g in k for g in gone)}
        doctypes = [d for d in ALL_DOCTYPES if not any(g in d for g in gone)]
        out = run_probe(make_frappe(store, doctypes), split=True)
        self.assertIn("Insights Query v3            absent", out)
        self.assertIn("v3=0", out)


if __name__ == "__main__":
    unittest.main()
