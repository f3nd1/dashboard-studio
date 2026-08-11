"""The number comparison: what counts as agreement, and what it proves.

Everything else in this suite proves a query CONVERTS. This is the first thing
that asks whether it returns the same numbers, so the failure mode is the
opposite of the usual one: a comparison that is too forgiving reports a match
over a wrong number, which is the silent wrong answer this project exists to
refuse. Each tolerance decision is pinned from both sides — it accepts the
formatting difference it was chosen for, and rejects the fault just past it.
"""

import ast
import contextlib
import datetime
import io
import pathlib
import unittest
from decimal import Decimal

from dashboard_studio.integrations.reconcile import (
    compare_results,
    describe,
    match_columns,
    normalise,
)

SCRIPT = (pathlib.Path(__file__).resolve().parents[2]
          / "scripts" / "reconcile_numbers.py")


def result(columns, rows):
    return {"columns": columns, "rows": [dict(zip(columns, row)) for row in rows]}


class TestTwoDriversSpeakingDifferently(unittest.TestCase):
    """`frappe.db.sql` and ibis return the same value in different types."""

    def test_a_decimal_and_a_float_are_the_same_number(self):
        self.assertEqual(normalise(Decimal("3.5")), normalise(3.5))

    def test_an_int_and_a_float_are_the_same_number(self):
        self.assertEqual(normalise(7), normalise(7.0))

    def test_a_date_and_its_string_agree(self):
        self.assertEqual(normalise(datetime.date(2026, 3, 1)), "2026-03-01")

    def test_a_datetime_keeps_its_time(self):
        """Truncating to the date would call two different timestamps equal."""
        self.assertEqual(normalise(datetime.datetime(2026, 3, 1, 14, 30)),
                         "2026-03-01 14:30:00")
        self.assertNotEqual(normalise(datetime.datetime(2026, 3, 1, 14, 30)),
                            normalise(datetime.date(2026, 3, 1)))

    def test_NaN_and_None_are_both_nothing(self):
        """ibis returns NaN where SQL returns NULL. Same absent value."""
        self.assertIsNone(normalise(float("nan")))
        self.assertIsNone(normalise(None))

    def test_case_is_NOT_folded(self):
        """MySQL compares strings case-insensitively under most collations and
        ibis does not — one of the drifts this harness exists to find. Folding
        here would hide exactly that."""
        self.assertNotEqual(normalise("Active"), normalise("active"))


class TestTheTolerance(unittest.TestCase):
    """Chosen to absorb MySQL's DECIMAL rounding and nothing wider."""

    def compare(self, expected_value, actual_value):
        return compare_results(result(["v"], [[expected_value]]),
                               result(["v"], [[actual_value]]))

    def test_mysqls_four_decimal_average_matches_the_full_float(self):
        """AVG() over exact values returns DECIMAL at scale+4, so the card's
        SQL says 3.3333 where ours says 3.3333333333333335. That is the driver
        talking, not a disagreement — and a tolerance that flagged it would
        report every average in the corpus as a finding."""
        report = self.compare(Decimal("3.3333"), 10 / 3)
        self.assertTrue(report["match"], report["differences"])

    def test_a_real_fault_just_past_it_still_fails(self):
        """The check has to BITE. A percent is far below anything a fan-out or
        a swapped column does, and it is still reported."""
        report = self.compare(100.0, 101.0)
        self.assertFalse(report["match"])
        self.assertAlmostEqual(report["differences"][0]["delta"], 1 / 101, places=6)

    def test_a_doubled_number_is_the_fan_out_signature(self):
        self.assertFalse(self.compare(50.0, 100.0)["match"])

    def test_integer_division_truncating_is_caught(self):
        """5/2 as 2 rather than 2.5 — the MySQL-vs-ibis arithmetic drift."""
        self.assertFalse(self.compare(2.5, 2.0)["match"])

    def test_zero_against_a_small_number_does_not_divide_by_zero(self):
        """A count of 0 where the card says 0.001 is a total disagreement, and
        the delta scales by the larger side so it reports as 1.0 rather than
        raising."""
        report = self.compare(0.0, 1e-3)
        self.assertFalse(report["match"])
        self.assertEqual(report["differences"][0]["delta"], 1.0)

    def test_two_zeroes_agree(self):
        self.assertTrue(self.compare(0.0, 0).get("match"))

    def test_the_largest_delta_is_reported_even_when_everything_passes(self):
        """The tolerance argues with itself: a corpus landing at 1e-5 confirms
        the DECIMAL-rounding reasoning, and one landing at 1e-2 is a finding
        wearing a pass."""
        report = self.compare(Decimal("3.3333"), 10 / 3)
        self.assertTrue(report["match"])
        self.assertGreater(report["max_delta"]["v"], 1e-6)
        self.assertLess(report["max_delta"]["v"], 1e-4)
        self.assertIn("largest relative delta", describe(report)[0])


