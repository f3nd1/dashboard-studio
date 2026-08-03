"""scripts/numeric_fields_typed_as_text.py must run on the live site, must not
write anything, and must judge a field by its VALUES.

Same fake-Bench approach as test_insights_schema_check: the real script is run
against a stub `frappe` in both namespace shapes, because `bench console` is an
embedded IPython where globals() and locals() differ.

The assertions that matter are the ones that make the output worth acting on:
the mistyped field is found, a field that merely LOOKS numeric by name is not
reported, and a mostly-numeric field is separated from a wholly-numeric one —
that separation is the finding, because retyping a mixed field changes what the
rows mean rather than just how they are stored.
"""

import contextlib
import io
import pathlib
import re
import sys
import types
import unittest

SCRIPT = (pathlib.Path(__file__).resolve().parents[2]
          / "scripts" / "numeric_fields_typed_as_text.py")

# The real one: a Data field on a child table holding numbers, with a handful
# of rows that are not numbers and coerce to 0 in every average today.
ACTUAL_VALUE = ["12", "8.5", "100", "N/A", "97"]
# 100% numeric: retypes cleanly, nothing to decide.
SCORE = ["1", "2", "3"]
# Named like a number, holds none. A name-based scan would report this and be
# wrong; `actual_value` is the counter-example in the other direction.
REFERENCE_NO = ["INV-0001", "INV-0002"]
# Ordinary text. Must not appear at all.
REMARKS = ["good", "needs work"]


def make_frappe():
    """A stub frappe recording every call, so writes are provable by absence."""
    calls = []
    frappe = types.ModuleType("frappe")
    fields = {
        ("QPO Child", "actual_value"): ("Data", ACTUAL_VALUE),
        ("QPO Child", "score"): ("Data", SCORE),
        ("QPO Child", "remarks"): ("Small Text", REMARKS),
        ("Invoice Log", "reference_no"): ("Data", REFERENCE_NO),
        # An Email field is a Data field with `options` — already declared as
        # something other than a bare string, so not this problem.
        ("Invoice Log", "contact"): ("Data", ["1", "2"]),
        # A real numeric field. Nothing to find; it is already typed.
        ("Invoice Log", "total"): ("Currency", ["5", "6"]),
    }

    def get_all(doctype, filters=None, fields=None, limit=None, pluck=None, **kwargs):
        calls.append(("get_all", doctype))
        if doctype == "Module Def":
            return [{"name": "Core", "app_name": "frappe"},
                    {"name": "UCC", "app_name": "ucc"}]
        if doctype == "DocType":
            return [{"name": "QPO Child", "module": "UCC", "issingle": 0, "istable": 1},
                    {"name": "Invoice Log", "module": "UCC", "issingle": 0, "istable": 0},
                    {"name": "User", "module": "Core", "issingle": 0, "istable": 0}]
        if doctype == "Unreadable":
            raise RuntimeError("TableMissingError")
        name = (fields or [None])[0]
        values = fields_or_values(doctype, name)
        return [{name: v} for v in values[:limit or len(values)]]

    def fields_or_values(doctype, fieldname):
        return fields.get((doctype, fieldname), ("Data", []))[1]

    def get_meta(doctype):
        calls.append(("get_meta", doctype))
        if doctype == "User":
            raise AssertionError("a skipped app's DocType was scanned")
        out = []
        for (dt, fieldname), (fieldtype, _) in fields.items():
            if dt != doctype:
                continue
            options = "Email" if fieldname == "contact" else None
            out.append(types.SimpleNamespace(fieldname=fieldname, fieldtype=fieldtype,
                                             options=options))
        return types.SimpleNamespace(fields=out)

    frappe.get_all = get_all
    frappe.get_meta = get_meta
    return frappe, calls


