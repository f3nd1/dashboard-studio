"""scripts/insights_operations_probe.py must answer two questions honestly.

Both are open because the source cannot be read from here: whether Insights
accepts a numeric dimension, and what a `mutate` expression may contain. Both
are answered from what Insights has actually STORED.

The failure that matters is not a crash — it is an answer that reads as settled
when it is not. A converter restriction removed on "no evidence" would be
exactly the guess ADR-009's first delivery was, so a negative result has to say
out loud that it is not a no. That is asserted for both halves.
"""

import contextlib
import io
import json
import pathlib
import re
import sys
import types
import unittest

SCRIPT = (pathlib.Path(__file__).resolve().parents[2]
          / "scripts" / "insights_operations_probe.py")

STRING_DIMENSION = [
    {"type": "source", "table": {"table_name": "tabX"}},
    {"type": "summarize", "measures": [{"measure_name": "count"}],
     "dimensions": [{"column_name": "status", "data_type": "String"}]},
]
MUTATE_ARITHMETIC = [
    {"type": "summarize", "measures": [{"measure_name": "avg_of_idx"}], "dimensions": []},
    {"type": "mutate", "new_name": "combined", "data_type": "Auto",
     "expression": {"type": "expression", "expression": "(avg_of_idx + avg_of_x) / 2"}},
]
# What a function-using calculated column would look like if anybody has built
# one. Invented HERE as a test input only — nothing asserts this is the real
# spelling, which is precisely what the script exists to find out.
MUTATE_WITH_FUNCTION = [
    {"type": "mutate", "new_name": "Year", "data_type": "Auto",
     "expression": {"type": "expression", "expression": "year(custom_proposed_date)"}},
]
NUMERIC_DIMENSION = [
    {"type": "summarize", "measures": [{"measure_name": "count"}],
     "dimensions": [{"column_name": "lft", "data_type": "Integer"}]},
]


def make_frappe(records, field="operations", exists=True):
    """A stub frappe recording every call, so writes are provable by absence."""
    calls = []
    frappe = types.ModuleType("frappe")

    def get_all(doctype, fields=None, **kwargs):
        calls.append(("get_all", doctype))
        return [{"name": name} for name in records]

    def get_meta(doctype):
        calls.append(("get_meta", doctype))
        return types.SimpleNamespace(fields=[
            types.SimpleNamespace(fieldname=name)
            for name in ("title", field, "is_native_query")])

    class Doc:
        def __init__(self, name):
            self.name = name

        def get(self, key, default=None):
            if key == field:
                return json.dumps(records[self.name])
            return {"title": "a query", "is_native_query": 0}.get(key, default)

    def get_doc(doctype, name=None):
        calls.append(("get_doc", doctype))
        return Doc(name)

    frappe.get_all = get_all
    frappe.get_meta = get_meta
    frappe.get_doc = get_doc
    frappe.db = types.SimpleNamespace(exists=lambda dt, name: exists)
    return frappe, calls


class _Base(unittest.TestCase):
    def run_script(self, frappe, namespace_split=True):
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
        return out.getvalue()


class TestItRuns(_Base):
    def test_runs_under_bench_consoles_split_namespaces(self):
        frappe, _ = make_frappe({"q1": STRING_DIMENSION})
        self.assertIn("What Insights has stored", self.run_script(frappe, True))

    def test_runs_under_a_plain_module_level_exec(self):
        frappe, _ = make_frappe({"q1": STRING_DIMENSION})
        self.assertIn("What Insights has stored", self.run_script(frappe, False))

    def test_no_blank_line_inside_an_indented_block(self):
        lines = SCRIPT.read_text().splitlines()
        indented = re.compile(r"^\s+\S")
        bad = [i + 1 for i in range(1, len(lines) - 1)
               if not lines[i].strip()
               and indented.match(lines[i - 1]) and indented.match(lines[i + 1])]
        self.assertEqual(bad, [], f"blank line inside a block at {bad} breaks piped paste")

    def test_a_site_without_insights_v3_says_so(self):
        frappe, _ = make_frappe({}, exists=False)
        self.assertIn("Insights v3 is not here", self.run_script(frappe))