class TestRowsThatDoNotLineUp(unittest.TestCase):
    def test_a_differing_row_count_short_circuits_the_values(self):
        """One fault, reported once. Pairing 40 rows against 80 would report a
        difference on every column of every row, all of them this."""
        report = compare_results(result(["a"], [[1], [2]]),
                                 result(["a"], [[1], [2], [3]]))
        self.assertFalse(report["match"])
        self.assertEqual(report["differences"], [])
        self.assertIn("row counts differ", " ".join(report["notes"]))
        self.assertEqual(report["row_count"], {"expected": 2, "actual": 3})

    def test_the_same_rows_in_a_different_order_MATCH(self):
        """A query with no ORDER BY may return rows in any order, and comparing
        position by position would report every one as different."""
        report = compare_results(result(["a", "n"], [["x", 1], ["y", 2]]),
                                 result(["a", "n"], [["y", 2], ["x", 1]]))
        self.assertTrue(report["match"], report["differences"])

    def test_but_the_differing_ORDER_is_still_reported(self):
        """An ORDER BY that failed to translate is a real finding — just not a
        value one, so it is a note beside a match rather than a difference."""
        report = compare_results(result(["a"], [["x"], ["y"]]),
                                 result(["a"], [["y"], ["x"]]))
        self.assertTrue(report["match"])
        self.assertTrue(report["order_differs"])
        self.assertIn("ROW ORDER DIFFERS", describe(report)[0])

    def test_a_genuinely_different_row_is_found_after_sorting(self):
        report = compare_results(result(["a"], [["x"], ["y"]]),
                                 result(["a"], [["x"], ["z"]]))
        self.assertFalse(report["match"])
        self.assertEqual(report["difference_count"], 1)

    def test_a_wall_of_differences_is_counted_in_full_and_listed_in_part(self):
        """Disjoint value sets, so every row really does differ — an earlier
        version of this test used i against i+1, whose two sets share 99 of
        their 100 values, and the sorted comparison correctly found 3."""
        rows_e = [[float(i)] for i in range(100)]
        rows_a = [[float(i) + 1000] for i in range(100)]
        report = compare_results(result(["v"], rows_e), result(["v"], rows_a))
        self.assertEqual(report["difference_count"], 100)
        self.assertEqual(len(report["differences"]), 20)
        self.assertIn("the first 20 are listed", " ".join(report["notes"]))

    def test_rows_pair_up_across_the_DECIMAL_rounding(self):
        """Numbers sort AS NUMBERS, rounded to 6 significant figures.

        Sorting them by their text is consistent right up until it is not:
        10.0 keys as "10.0" and its float64 twin 9.9999999 as "9.99…", which
        sorts the other side of a row worth 9.5. The two sides then land in
        different orders, 10.0 is compared against 9.5, and a query that agrees
        perfectly reports every row as different.
        """
        report = compare_results(
            result(["v"], [[Decimal("10.0")], [Decimal("9.5")]]),
            result(["v"], [[9.99999993], [9.5]]))
        self.assertTrue(report["match"], report["differences"])


class TestNoRowsIsNotAgreement(unittest.TestCase):
    """The failure mode of running this against the wrong database.

    Two empty results agree, and prove nothing. On a copy that is not the one
    the reports were written against, that is EVERY card — and a column of
    green ticks is exactly how a harness stops being read.
    """

    def test_both_empty_is_inconclusive_and_not_a_match(self):
        report = compare_results(result(["a"], []), result(["a"], []))
        self.assertTrue(report["inconclusive"])
        self.assertFalse(report["match"])
        self.assertIn("INCONCLUSIVE", describe(report)[0])
        self.assertIn("not evidence of anything", " ".join(report["notes"]))

    def test_one_side_empty_is_an_ordinary_difference(self):
        """Rows on one side and none on the other is a real finding, not an
        inconclusive one — a filter that did not survive looks exactly so."""
        report = compare_results(result(["a"], [["x"]]), result(["a"], []))
        self.assertFalse(report["inconclusive"])
        self.assertFalse(report["match"])

    def test_rows_that_agree_are_still_a_match(self):
        report = compare_results(result(["a"], [["x"]]), result(["a"], [["x"]]))
        self.assertTrue(report["match"])
        self.assertFalse(report["inconclusive"])


