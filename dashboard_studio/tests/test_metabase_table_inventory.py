"""scripts/metabase_table_inventory.py must run, and must not hand out a GRANT
block it cannot stand behind.

Same fake-Bench approach as test_insights_v3_probe: run the real script against
stub frappe/requests modules in both namespace shapes, because `bench console`
is an embedded IPython where globals() and locals() differ.

The assertion that matters most is the negative one: when anything is
unresolved, no GRANT block is printed. A table missing from a GRANT breaks a
dashboard with a permission error, so a confident-looking list built from a
partial scan is worse than no list.
"""

import contextlib
import io
import pathlib
import re
import sys
import types
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "metabase_table_inventory.py"

TABLES = [{"id": 2201, "name": "tabStudent Applicant"},
          {"id": 2359, "name": "tabPurchase Order"}]

NATIVE = {"id": 1, "name": "n", "query_type": "native", "archived": False,
          "dataset_query": {"lib/type": "mbql/query", "database": 3, "stages": [
              {"lib/type": "mbql.stage/native",
               "native": "SELECT * FROM `tabStudent Applicant`"}]}}
GUI = {"id": 2, "name": "g", "query_type": "query", "archived": False,
       "dataset_query": {"lib/type": "mbql/query", "database": 3, "stages": [
           {"lib/type": "mbql.stage/mbql", "source-table": 2359}]}}
BAD = {"id": 3, "name": "b", "query_type": "query", "archived": False,
       "dataset_query": {"lib/type": "mbql/query", "database": 3, "stages": [
           {"lib/type": "mbql.stage/mbql", "source-table": 9999}]}}
GONE = {"id": 4, "name": "old", "query_type": "query", "archived": True,
        "dataset_query": {}}


def make_modules(cards):
    """Stub frappe + requests. Records every URL so GET-only stays provable."""
    calls = []
    frappe = types.ModuleType("frappe")
    frappe.conf = {"metabase_url": "https://mb.example/", "metabase_api_key": "SECRET"}

    requests = types.ModuleType("requests")

    class Response:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    def get(url, headers=None, timeout=None):
        calls.append(url)
        path = url.split("mb.example", 1)[1]
        if path == "/api/table":
            return Response(TABLES)
        if path == "/api/card":
            return Response(cards)
        match = re.match(r"^/api/card/(\d+)$", path)
        if match:
            wanted = int(match.group(1))
            return Response(next(c for c in cards if c["id"] == wanted))
        raise AssertionError("unexpected path " + path)

    requests.get = get
    requests.RequestException = Exception
    return frappe, requests, calls


def run(cards, *, split):
    frappe, requests, calls = make_modules(cards)
    saved = {k: sys.modules.get(k) for k in ("frappe", "requests")}
    sys.modules["frappe"] = frappe
    sys.modules["requests"] = requests
    code = compile(SCRIPT.read_text(), str(SCRIPT), "exec")
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            if split:
                exec(code, {"__name__": "frappe.commands.utils"}, {})   # noqa: S102
            else:
                exec(code, {"__name__": "__inv__"})                     # noqa: S102
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    return buffer.getvalue(), calls


class TestRuns(unittest.TestCase):
    def test_runs_under_bench_consoles_split_namespaces(self):
        out, _ = run([NATIVE, GUI], split=True)
        self.assertNotIn("NameError", out)
        self.assertIn("tabStudent Applicant", out)

    def test_runs_under_a_plain_module_level_exec(self):
        out, _ = run([NATIVE, GUI], split=False)
        self.assertIn("tabPurchase Order", out)

    def test_no_blank_line_inside_an_indented_block(self):
        lines = SCRIPT.read_text().splitlines()
        indented = re.compile(r"^\s+\S")
        bad = [i + 1 for i in range(1, len(lines) - 1)
               if not lines[i].strip()
               and indented.match(lines[i - 1]) and indented.match(lines[i + 1])]
        self.assertEqual(bad, [], f"blank line inside a block at {bad} breaks piped paste")


class TestFindings(unittest.TestCase):
    def test_it_only_ever_issues_GETs(self):
        _, calls = run([NATIVE, GUI], split=True)
        self.assertTrue(all(c.startswith("https://mb.example/api/") for c in calls))
        self.assertIn("https://mb.example/api/table", calls)

    def test_both_native_and_gui_cards_contribute_tables(self):
        out, _ = run([NATIVE, GUI], split=True)
        self.assertIn("tabStudent Applicant", out)
        self.assertIn("tabPurchase Order", out)
        self.assertIn("1 native SQL", out)

    def test_archived_cards_are_skipped_and_counted(self):
        out, _ = run([NATIVE, GONE], split=True)
        self.assertIn("1 archived skipped", out)

    def test_a_clean_run_prints_the_grant_block(self):
        out, _ = run([NATIVE, GUI], split=True)
        self.assertIn("GRANT SELECT ON", out)
        self.assertIn("`tabStudent Applicant`", out)
        self.assertIn("REVOKE SELECT ON", out)

    def test_an_unresolved_card_withholds_the_grant_block(self):
        """The load-bearing one. A partial scan must not produce a list that
        looks authoritative — a missing table is a broken dashboard."""
        out, _ = run([NATIVE, BAD], split=True)
        self.assertIn("UNRESOLVED", out)
        self.assertIn("table id 9999", out)
        self.assertIn("NO GRANT BLOCK PRINTED", out)
        self.assertNotIn("GRANT SELECT ON", out)

    def test_the_key_is_never_printed(self):
        out, _ = run([NATIVE, GUI, BAD], split=True)
        self.assertNotIn("SECRET", out)


if __name__ == "__main__":
    unittest.main()