class TestTheAnswer(_Base):
    def test_a_stored_expression_is_printed_whole(self):
        """The expression is the evidence. Summarising it would lose the one
        thing being looked for."""
        frappe, _ = make_frappe({"q1": MUTATE_WITH_FUNCTION})
        text = self.run_script(frappe)
        self.assertIn("year(custom_proposed_date)", text)
        self.assertIn("q1: Year =", text)

    def test_a_function_in_a_stored_expression_settles_the_dialect(self):
        frappe, _ = make_frappe({"q1": MUTATE_WITH_FUNCTION})
        text = self.run_script(frappe)
        self.assertIn("Functions called inside them", text)
        self.assertIn("YEAR", text)
        self.assertIn("the allowlist can widen to exactly these".upper()[:10], text.upper())

    def test_arithmetic_only_expressions_are_NOT_reported_as_a_dialect_answer(self):
        """The captured example was arithmetic. Reading "no function seen" as
        "the language has no functions" is the guess this file exists to avoid."""
        frappe, _ = make_frappe({"q1": MUTATE_ARITHMETIC})
        text = self.run_script(frappe)
        self.assertIn("NO FUNCTION SEEN", text)
        self.assertIn("that is not", text)
        self.assertNotIn("Functions called inside them", text)

    def test_no_calculated_column_at_all_says_so(self):
        frappe, _ = make_frappe({"q1": STRING_DIMENSION})
        self.assertIn("no query here has a calculated column", self.run_script(frappe))

    def test_a_numeric_dimension_settles_it(self):
        frappe, _ = make_frappe({"q1": STRING_DIMENSION, "q2": NUMERIC_DIMENSION})
        text = self.run_script(frappe)
        self.assertIn("ANSWER: yes", text)
        self.assertIn("Integer", text)
        self.assertIn("own over-restriction", text)

    def test_finding_none_is_NOT_reported_as_a_no(self):
        """The whole point. Removing a refusal on "no evidence" is the guess
        this project keeps paying for."""
        frappe, _ = make_frappe({"q1": STRING_DIMENSION})
        text = self.run_script(frappe)
        self.assertIn("NO EVIDENCE EITHER WAY", text)
        self.assertIn("that is not a no", text)
        self.assertNotIn("ANSWER: yes", text)

    def test_it_says_how_to_settle_a_negative_result(self):
        frappe, _ = make_frappe({"q1": STRING_DIMENSION})
        self.assertIn("build any query grouped by a numeric column",
                      self.run_script(frappe))

    def test_every_dimension_type_is_counted_with_an_example(self):
        frappe, _ = make_frappe({"q1": STRING_DIMENSION, "q2": NUMERIC_DIMENSION})
        text = self.run_script(frappe)
        self.assertRegex(text, r"1\s+String")
        self.assertIn("e.g. q2: lft", text)

    def test_the_operations_field_is_found_whatever_it_is_called(self):
        """Named rather than discovered, a field that differs on this version
        reads as "no queries have a summarize" — a false finding."""
        frappe, _ = make_frappe({"q1": NUMERIC_DIMENSION}, field="operations_json")
        text = self.run_script(frappe)
        self.assertIn("ANSWER: yes", text)

    def test_a_record_that_cannot_be_read_is_reported_not_fatal(self):
        frappe, _ = make_frappe({"q1": NUMERIC_DIMENSION})
        real = frappe.get_doc

        def boom(doctype, name=None):
            if name == "broken":
                raise RuntimeError("PermissionError")
            return real(doctype, name)
        frappe.get_doc = boom
        frappe.get_all = lambda dt, **k: [{"name": "broken"}, {"name": "q1"}]
        text = self.run_script(frappe)
        self.assertIn("could not read broken", text)
        self.assertIn("ANSWER: yes", text)


class TestTheStoredOrder(_Base):
    """A UI list is in the UI's display order. The record is the source of
    truth for whether a mutate precedes a summarize."""

    BEFORE = [
        {"type": "source", "table": {"table_name": "tabQuality Action"}},
        {"type": "mutate", "new_name": "year_col", "data_type": "Auto",
         "expression": {"type": "expression",
                        "expression": "year(custom_proposed_date)"}},
        {"type": "summarize", "measures": [{"measure_name": "avg_of_x"}],
         "dimensions": [{"column_name": "year_col", "data_type": "String"}]},
    ]

    def test_the_order_is_printed_from_the_record(self):
        frappe, _ = make_frappe({"q1": self.BEFORE})
        text = self.run_script(frappe)
        self.assertIn("source -> mutate -> summarize", text)

    def test_a_mutate_before_a_summarize_is_counted(self):
        frappe, _ = make_frappe({"q1": self.BEFORE})
        self.assertIn("1 of 1 put the mutate BEFORE a summarize", text := self.run_script(frappe))
        self.assertIn("from the record rather than from the UI", text)

    def test_a_mutate_after_a_summarize_is_not_counted_as_before(self):
        """The arithmetic case puts it after. Counting that as evidence for the
        other ordering would be reading the answer into the question."""
        after = [self.BEFORE[0], self.BEFORE[2], self.BEFORE[1]]
        frappe, _ = make_frappe({"q1": after})
        self.assertIn("0 of 1 put the mutate BEFORE a summarize", self.run_script(frappe))

    def test_no_mutate_anywhere_says_so(self):
        frappe, _ = make_frappe({"q1": STRING_DIMENSION})
        self.assertIn("no stored query has a mutate at all", self.run_script(frappe))


class TestItCreatesNothing(_Base):
    def test_only_reads_were_called(self):
        frappe, calls = make_frappe({"q1": STRING_DIMENSION})
        self.run_script(frappe)
        self.assertEqual({name for name, _ in calls} - {"get_all", "get_meta", "get_doc"},
                         set())

    def test_the_source_reaches_for_no_write(self):
        self.longMessage = False
        source = SCRIPT.read_text()
        for forbidden in (".insert(", ".save(", ".delete(", "db.set_value",
                          "db.sql(", "frappe.enqueue", "requests."):
            self.assertNotIn(forbidden, source,
                             f"insights_operations_probe.py contains {forbidden!r}")


if __name__ == "__main__":
    unittest.main()