class TestPairingColumns(unittest.TestCase):
    def test_an_exact_name_pairs(self):
        pairs, left, right = match_columns(["name"], ["name"])
        self.assertEqual((pairs, left, right), ([("name", "name")], [], []))

    def test_a_slugged_computed_alias_pairs_with_its_raw_spelling(self):
        """ADR-033: every computed alias is stored under Insights' own
        sanitize_name, so the card's `Exit  Qn. 7` is our `exit__qn__7`. Same
        column, spelled the way the engine spells it."""
        pairs, _, _ = match_columns(["Exit  Qn. 7"], ["exit__qn__7"])
        self.assertEqual(pairs, [("Exit  Qn. 7", "exit__qn__7")])

    def test_leftovers_are_NOT_paired_by_position(self):
        """The card's `AVG(x) AS avg` is our `avg_of_x` and they do not match by
        name. Pairing what is left over by position would compare two columns
        nobody checked were the same — which can agree as easily as it can
        disagree, and a false agreement here is worse than no answer."""
        pairs, left, right = match_columns(["avg"], ["avg_of_x"])
        self.assertEqual(pairs, [])
        self.assertEqual((left, right), (["avg"], ["avg_of_x"]))

    def test_an_operators_mapping_pairs_them(self):
        pairs, left, right = match_columns(["avg"], ["avg_of_x"],
                                           {"avg": "avg_of_x"})
        self.assertEqual((pairs, left, right), ([("avg", "avg_of_x")], [], []))

    def test_unpaired_columns_prevent_a_MATCH_and_say_so(self):
        """Half a comparison must never read as a pass."""
        report = compare_results(result(["a", "avg"], [["x", 1.0]]),
                                 result(["a", "avg_of_x"], [["x", 1.0]]))
        self.assertFalse(report["match"])
        self.assertIn("could not be paired", " ".join(report["notes"]))
        self.assertEqual(report["columns"]["only_expected"], ["avg"])
        self.assertEqual(report["columns"]["only_actual"], ["avg_of_x"])

    def test_one_name_is_not_consumed_twice(self):
        pairs, left, right = match_columns(["v", "V"], ["v"])
        self.assertEqual(pairs, [("v", "v")])
        self.assertEqual((left, right), (["V"], []))


class TestTheScriptIsReadOnly(unittest.TestCase):
    """It runs SQL on the live site, so what it may run is asserted, not
    reviewed. Read as a SYNTAX TREE where that is what the check is about —
    grepping source text is how an earlier test in this repo matched its own
    docstring and proved nothing."""

    SOURCE = SCRIPT.read_text()
    TREE = ast.parse(SOURCE)

    def called(self):
        out = []
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.Call):
                out.append(ast.unparse(node.func))
        return out

    def test_it_never_writes_anything(self):
        for name in ("insert", "save", "submit", "delete", "db_set",
                     "frappe.db.set_value", "frappe.db.commit",
                     "frappe.delete_doc", "convert_sql"):
            self.assertNotIn(name, self.called(), f"{name} is a write path")
        for name in self.called():
            self.assertFalse(name.endswith((".insert", ".save", ".commit")), name)

    def literals(self):
        """Every string the code contains, EXCLUDING docstrings.

        The first version of this test searched the source text and failed on
        this script's own docstring, which explains why it must not call
        `/api/card/:id/query`. That is the same fault the AST tests next door
        exist to prevent — prose read as if it were code — and it has now
        appeared three times in this repo, so it is worth recognising on sight.
        """
        docstrings = set()
        for node in ast.walk(self.TREE):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
                body = getattr(node, "body", None) or []
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    docstrings.add(id(body[0].value))
        return [node.value for node in ast.walk(self.TREE)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings]

    def test_it_makes_no_network_call_of_any_kind(self):
        """It does not touch Metabase. Running a card would need
        `POST /api/card/:id/query`, which executes against production and is on
        the never-add list — the card's SQL is read off disk instead, from the
        export the approved compile-only endpoint already produced."""
        imported = set()
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        for name in imported:
            self.assertFalse(
                name.split(".")[0] in {"requests", "urllib", "http", "socket"},
                f"{name} could reach the network")
        for text in self.literals():
            for forbidden in ("/api/", "metabase_api_key", "http://", "https://"):
                self.assertNotIn(forbidden, text, f"{forbidden} in {text!r}")

    def test_the_statement_guard_is_applied_before_anything_runs(self):
        """The card's SQL comes off disk, and disk is not a trusted input: the
        folder is writable by whoever can reach the bench. So it is checked to
        be one SELECT before it is handed to the database."""
        self.assertIn("def _read_only", self.SOURCE)
        self.assertIn("rollback", self.SOURCE)

    def test_it_rolls_back_whatever_happened(self):
        self.assertIn("frappe.db.rollback()", self.SOURCE)

    def test_no_blank_line_inside_an_indented_block(self):
        """IPython reading stdin ends a block at the first blank line."""
        lines = self.SOURCE.splitlines()
        bad = [i + 1 for i in range(1, len(lines) - 1)
               if not lines[i].strip()
               and lines[i - 1][:1].isspace() and lines[i - 1].strip()
               and lines[i + 1][:1].isspace() and lines[i + 1].strip()]
        self.assertEqual(bad, [], f"blank line inside a block at {bad}")


