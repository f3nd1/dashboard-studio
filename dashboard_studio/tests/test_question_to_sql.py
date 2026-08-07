"""The question box: what leaves the site, what comes back, and what is claimed.

The feature's whole risk is that a model names a real column of the right type
that is not the one somebody meant, and every existing check passes. Nothing
here can fix that. What these tests hold in place is the three things that make
it survivable: the model's prose never reaches the user, the validation strip
says what it did NOT check, and a join that multiplies rows is named.
"""

import ast
import pathlib
import unittest

from dashboard_studio.integrations.llm import question as Q
from dashboard_studio.integrations.metabase.sql_ops import rows_multiplied_by

SCHEMA = {"Sales Invoice": {"name": "String", "agent_name": "String",
                            "sales_income": "Decimal", "posting_date": "Date"}}


def reply(text):
    return {"content": [{"type": "text", "text": text}]}


class TestNothingButNamesAndTypesLeaves(unittest.TestCase):
    """The egress rule, enforced structurally rather than by care."""

    TREE = ast.parse(pathlib.Path(Q.__file__).read_text())

    def imported(self):
        """Every module this one imports, read from the syntax tree.

        Not grepped: the first version of this test searched the source text and
        failed on its own docstring, which is the same fault it exists to
        prevent — a check that reads prose as if it were code."""
        names = set()
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        return names

    def test_the_module_cannot_reach_a_database_at_all(self):
        """It does not import frappe, so there is no path from here to a row.
        That is the guarantee — not a review that happened to find no query."""
        self.assertNotIn("frappe", self.imported())
        self.assertFalse([name for name in self.imported()
                          if name.startswith("frappe")])

    def test_the_request_carries_only_what_it_was_given(self):
        payload = Q.write_sql_request("which agent sold most", SCHEMA)
        sent = repr(payload)
        for column in ("agent_name", "sales_income", "posting_date"):
            self.assertIn(column, sent)
        # Nothing resembling a value: the schema holds types, and there is
        # nowhere for a value to come from.
        self.assertIn("Decimal", sent)
        self.assertIn("which agent sold most", sent)

    def test_the_first_pass_sends_names_and_no_columns(self):
        """A site has hundreds of DocTypes. Sending every column of all of them
        to answer a question about two is egress nobody agreed to."""
        payload = Q.pick_doctypes_request("x", ["Sales Invoice", "Item"])
        self.assertIn("Sales Invoice", repr(payload))
        self.assertNotIn("sales_income", repr(payload))

    def test_no_credential_is_reachable_from_here(self):
        """It imports nothing that could hold one, and takes none as an
        argument — the HTTP call lives in the api module with the key."""
        self.assertEqual(self.imported() & {"os", "frappe", "requests"}, set())


class TestReadingTheReply(unittest.TestCase):
    def test_plain_sql_comes_back_as_sql(self):
        sql, refusal = Q.sql_from_response(reply("SELECT `a` FROM `tabX`"))
        self.assertEqual(sql, "SELECT `a` FROM `tabX`")
        self.assertEqual(refusal, "")

    def test_a_code_fence_is_stripped(self):
        sql, _ = Q.sql_from_response(reply("```sql\nSELECT `a` FROM `tabX`\n```"))
        self.assertEqual(sql, "SELECT `a` FROM `tabX`")

    def test_CANNOT_is_passed_through_as_the_refusal(self):
        """The model saying it cannot answer is it doing the right thing, and
        its sentence is better than anything this could invent."""
        sql, refusal = Q.sql_from_response(reply("CANNOT: there is no income column"))
        self.assertEqual(sql, "")
        self.assertEqual(refusal, "there is no income column")

    def test_anything_that_is_not_a_SELECT_refuses(self):
        for text in ("DELETE FROM `tabX`", "Here is your query!", ""):
            with self.subTest(text):
                sql, refusal = Q.sql_from_response(reply(text))
                self.assertEqual(sql, "")
                self.assertTrue(refusal)

    def test_a_shape_it_does_not_recognise_refuses_rather_than_raising(self):
        for response in (None, {}, {"content": "text"}, {"content": [{"type": "tool"}]}):
            with self.subTest(repr(response)):
                sql, refusal = Q.sql_from_response(response)
                self.assertEqual(sql, "")
                self.assertTrue(refusal)

    def test_a_doctype_it_invented_is_dropped(self):
        """A name that does not exist would otherwise reach `get_meta` and come
        back as "There is no DocType called …" — a true message about the wrong
        thing."""
        chosen = Q.doctypes_from_response(reply("Sales Invoice\nSales Ledger"),
                                          ["Sales Invoice", "Item"])
        self.assertEqual(chosen, ["Sales Invoice"])

    def test_NONE_means_none(self):
        self.assertEqual(Q.doctypes_from_response(reply("NONE"), ["Item"]), [])


