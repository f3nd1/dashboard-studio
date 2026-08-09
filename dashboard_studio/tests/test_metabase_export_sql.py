"""scripts/metabase_export_sql.py must never execute a query, never leak the
key, and produce files bulk_dry_run.py can read.

Same fake-Bench approach as the other Metabase script's test: the real file is
run against a stub `frappe` and a stub `requests` that RECORDS every call, in
both namespace shapes, because `bench console` is an embedded IPython where
globals() and locals() differ.

This is the only file in the project that POSTs to Metabase, so the assertions
that matter are the ones about that: exactly one path is ever posted to, the
two endpoints that would run a query against production appear nowhere, and a
403 is a skipped card rather than a failed run.
"""

import contextlib
import io
import json
import pathlib
import re
import sys
import tempfile
import types
import unittest

SCRIPT = (pathlib.Path(__file__).resolve().parents[2]
          / "scripts" / "metabase_export_sql.py")

KEY = "mb_secret_key_do_not_print_me"
NATIVE_SQL = "SELECT `academic_year`, COUNT(*) FROM `tabStudent Applicant`"
COMPILED_SQL = "SELECT `__mb_source`.`avg` AS `avg` FROM ( SELECT 1 ) AS `__mb_source`"

# id, name, archived, query_type
CARDS = [
    {"id": 1, "name": "Enrolment by year", "archived": False},
    {"id": 2, "name": "Quality Performance / Outcomes", "archived": False},
    {"id": 3, "name": "Old thing", "archived": True},
]
DETAIL = {
    1: {"id": 1, "name": "Enrolment by year", "query_type": "native",
        "display": "line",
        # The real QIPI shape, plus two keys that live alongside
        # `series_settings` and are deliberately NOT copied.
        "visualization_settings": {
            "series_settings": {"avg": {"color": "#E75454", "title": "Average of QIPI"},
                                "count": {"display": "bar", "title": "Count of QA"}},
            "graph.dimensions": ["custom_proposed_date"],
            "column_settings": {'["name","fee"]': {"decimals": 2}},
        },
        "dataset_query": {"type": "native", "native": {"query": NATIVE_SQL}}},
    # GUI-built: MBQL, no SQL anywhere on the card.
    2: {"id": 2, "name": "Quality Performance / Outcomes", "query_type": "query",
        "dataset_query": {"type": "query", "database": 2,
                          "query": {"source-table": 7, "aggregation": [["avg", 9]]}}},
    3: {"id": 3, "name": "Old thing", "query_type": "native",
        "dataset_query": {"type": "native", "native": {"query": "SELECT 1"}}},
}


def make_requests(compile_status=200, compile_body=None):
    """A stub `requests` recording every call, so an execution is provable."""
    calls = []

    class Response:
        def __init__(self, status, body):
            self.status_code = status
            self._body = body

        def json(self):
            return self._body

    def get(url, headers=None, timeout=None):
        calls.append(("GET", url, None))
        path = url.split("/api/", 1)[1]
        if path == "card":
            return Response(200, CARDS)
        if path.startswith("card/"):
            return Response(200, DETAIL[int(path.split("/")[1])])
        return Response(404, {})

    def post(url, headers=None, json=None, timeout=None):
        calls.append(("POST", url, json))
        body = compile_body if compile_body is not None else {"query": COMPILED_SQL}
        return Response(compile_status, body)

    module = types.ModuleType("requests")
    module.get = get
    module.post = post
    return module, calls


def make_frappe(url="https://metabase.example", key=KEY):
    frappe = types.ModuleType("frappe")
    frappe.conf = {"metabase_url": url, "metabase_api_key": key}
    return frappe