class TestWhatTheGuardRejects(unittest.TestCase):
    """The guard is imported from the script rather than re-implemented here —
    a copy would drift from the one that runs."""

    def guard(self):
        """The guard the SCRIPT runs, not a copy of it — a copy would drift
        from the one that touches the database. Its usage banner is swallowed;
        the script prints it because exec'ing the file also runs it."""
        namespace = {}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), namespace)  # noqa: S102
        return namespace["_read_only"]

    def test_every_captured_card_in_this_repo_passes_it(self):
        """A guard that refused real Metabase SQL would be useless, and these
        are the real captures — Metabase's own compiled output, brackets,
        wrappers, string literals and all."""
        fixtures = sorted((pathlib.Path(__file__).resolve().parent
                           / "fixtures").glob("*.sql"))
        self.assertGreaterEqual(len(fixtures), 5, "expected the real captures")
        guard = self.guard()
        for path in fixtures:
            with self.subTest(path.name):
                self.assertEqual(guard(path.read_text()), "", path.name)

    def test_a_plain_select_passes(self):
        self.assertEqual(self.guard()("SELECT `a` FROM `tabX`"), "")

    def test_a_leading_comment_or_bracket_does_not_hide_the_verb(self):
        for text in ("/* hi */ DELETE FROM `tabX`", "( DELETE FROM `tabX` )",
                     "\n\n  -- note\n  UPDATE `tabX` SET a = 1"):
            with self.subTest(text):
                self.assertTrue(self.guard()(text), text)

    def test_a_second_statement_is_refused(self):
        self.assertTrue(self.guard()("SELECT 1; DROP TABLE `tabX`"))

    def test_TWO_SELECTS_are_refused_too(self):
        """Not because a second read is dangerous, but because the count check
        must stand on its own: with only the verb scan, this file's protection
        would rest entirely on a list of words, and a driver configured for
        multi-statements would run whatever followed the first semicolon."""
        self.assertTrue(self.guard()("SELECT 1; SELECT 2"))

    def test_a_semicolon_inside_a_string_is_not_a_second_statement(self):
        """A real card filters on values with punctuation in them; refusing
        those would make the harness useless on exactly the filtered shape it
        is meant to cover."""
        self.assertEqual(self.guard()("SELECT `a` FROM `tabX` WHERE `b` = 'x; y'"), "")

    def test_a_trailing_semicolon_is_fine(self):
        self.assertEqual(self.guard()("SELECT `a` FROM `tabX` ;  "), "")

    def test_every_writing_verb_is_refused(self):
        for verb in ("INSERT INTO x VALUES (1)", "UPDATE x SET a = 1",
                     "DELETE FROM x", "DROP TABLE x", "TRUNCATE x",
                     "ALTER TABLE x ADD b INT", "CREATE TABLE x (a INT)",
                     "GRANT ALL ON x TO y", "REPLACE INTO x VALUES (1)",
                     "CALL sp()", "LOAD DATA INFILE 'x' INTO TABLE y",
                     "SET autocommit = 1"):
            with self.subTest(verb):
                self.assertTrue(self.guard()(verb), verb)

    def test_a_writing_verb_hidden_mid_statement_is_refused(self):
        """`SELECT … INTO OUTFILE` writes a file and starts with SELECT."""
        self.assertTrue(self.guard()(
            "SELECT `a` FROM `tabX` INTO OUTFILE '/tmp/x'"))

    def test_a_column_named_after_a_verb_still_passes(self):
        """`update_stock` and `create_date` are ordinary Frappe columns. A
        guard that refused them would refuse most of the corpus."""
        self.assertEqual(
            self.guard()("SELECT `update_stock`, `creation` FROM `tabX`"), "")