class TestAJoinThatMultipliesRows(unittest.TestCase):
    """The likeliest way a proposal is quietly wrong.

    Joining a parent to its child table gives the parent one row per child, so a
    SUM after it counts the parent's value once per child. The number is too big
    and looks entirely ordinary.
    """

    def operations(self, table="tabSales Invoice Item", summarize=True):
        out = [{"type": "source", "table": {"type": "table", "table_name": "tabSales Invoice"}},
               {"type": "join", "join_type": "left",
                "table": {"type": "table", "table_name": table},
                "select_columns": [], "join_condition": {}}]
        if summarize:
            out.append({"type": "summarize", "measures": [], "dimensions": []})
        return out

    def test_a_child_table_join_under_an_aggregate_is_named(self):
        self.assertEqual(
            rows_multiplied_by(self.operations(), {"Sales Invoice Item"}),
            ["tabSales Invoice Item"])

    def test_a_join_to_an_ordinary_doctype_is_not(self):
        self.assertEqual(rows_multiplied_by(self.operations("tabCustomer"),
                                            {"Sales Invoice Item"}), [])

    def test_without_an_aggregate_there_is_nothing_to_inflate(self):
        """Fan-out only misleads when something is being totalled. Warning about
        a plain join would train people to ignore the warning."""
        self.assertEqual(
            rows_multiplied_by(self.operations(summarize=False), {"Sales Invoice Item"}),
            [])

    def test_every_multiplying_join_is_named_not_just_the_first(self):
        operations = self.operations()
        operations.insert(2, {"type": "join", "join_type": "left",
                              "table": {"type": "table", "table_name": "tabSales Taxes"},
                              "select_columns": [], "join_condition": {}})
        self.assertEqual(
            rows_multiplied_by(operations, {"Sales Invoice Item", "Sales Taxes"}),
            ["tabSales Invoice Item", "tabSales Taxes"])

    def test_non_list_input_is_a_programming_error(self):
        with self.assertRaises(TypeError):
            rows_multiplied_by("not a list", set())


class TestTheModuleThatCreatesNothing(unittest.TestCase):
    """`propose_from_question` must have no write path in it — not a flag
    defaulting to false, no call that inserts.

    Read as a SYNTAX TREE rather than as text. The first version of these tests
    grepped the source and failed on its own docstring, which is the same fault
    in miniature: a check that reads prose as if it were code proves nothing
    about what runs.
    """

    PATH = pathlib.Path(__file__).resolve().parents[1] / "api" / "propose.py"
    TREE = ast.parse(PATH.read_text())

    def called_names(self):
        """Every function call in the module, as written: `a.b.c` or `f`."""
        out = []
        for node in ast.walk(self.TREE):
            if not isinstance(node, ast.Call):
                continue
            parts, cursor = [], node.func
            while isinstance(cursor, ast.Attribute):
                parts.append(cursor.attr)
                cursor = cursor.value
            if isinstance(cursor, ast.Name):
                parts.append(cursor.id)
            if parts:
                out.append(".".join(reversed(parts)))
        return out

    def test_it_never_inserts_saves_or_creates(self):
        banned = {"frappe.get_doc", "frappe.new_doc", "insert", "save",
                  "convert_sql", "create_insights_query", "db_set",
                  "frappe.db.set_value", "frappe.db.sql", "frappe.db.commit"}
        called = self.called_names()
        for name in called:
            self.assertNotIn(name, banned, f"{name} is a write path")
            self.assertFalse(name.endswith((".insert", ".save")), name)

    def test_exactly_one_outbound_call_and_its_url_is_checked(self):
        """The shape `metabase_export_sql.py` uses: one post, its URL asserted
        at the call site, so a second endpoint cannot be added quietly."""
        posts = [name for name in self.called_names() if name.endswith(".post")]
        self.assertEqual(posts, ["requests.post"])
        self.assertIn('if API_URL != "https://api.anthropic.com/v1/messages"',
                      self.PATH.read_text())

    def test_the_reply_carries_no_free_text_from_the_model(self):
        """The whole safety argument. Every key the endpoint returns is listed
        here on purpose: `sql` and `operations` are what will run and are
        checkable, `reasons` are this converter's own words. Adding a key
        holding the model's prose is what would let a summary describe its
        intention while the operations did something else — so it fails here."""
        returns = [node for node in ast.walk(self.TREE)
                   if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)]
        self.assertTrue(returns, "expected the endpoint to return dicts")
        allowed = {"supported", "sql", "operations", "reasons", "checked",
                   "not_checked", "multiplied"}
        for node in returns:
            keys = {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
            self.assertEqual(keys, allowed, f"unexpected reply keys: {keys ^ allowed}")

    def test_the_strip_states_what_it_did_NOT_check(self):
        """A strip that reports "checked" without saying what it did NOT check
        implies an assurance nobody can give. Read from the tree because the
        module imports frappe and there is no site here."""
        assigned = [node for node in ast.walk(self.TREE)
                    if isinstance(node, ast.Assign)
                    and any(getattr(t, "id", "") == "NOT_CHECKED" for t in node.targets)]
        self.assertEqual(len(assigned), 1)
        self.assertIn("whether these are the columns you meant",
                      ast.literal_eval(assigned[0].value))

    def test_the_key_is_read_from_site_config_and_never_echoed(self):
        source = self.PATH.read_text()
        self.assertIn('frappe.conf.get("llm_api_key")', source)
        # No f-string or format anywhere puts the key into a message.
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.JoinedStr):
                text = ast.unparse(node)
                self.assertNotIn("key", text, f"the key may reach a message: {text}")


if __name__ == "__main__":
    unittest.main()