class _Base(unittest.TestCase):
    def run_script(self, namespace_split=True, requests_module=None, frappe=None,
                   source=None):
        requests_module = requests_module or make_requests()[0]
        saved = {name: sys.modules.get(name) for name in ("frappe", "requests")}
        sys.modules["frappe"] = frappe or make_frappe()
        sys.modules["requests"] = requests_module
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            cwd = pathlib.Path.cwd()
            try:
                import os
                os.chdir(directory)
                text = source if source is not None else SCRIPT.read_text()
                with contextlib.redirect_stdout(out):
                    if namespace_split:
                        # bench console: globals() and locals() are different dicts.
                        exec(compile(text, str(SCRIPT), "exec"), {}, {})
                    else:
                        exec(compile(text, str(SCRIPT), "exec"), {})
                # Both halves of the export: the .sql AND its .json sidecar.
                files = {p.name: p.read_text()
                         for p in sorted(pathlib.Path("metabase_sql").glob("*.*"))} \
                    if pathlib.Path("metabase_sql").is_dir() else {}
            finally:
                os.chdir(cwd)
                for name, value in saved.items():
                    if value is None:
                        sys.modules.pop(name, None)
                    else:
                        sys.modules[name] = value
        return out.getvalue(), files


class TestItRuns(_Base):
    def test_runs_under_bench_consoles_split_namespaces(self):
        text, _ = self.run_script(True)
        self.assertIn("Exporting Metabase SQL", text)

    def test_runs_under_a_plain_module_level_exec(self):
        text, _ = self.run_script(False)
        self.assertIn("Exporting Metabase SQL", text)

    def test_no_blank_line_inside_an_indented_block(self):
        """IPython reading stdin ends a block at the first blank line, so a
        piped paste would stop halfway through the function."""
        lines = SCRIPT.read_text().splitlines()
        indented = re.compile(r"^\s+\S")
        bad = [i + 1 for i in range(1, len(lines) - 1)
               if not lines[i].strip()
               and indented.match(lines[i - 1]) and indented.match(lines[i + 1])]
        self.assertEqual(bad, [], f"blank line inside a block at {bad} breaks piped paste")

    def test_missing_config_says_so_and_calls_nothing(self):
        module, calls = make_requests()
        text, _ = self.run_script(requests_module=module,
                                  frappe=make_frappe(url="", key=""))
        self.assertIn("missing from site_config.json", text)
        self.assertEqual(calls, [], "it called Metabase without a configured key")


class TestNothingIsExecuted(_Base):
    """The whole reason this file is allowed to POST at all."""

    def test_the_only_POST_is_the_compile_endpoint(self):
        module, calls = make_requests()
        self.run_script(requests_module=module)
        posts = [url for verb, url, _ in calls if verb == "POST"]
        self.assertEqual(posts, ["https://metabase.example/api/dataset/native"])

    def test_the_executing_endpoints_appear_nowhere_in_the_source(self):
        """`POST /api/dataset` and `POST /api/card/:id/query` run the query
        against the production database. They are one word away from the one
        this file does use, so they are grepped for rather than reasoned about."""
        source = SCRIPT.read_text()
        for forbidden in ('"/api/dataset"', "'/api/dataset'", "/query\"", "/query'",
                          "/api/card/{card_id}/query", "query_json", "/api/dataset/"
                          + "json"):
            self.assertNotIn(forbidden, source, f"{forbidden} would execute a query")
        # requests.post appears exactly once, and on the compile path.
        self.assertEqual(source.count("requests.post"), 1)

    def test_a_redirected_compile_path_refuses_rather_than_posting(self):
        """The guard is at the call, not on the constant: changing the path has
        to delete a line that says what it protects."""
        module, calls = make_requests()
        source = SCRIPT.read_text().replace(
            '    native_path = "/api/dataset/native"',
            '    native_path = "/api/dataset"')
        text, _ = self.run_script(requests_module=module, source=source)
        self.assertEqual([c for c in calls if c[0] == "POST"], [],
                         "it posted to an executing endpoint")
        self.assertIn("could not compile", text)

    def test_with_compiling_off_it_never_posts(self):
        module, calls = make_requests()
        source = SCRIPT.read_text().replace("    compile_gui_cards = True",
                                            "    compile_gui_cards = False")
        text, files = self.run_script(requests_module=module, source=source)
        self.assertEqual([c for c in calls if c[0] == "POST"], [])
        self.assertIn("GUI-built, and compile_gui_cards is off", text)
        # …and the native card still exports, so the GET-only run is useful.
        # The native card still exports — its .sql and its sidecar, which is
        # written from the card JSON already in hand and needs no POST.
        self.assertEqual(sorted(files), ["Enrolment by year--1.json",
                                         "Enrolment by year--1.sql"])

    def test_it_writes_nothing_to_metabase_or_frappe(self):
        source = SCRIPT.read_text()
        for forbidden in (".insert(", ".save(", "requests.put", "requests.delete",
                          "requests.patch", "frappe.db", "frappe.get_doc"):
            self.assertNotIn(forbidden, source, f"{forbidden} writes something")