if __name__ == "__main__":
    unittest.main()


class TestTheDatabaseReport(unittest.TestCase):
    """`which_database.py` exists because "does this reach production?" was
    answered by inference once. It prints configuration, so what it may print
    is asserted rather than reviewed — this output gets pasted into chat."""

    PATH = (pathlib.Path(__file__).resolve().parents[2]
            / "scripts" / "which_database.py")
    SOURCE = PATH.read_text()
    TREE = ast.parse(SOURCE)

    def field_lists(self):
        """Every string inside a `fields=[...]` argument."""
        out = []
        for node in ast.walk(self.TREE):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg == "fields":
                    out.extend(element.value for element in keyword.value.elts
                               if isinstance(element, ast.Constant))
        return out

    def test_it_never_asks_for_a_credential_field(self):
        """The credential fields on Insights Data Source v3, read from the
        DocType's own JSON at v3.12.2. Asking for one would put it in a
        terminal, and this output is written to be pasted."""
        for secret in ("password", "username", "api_token", "api_password",
                       "bigquery_service_account_key", "connection_string"):
            self.assertNotIn(secret, self.field_lists(), secret)

    def test_it_reads_BOTH_halves_of_the_harness(self):
        """The site DB is what runs the card's SQL; the Insights data source is
        what runs ours. They are not necessarily the same database, and a
        report naming only one would answer half the question."""
        self.assertIn("db_name", self.SOURCE)
        self.assertIn("Insights Data Source v3", self.SOURCE)
        self.assertIn("is_site_db", self.field_lists())

    def test_it_runs_no_query_and_writes_nothing(self):
        called = [ast.unparse(node.func) for node in ast.walk(self.TREE)
                  if isinstance(node, ast.Call)]
        for name in ("frappe.db.sql", "insert", "save", "frappe.db.set_value"):
            self.assertNotIn(name, called, name)

    def host_of(self):
        """The real `host_of`, lifted out of the script and compiled alone.

        It is nested inside a function that needs a bench, so it is extracted
        rather than imported — but it is the code that runs, not a copy of it.
        """
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.FunctionDef) and node.name == "host_of":
                namespace = {}
                exec(compile(ast.Module(body=[node], type_ignores=[]),  # noqa: S102
                             "<host_of>", "exec"), namespace)
                return namespace["host_of"]
        self.fail("host_of is missing from which_database.py")

    def test_a_url_carrying_credentials_prints_only_its_host(self):
        """A configured URL may be `https://user:token@host/path`, and this
        output is written to be pasted into chat."""
        host_of = self.host_of()
        self.assertEqual(host_of("https://metabase.example.com/api"),
                         "metabase.example.com")
        self.assertEqual(host_of("https://someone:s3cret@metabase.example.com/x"),
                         "metabase.example.com")
        self.assertEqual(host_of(None), "(not set)")

    def test_the_api_key_is_never_read(self):
        self.assertNotIn("metabase_api_key", self.SOURCE)

    def test_no_blank_line_inside_an_indented_block(self):
        lines = self.SOURCE.splitlines()
        bad = [i + 1 for i in range(1, len(lines) - 1)
               if not lines[i].strip()
               and lines[i - 1][:1].isspace() and lines[i - 1].strip()
               and lines[i + 1][:1].isspace() and lines[i + 1].strip()]
        self.assertEqual(bad, [], f"blank line inside a block at {bad}")


class _ScriptBase(unittest.TestCase):
    """Runs the real script over a temp folder, the way bench console does.

    Exceptions are swallowed and stdout returned regardless: without a bench
    the run reaches `import frappe` and stops, which is exactly the point —
    everything these tests assert on is printed before it.
    """

    def run_script(self, files, env=None):
        import os
        import sys
        import tempfile
        saved_argv, saved_env = list(sys.argv), dict(os.environ)
        with tempfile.TemporaryDirectory() as directory:
            for name, sql in files.items():
                (pathlib.Path(directory) / f"{name}.sql").write_text(sql)
            os.environ.update({k: v.replace("<DIR>", directory)
                               for k, v in (env or {}).items()})
            sys.argv = ["reconcile_numbers.py"]
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    try:
                        exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"),  # noqa: S102
                             {}, {})
                    except Exception:
                        pass
            finally:
                os.environ.clear()
                os.environ.update(saved_env)
                sys.argv = saved_argv
            return out.getvalue()


