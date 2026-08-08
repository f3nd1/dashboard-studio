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
    """OpenAI's chat-completion shape: choices[].message.content.

    Read from `types/chat/chat_completion.py` in openai-python, not recalled."""
    return {"choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": text}}]}


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

    def test_the_request_is_the_shape_openais_own_sdk_documents(self):
        """Verified against openai-python at main rather than recalled:
        `max_tokens` is deprecated in favour of `max_completion_tokens`, and the
        instruction message is role "developer" in the current chat example."""
        payload = Q.write_sql_request("x", SCHEMA)
        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertIn("max_completion_tokens", payload)
        self.assertNotIn("max_tokens", payload)
        self.assertEqual([m["role"] for m in payload["messages"]],
                         ["developer", "user"])
        self.assertNotIn("system", payload)

    def test_a_supplied_model_is_used_and_blank_means_the_default(self):
        """Free text, session-only, blank behaves exactly as before the field
        existed."""
        self.assertEqual(Q.write_sql_request("x", SCHEMA, "gpt-5.4-mini")["model"],
                         "gpt-5.4-mini")
        for blank in (None, "", "   "):
            with self.subTest(repr(blank)):
                self.assertEqual(Q.write_sql_request("x", SCHEMA, blank)["model"],
                                 Q.MODEL)
        self.assertEqual(Q.pick_doctypes_request("x", ["A"], "gpt-5.4")["model"],
                         "gpt-5.4")

    def test_the_prompt_states_the_dialect_the_parser_accepts(self):
        """The model writes SQL for a PARSER, not for a reader. Left to write
        idiomatically it produced `YEAR(si.posting_date)` and `ORDER BY total`,
        both of which refuse — so the subset is described rather than the parser
        widened to every dialect a model might pick."""
        prompt = Q.write_sql_request("x", SCHEMA)["messages"][0]["content"]
        self.assertIn("BACKTICKED", prompt)
        self.assertIn("`si`.`posting_date`", prompt)
        self.assertIn("sum_of_<column>", prompt)
        self.assertIn("never a SELECT-list alias", prompt)

    def test_a_shape_it_does_not_recognise_refuses_rather_than_raising(self):
        for response in (None, {}, {"choices": "text"}, {"choices": []},
                         {"choices": [{"message": None}]},
                         {"content": [{"type": "text", "text": "SELECT 1"}]}):
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
        self.assertIn('if API_URL != "https://api.openai.com/v1/chat/completions"',
                      self.PATH.read_text())

    def test_the_reply_carries_no_free_text_from_the_model(self):
        """The whole safety argument. Every key the endpoint returns is listed
        here on purpose: `sql` and `operations` are what will run and are
        checkable, `reasons` are this converter's own words. Adding a key
        holding the model's prose is what would let a summary describe its
        intention while the operations did something else — so it fails here."""
        # Both the success shape and the shared refusal shape. `_refused` exists
        # so every refusal returns one set of keys; walking only the endpoint
        # would stop checking the moment a return moved into it.
        wanted = {"propose_from_question", "_refused"}
        endpoints = [node for node in ast.walk(self.TREE)
                     if isinstance(node, ast.FunctionDef) and node.name in wanted]
        self.assertEqual({n.name for n in endpoints}, wanted)
        returns = [node for endpoint in endpoints
                   for node in ast.walk(endpoint)
                   if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)]
        self.assertTrue(returns, "expected the endpoint to return dicts")
        # `doctypes` is the tables the USER confirmed, echoed back so the page
        # can show what the query was built over. Names, not prose.
        allowed = {"supported", "sql", "doctypes", "operations", "reasons",
                   "checked", "not_checked", "multiplied"}
        for node in returns:
            keys = {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
            self.assertEqual(keys, allowed, f"unexpected reply keys: {keys ^ allowed}")

    def test_the_endpoint_REQUIRES_the_tables_and_never_picks_them(self):
        """The wrong-DocType failure in one assertion: there is no path through
        `propose_from_question` that chooses a table. `doctypes` has no default,
        so a caller cannot omit it, and the picking call lives in its own
        read-only endpoint whose answer a person confirms."""
        signatures = {node.name: node for node in ast.walk(self.TREE)
                      if isinstance(node, ast.FunctionDef)}
        args = signatures["propose_from_question"].args
        required = args.args[:len(args.args) - len(args.defaults)]
        self.assertEqual([a.arg for a in required], ["question", "doctypes"])
        # And it does not call the picker itself. Scoped to this function's own
        # body: the module DOES call it, from `propose_tables`, which is the
        # point — the picking lives where a person confirms it.
        own = [ast.unparse(n.func) for n in ast.walk(signatures["propose_from_question"])
               if isinstance(n, ast.Call)]
        self.assertNotIn("pick_doctypes_request", own)
        self.assertNotIn("doctypes_from_response", own)

    def test_the_picking_step_is_its_own_read_only_endpoint(self):
        source = self.PATH.read_text()
        self.assertIn("def propose_tables(", source)
        picker = [node for node in ast.walk(self.TREE)
                  if isinstance(node, ast.FunctionDef) and node.name == "propose_tables"]
        self.assertEqual(len(picker), 1)
        returns = [n for n in ast.walk(picker[0])
                   if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]
        # Names only. A rationale from the model would describe its intention,
        # and it is the choice that has to be checked.
        self.assertEqual(
            [{k.value for k in n.value.keys} for n in returns], [{"doctypes"}])

    def test_widening_past_the_confirmed_tables_refuses_by_name(self):
        """The server half, and the half that actually bites. Before this, the
        columns were re-typed from whatever tables the SQL mentioned, so a model
        that reached past the confirmed set was accepted."""
        source = self.PATH.read_text()
        self.assertIn("if doctype not in chosen", source)
        self.assertIn("not among the tables you", source)
        # And the columns are typed from the CONFIRMED set, never from whatever
        # the SQL mentioned — that re-typing was the gap.
        self.assertIn("columns = {doctype: _table_columns(doctype) for doctype in chosen}",
                      source)
        self.assertEqual(source.count("_table_columns(doctype)"), 1)

    def test_a_doctype_that_does_not_exist_refuses_before_it_is_used(self):
        source = self.PATH.read_text()
        self.assertIn('frappe.db.exists("DocType", name)', source)

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

    def test_the_key_is_read_from_the_request_then_site_config(self):
        """A key typed into the page wins; the site's setting is the fallback."""
        source = self.PATH.read_text()
        self.assertIn('frappe.conf.get("llm_api_key")', source)
        self.assertIn('(api_key or "").strip() or frappe.conf.get("llm_api_key")', source)

    def test_NEITHER_key_can_reach_a_message(self):
        """Covers the site key AND the one the request supplies. Both are bound
        to names containing "key", and no f-string anywhere in the module may
        mention one — a thrown message travels to the browser."""
        bound = set()
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.arg) and "key" in node.arg:
                bound.add(node.arg)
            if isinstance(node, ast.Name) and "key" in node.id:
                bound.add(node.id)
        # The guard is worthless if nothing is bound to a key-shaped name.
        self.assertIn("api_key", bound)
        self.assertIn("key", bound)
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.JoinedStr):
                text = ast.unparse(node)
                for name in bound:
                    self.assertNotIn(name, text,
                                     f"the key may reach a message: {text}")

    def test_the_configured_check_returns_a_boolean_and_nothing_else(self):
        """It exists so the page can hide the field. It must never hand back the
        key, part of it, or its length."""
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.FunctionDef) and node.name == "llm_key_is_configured":
                returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
                self.assertEqual(len(returns), 1)
                self.assertEqual(ast.unparse(returns[0].value),
                                 "{'configured': bool(frappe.conf.get('llm_api_key'))}")
                return
        self.fail("llm_key_is_configured is missing")


if __name__ == "__main__":
    unittest.main()