class TestTheKeyNeverLeaves(_Base):
    def test_the_key_is_not_printed_on_the_happy_path(self):
        text, _ = self.run_script()
        self.assertNotIn(KEY, text)

    def test_the_key_is_not_printed_when_metabase_rejects_the_call(self):
        """The 401/403 path is exactly where "helpful" context has put a key
        into _server_messages and then into somebody's browser."""
        module, _ = make_requests(compile_status=401)
        text, _ = self.run_script(requests_module=module)
        self.assertNotIn(KEY, text)
        self.assertIn("could not compile", text)

    def test_the_source_never_prints_the_key_or_the_headers(self):
        source = SCRIPT.read_text()
        for forbidden in ("print(key", "print(headers", "{key}", "{headers}"):
            self.assertNotIn(forbidden, source)


class TestTheOutput(_Base):
    def test_a_native_card_is_written_verbatim(self):
        _, files = self.run_script()
        self.assertEqual(files["Enrolment by year--1.sql"], NATIVE_SQL)

    def test_a_GUI_card_is_written_from_the_compiled_sql(self):
        _, files = self.run_script()
        self.assertEqual(files["Quality Performance - Outcomes--2.sql"], COMPILED_SQL)

    def test_the_card_is_sent_to_be_compiled_unchanged(self):
        """Metabase is the authority on what the question computes — ADR-006.
        Editing the MBQL on the way past would make that untrue."""
        module, calls = make_requests()
        self.run_script(requests_module=module)
        sent = [body for verb, _, body in calls if verb == "POST"][0]
        self.assertEqual(sent, DETAIL[2]["dataset_query"])

    def test_a_slash_in_a_card_name_does_not_become_a_directory(self):
        """"Quality Performance / Outcomes" would otherwise write into a
        subfolder that bulk_dry_run's rglob then reports under the wrong name."""
        _, files = self.run_script()
        self.assertIn("Quality Performance - Outcomes--2.sql", files)

    def test_the_id_is_in_the_name_so_two_cards_cannot_collide(self):
        _, files = self.run_script()
        # Both halves carry it: a sidecar is only trustworthy because its
        # name pins it to one card.
        self.assertTrue(all(re.search(r"--\d+\.(sql|json)$", name)
                            for name in files), files)

    def test_an_archived_card_is_skipped(self):
        _, files = self.run_script()
        self.assertNotIn("Old thing--3.sql", files)

    def test_it_points_at_the_dry_run(self):
        text, _ = self.run_script()
        self.assertIn("python scripts/bulk_dry_run.py", text)