class TestColumnMapsFromTheEnvironment(_ScriptBase):
    """`column_maps` is read from $DASHBOARD_STUDIO_COLUMN_MAPS.

    Setting it in the console before the exec cannot work — the function
    declares its own and shadows it, the same trap `directory` already carries
    a warning about — so the first version meant hand-editing the file between
    runs, which is not a thing to ask of somebody comparing numbers.
    """

    def parser(self):
        namespace = {}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), namespace)  # noqa: S102
        return namespace["_column_maps_from"]

    def test_unset_means_use_the_files_own_default(self):
        """None, not {} — the difference between "nothing was supplied" and
        "an empty mapping was supplied" is what lets the file keep a default."""
        for blank in (None, "", "   "):
            with self.subTest(repr(blank)):
                self.assertEqual(self.parser()(blank), (None, ""))

    def test_the_real_mapping_parses(self):
        """Card 2424's, exactly as reported: Metabase names an inline
        `MONTH(`d`)` item after the column it reads, and ADR-022 renames ours
        to `month_of_d`, so the two need pairing by hand."""
        maps, problem = self.parser()(
            '{"2424": {"custom_proposed_date": "month_of_custom_proposed_date",'
            ' "avg": "avg_of_custom_aggregated_performance_index_api"}}')
        self.assertEqual(problem, "")
        self.assertEqual(maps, {"2424": {
            "custom_proposed_date": "month_of_custom_proposed_date",
            "avg": "avg_of_custom_aggregated_performance_index_api"}})

    def test_a_numeric_card_id_still_keys_as_a_string(self):
        """JSON keys are strings, but a card id written as a number in a nested
        position would not match the loop's string ids."""
        maps, _ = self.parser()('{"2424": {"avg": "avg_of_x"}}')
        self.assertIn("2424", maps)

    def test_unreadable_JSON_is_a_PROBLEM_not_a_silent_empty_map(self):
        """Falling back to {} would run, report the same unpaired columns as
        last time, and read as "the mapping did not help" rather than "the
        mapping never arrived"."""
        maps, problem = self.parser()("{not json")
        self.assertIsNone(maps)
        self.assertIn("not readable as JSON", problem)

    def test_the_wrong_SHAPE_is_refused_by_name(self):
        for raw, expected in (
                ('["2424"]', "keyed by card id"),
                ('{"2424": "avg"}', "is not an object"),
                ('{"2424": {"avg": null}}', "not a column name"),
                ('{"2424": {"avg": "  "}}', "not a column name")):
            with self.subTest(raw):
                maps, problem = self.parser()(raw)
                self.assertIsNone(maps)
                self.assertIn(expected, problem)

    def test_a_bad_value_stops_the_run_before_any_query(self):
        """It is read before the site imports, so a mistyped mapping is a
        message rather than a stack trace three minutes into a run."""
        text = self.run_script({"R--10": "SELECT `a` FROM `tabX`"},
                               env={"DASHBOARD_STUDIO_SQL_DIR": "<DIR>",
                                    "DASHBOARD_STUDIO_CARDS": "10",
                                    "DASHBOARD_STUDIO_COLUMN_MAPS": "{oops"})
        self.assertIn("not readable as JSON", text)
        self.assertIn("Nothing was run", text)
        self.assertNotIn("card 10:", text)

    def test_the_run_says_where_the_maps_came_from(self):
        """Same rule as the directory and the card ids: a run that does not
        say what it read cannot be argued with."""
        text = self.run_script({"R--10": "SELECT `a` FROM `tabX`"},
                               env={"DASHBOARD_STUDIO_SQL_DIR": "<DIR>",
                                    "DASHBOARD_STUDIO_CARDS": "10",
                                    "DASHBOARD_STUDIO_COLUMN_MAPS":
                                        '{"10": {"avg": "avg_of_a"}}'})
        self.assertIn("Column maps: 1 card(s)   (from "
                      "$DASHBOARD_STUDIO_COLUMN_MAPS)", text)
