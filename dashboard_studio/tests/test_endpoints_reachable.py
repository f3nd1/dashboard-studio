"""Every method the browser calls must exist and be whitelisted.

Written after a real bug: an AST-based trim of api/insights.py dropped
``@frappe.whitelist()`` from list_insights_workbooks, because
``ast.FunctionDef.lineno`` points at the ``def`` line and the trim walked back
only over ``#`` comments, never over decorators. Frappe still resolved the
dotted path, found the function unwhitelisted, and refused with
"Method Not Allowed / Login to access" — a failure no unit test could see,
because calling the function directly in Python works perfectly.

This reads the JS call sites and the Python decorators and compares them. It is
the only test here that would have caught it.
"""

import ast
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "dashboard_studio"
JS = APP / "public" / "js"

# `method: "dotted.path.to.function"` as the SPA writes it.
CALL = re.compile(r"""method:\s*["']([a-zA-Z0-9_.]+)["']""")


def js_call_sites():
    """Every server method the front end asks for, with the file it came from."""
    out = {}
    for path in sorted(JS.glob("*.js")):
        if path.name.endswith(".test.js"):
            continue
        for match in CALL.finditer(path.read_text()):
            out.setdefault(match.group(1), []).append(path.name)
    return out


def whitelisted():
    """Every function in the app carrying @frappe.whitelist(), by dotted path."""
    found = set()
    for path in sorted(APP.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        module = path.relative_to(ROOT).with_suffix("")
        dotted = ".".join(module.parts)
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                text = ast.unparse(decorator)
                if "frappe.whitelist" in text:
                    found.add(f"{dotted}.{node.name}")
    return found


class TestEndpointsReachable(unittest.TestCase):
    def test_the_front_end_calls_something(self):
        """A guard on the guard: if the regex stops matching, everything below
        passes vacuously."""
        # Named one by one: if the regex stops matching, everything below passes
        # vacuously, so this has to fail loudly rather than quietly.
        #
        # `propose_from_question` proposes and creates nothing. `convert_sql` is
        # still the only route to Insights, whether the SQL was pasted or came
        # from a proposal the user read and accepted.
        self.assertEqual(set(js_call_sites()), {
            "dashboard_studio.api.insights.list_insights_workbooks",
            "dashboard_studio.api.convert.convert_sql",
            "dashboard_studio.api.propose.propose_from_question",
            "dashboard_studio.api.propose.llm_key_is_configured",
            "dashboard_studio.api.propose.propose_tables",
        }, "the front end's call sites changed — has the call shape changed too?")

    def test_every_method_the_browser_calls_is_whitelisted(self):
        exposed = whitelisted()
        missing = {}
        for method, files in js_call_sites().items():
            if method not in exposed:
                missing[method] = files
        self.assertEqual(missing, {}, (
            "these are called from the browser but carry no @frappe.whitelist(), "
            "so Frappe answers 'Method Not Allowed / Login to access': "
            + repr(missing)
        ))

    def test_every_method_the_browser_calls_belongs_to_this_app(self):
        for method in js_call_sites():
            self.assertTrue(method.startswith("dashboard_studio."),
                            f"{method} is not this app's to call")

    def test_nothing_live_imports_the_archive(self):
        """archive/ is dead code. A live module importing it would make it
        load-bearing again without anyone deciding to.

        Checked by parsing imports, not by searching for the word: a substring
        search matched this very file's own assertion text.
        """
        offenders = []
        for path in sorted(APP.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("archive"):
                    offenders.append(f"{path.name}: from {node.module}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("archive"):
                            offenders.append(f"{path.name}: import {alias.name}")
        self.assertEqual(offenders, [], "live code reaching into archive/")


if __name__ == "__main__":
    unittest.main()