class TestWhatGoesWrong(_Base):
    def test_a_403_skips_the_card_and_explains_the_permission(self):
        """The key's group may not allow compiling. That is a fact about the
        key, not a failure of the run, and the other cards still export."""
        module, _ = make_requests(compile_status=403)
        text, files = self.run_script(requests_module=module)
        self.assertIn("1 refused by Metabase permissions", text)
        self.assertIn("does not allow it", text)
        self.assertIn("Enrolment by year--1.sql", files)

    def test_a_compile_that_returns_no_sql_is_a_failure_not_an_empty_file(self):
        """An empty .sql file would convert cleanly in the dry run and count as
        a report that works."""
        module, _ = make_requests(compile_body={})
        text, files = self.run_script(requests_module=module)
        self.assertIn("compiled to nothing", text)
        self.assertNotIn("Quality Performance - Outcomes--2.sql", files)

    def test_the_other_spelling_of_the_compiled_body_is_read(self):
        """The key has moved between Metabase versions. Reading only one and
        finding nothing looks exactly like an empty card."""
        module, _ = make_requests(compile_body={"native": {"query": COMPILED_SQL}})
        _, files = self.run_script(requests_module=module)
        self.assertEqual(files["Quality Performance - Outcomes--2.sql"], COMPILED_SQL)

    def test_a_template_tag_is_counted_so_its_refusal_is_expected(self):
        """`{{param}}` is Metabase's syntax, not SQL. The dry run will refuse
        it, and that should be a known number rather than a mystery."""
        module, _ = make_requests(compile_body={"query": "SELECT {{year}} FROM `tabX`"})
        text, _ = self.run_script(requests_module=module)
        self.assertIn("contain Metabase template tags", text)

    def test_a_card_that_cannot_be_fetched_is_reported_not_fatal(self):
        module, calls = make_requests()
        broken = types.ModuleType("requests")
        broken.post = module.post

        def get(url, headers=None, timeout=None):
            if url.endswith("/api/card/1"):
                raise OSError("connection reset")
            return module.get(url, headers=headers, timeout=timeout)
        broken.get = get
        text, files = self.run_script(requests_module=broken)
        self.assertIn("could not fetch", text)
        self.assertIn("Quality Performance - Outcomes--2.sql", files)


if __name__ == "__main__":
    unittest.main()


class TestTheChartSidecar(_Base):
    """One `.json` beside every `.sql`, written in the SAME pass.

    That simultaneity is the whole design: it is what lets `convert_sql` trust
    the pair without matching anything. Matching a pasted query back to a card
    later would mean comparing SQL text, and this export is full of
    near-identical variants of one report.
    """

    def sidecar(self, files, name="Enrolment by year--1.json"):
        return json.loads(files[name])

    def test_one_is_written_beside_every_sql(self):
        _, files = self.run_script()
        for sql_name in [n for n in files if n.endswith(".sql")]:
            with self.subTest(sql_name):
                self.assertIn(sql_name[:-4] + ".json", files)

    def test_it_carries_the_series_settings_the_display_and_the_id(self):
        _, files = self.run_script()
        self.assertEqual(self.sidecar(files), {
            "card_id": 1,
            "display": "line",
            "series_settings": {
                "avg": {"color": "#E75454", "title": "Average of QIPI"},
                "count": {"display": "bar", "title": "Count of QA"}},
        })

    def test_it_does_NOT_copy_visualization_settings_wholesale(self):
        """Only the one key the chart needs. `visualization_settings` carries
        plenty else — axis choices, per-column formatting keyed by column name —
        and an export writes to disk, so it copies what it needs and no more."""
        _, files = self.run_script()
        written = self.sidecar(files)
        self.assertEqual(set(written), {"card_id", "display", "series_settings"})
        self.assertNotIn("column_settings", json.dumps(written))
        self.assertNotIn("graph.dimensions", json.dumps(written))

    def test_a_card_with_no_visualization_settings_still_gets_one(self):
        """Card 2 has none. An absent sidecar and an empty one mean the same
        thing to the converter, and always writing one keeps the pair total."""
        _, files = self.run_script()
        self.assertEqual(
            self.sidecar(files, "Quality Performance - Outcomes--2.json"),
            {"card_id": 2, "display": None, "series_settings": {}})

    def test_no_row_data_can_reach_it(self):
        """`visualization_settings` describes the chart, never its contents —
        but this asserts the output rather than trusting that."""
        _, files = self.run_script()
        for name in [n for n in files if n.endswith(".json")]:
            with self.subTest(name):
                for banned in ("rows", "data", "result_metadata", "dataset_query"):
                    self.assertNotIn(banned, json.loads(files[name]))