class TestNumericFieldScan(unittest.TestCase):
    def run_script(self, namespace_split=True, frappe=None):
        frappe, calls = (frappe, []) if frappe else make_frappe()
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
        self.assertIn("Numeric-looking data stored in text fields", text)

    def test_runs_under_a_plain_module_level_exec(self):
        text, _ = self.run_script(False)
        self.assertIn("Numeric-looking data stored in text fields", text)

    def test_no_blank_line_inside_an_indented_block(self):
        """IPython reading stdin ends a block at the first blank line, so a
        piped paste would stop halfway through the function."""
        lines = SCRIPT.read_text().splitlines()
        indented = re.compile(r"^\s+\S")
        bad = [i + 1 for i in range(1, len(lines) - 1)
               if not lines[i].strip()
               and indented.match(lines[i - 1]) and indented.match(lines[i + 1])]
        self.assertEqual(bad, [], f"blank line inside a block at {bad} breaks piped paste")

    def test_the_field_this_exists_for_is_found(self):
        text, _ = self.run_script()
        self.assertIn("QPO Child.actual_value", text)
        self.assertIn("4/5 sampled are numbers", text)

    def test_a_mixed_field_is_separated_from_a_clean_one(self):
        """The separation IS the finding: a clean field retypes without a
        decision, a mixed one turns silent zeros into visible bad data."""
        text, _ = self.run_script()
        clean, _, mixed = text.partition("B. Mostly numbers, some not")
        self.assertIn("QPO Child.score", clean)
        self.assertNotIn("QPO Child.actual_value", clean)
        self.assertIn("QPO Child.actual_value", mixed)
        self.assertIn("'N/A'", mixed)

    def test_a_field_that_only_LOOKS_numeric_by_name_is_not_reported(self):
        """`reference_no` is full of digits and holds no numbers. A name-based
        scan would report it and miss `actual_value` entirely."""
        text, _ = self.run_script()
        self.assertNotIn("reference_no", text)

    def test_ordinary_text_and_already_typed_fields_are_not_reported(self):
        text, _ = self.run_script()
        self.assertNotIn("remarks", text)
        self.assertNotIn("Invoice Log.total", text)

    def test_a_declared_format_is_not_a_finding(self):
        """A Data field with `options` (Email, Phone, URL) is already declared
        as something other than a bare string."""
        text, _ = self.run_script()
        self.assertNotIn("contact", text)

    def test_another_apps_doctypes_are_skipped(self):
        """get_meta raises on User in the stub — reaching it is the failure."""
        text, _ = self.run_script()
        self.assertIn("1 skipped as frappe, erpnext", text)

    def test_a_child_table_is_marked_as_one(self):
        """Both live column faults were on child tables; which kind of table a
        field is on is the first thing anyone will ask."""
        text, _ = self.run_script()
        self.assertIn("QPO Child.actual_value [child table]", text)
        self.assertNotIn("Invoice Log.reference_no [child table]", text)

    def test_an_unreadable_doctype_is_reported_not_crashed(self):
        frappe, _ = make_frappe()
        real_meta = frappe.get_meta

        def boom(doctype):
            if doctype == "Invoice Log":
                raise RuntimeError("TableMissingError")
            return real_meta(doctype)
        frappe.get_meta = boom
        text, _ = self.run_script(frappe=frappe)
        self.assertIn("Could not be read (1)", text)
        self.assertIn("Invoice Log: RuntimeError: TableMissingError", text)
        self.assertIn("QPO Child.actual_value", text)

    def test_it_writes_nothing(self):
        _, calls = self.run_script()
        made = {name for name, _ in calls}
        self.assertEqual(made - {"get_all", "get_meta"}, set(),
                         "the script called something other than a read")
        source = SCRIPT.read_text()
        for forbidden in (".insert(", ".save(", ".delete(", "db.set_value",
                          "db.sql(", "frappe.enqueue", ".submit(", "set_property"):
            self.assertNotIn(forbidden, source,
                             f"{forbidden} is a write; this script is read-only")


if __name__ == "__main__":
    unittest.main()
