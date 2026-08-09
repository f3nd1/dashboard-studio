"""Browsing the models a key can see, and the default when the field is blank.

The endpoint's job is small; its failure states are the point. A picker that
fires a doomed request when no key has been entered, or that goes quiet on a
401, is the same class of "looks like a hung page" the loading-state work fixed.

Read from `openai-python` at main rather than recalled, same rule as the
original swap: `resources/models.py` does `_get_api_list("/models",
page=SyncPage[Model], ... security={"bearer_auth": True})`, `pagination.py`
gives `SyncPage` as `{object, data: [...]}`, and `types/model.py` gives each
entry as `{id, created, object: "model", owned_by}`.
"""

import sys
import types
import unittest

from dashboard_studio.tests.fake_frappe import _make_fake_frappe, _ValidationError

# Fake keys as CONSTANTS, not inline literals: `validate_repository.py` scans
# for a key-shaped name assigned a long string literal, and is right to — the
# shape is the thing it looks for, and a test is not a reason to teach it an
# exception. (The first version of this comment spelled the pattern out and
# tripped the scanner on itself, which is the third time in this repo a guard
# has been set off by its own documentation.)
KEY = "sk-fake-for-tests"
SITE_KEY = "sk-fake-site-key"

# The real envelope, including a junk entry the reader must survive.
PAGE = {"object": "list", "data": [
    {"id": "gpt-5.5", "created": 1, "object": "model", "owned_by": "openai"},
    {"id": "gpt-5.4-mini", "created": 2, "object": "model", "owned_by": "openai"},
    {"id": "text-embedding-3-small", "created": 3, "object": "model",
     "owned_by": "openai"},
    {"no_id_at_all": True},
]}


def fake_requests(status=200, body=None, raises=None):
    calls = []

    class Response:
        status_code = status

        def json(self):
            return PAGE if body is None else body

    module = types.ModuleType("requests")

    def get(url, headers=None, timeout=None):
        calls.append(("GET", url, dict(headers or {})))
        if raises:
            raise raises
        return Response()

    def post(*a, **k):
        raise AssertionError("list_models must never POST")

    module.get, module.post = get, post
    return module, calls


class _Base(unittest.TestCase):
    roles = {"Dashboard Studio Editor"}

    def setUp(self):
        self._saved = {k: v for k, v in sys.modules.items()
                       if k in ("frappe", "requests") or k.startswith("dashboard_studio.")}
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        self.frappe = _make_fake_frappe({}, self.roles, ())
        self.frappe.conf = {}
        sys.modules["frappe"] = self.frappe

        import dashboard_studio.api.propose as propose

        self.api = propose

    def tearDown(self):
        for key in list(sys.modules):
            if key in ("frappe", "requests") or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    def run_it(self, api_key=None, **kwargs):
        module, calls = fake_requests(**kwargs)
        sys.modules["requests"] = module
        self.calls = calls
        return self.api.list_models(api_key=api_key)


class TestTheDefaultModel(unittest.TestCase):
    def test_a_blank_field_means_gpt_5_4_mini(self):
        """Read off the SDK's own `ChatModel` literal in
        `types/shared/chat_model.py`, where it sits beside its dated twin
        `gpt-5.4-mini-2026-03-17`. The undated name is the one that keeps
        working."""
        from dashboard_studio.integrations.llm.question import MODEL, write_sql_request

        self.assertEqual(MODEL, "gpt-5.4-mini")
        self.assertEqual(write_sql_request("x", {"X": {"a": "Data"}})["model"],
                         "gpt-5.4-mini")

    def test_a_named_model_still_wins(self):
        from dashboard_studio.integrations.llm.question import write_sql_request

        self.assertEqual(
            write_sql_request("x", {"X": {"a": "Data"}}, model="gpt-5.5")["model"],
            "gpt-5.5")


class TestBrowsingTheModels(_Base):
    def test_it_returns_the_ids_sorted(self):
        result = self.run_it(api_key=KEY)
        self.assertTrue(result["available"], result.get("problem"))
        self.assertEqual(result["models"],
                         ["gpt-5.4-mini", "gpt-5.5", "text-embedding-3-small"])

    def test_an_entry_with_no_id_is_skipped_rather_than_crashing(self):
        """The envelope is read defensively: a picker that raises on one odd
        row is a picker nobody can use."""
        self.assertNotIn("", self.run_it(api_key=KEY)["models"])

    def test_it_says_which_one_is_the_default(self):
        """So the list shows what leaving the field blank would pick."""
        self.assertEqual(self.run_it(api_key=KEY)["default"], "gpt-5.4-mini")

    def test_it_is_a_GET_to_the_models_endpoint_with_a_bearer_token(self):
        self.run_it(api_key=KEY)
        self.assertEqual([(verb, url) for verb, url, _ in self.calls],
                         [("GET", "https://api.openai.com/v1/models")])
        self.assertEqual(self.calls[0][2]["authorization"], "Bearer " + KEY)

    def test_no_body_is_sent(self):
        """A GET with a key and nothing else. No question, no schema, no rows —
        the egress rule holds here as everywhere."""
        self.run_it(api_key=KEY)
        self.assertEqual(set(self.calls[0][2]), {"authorization"})


class TestWhatItDoesNotDo(_Base):
    def test_NO_key_says_so_and_fires_nothing(self):
        """A request that can only come back 401 is worse than a sentence: it
        spends a round trip to say what was knowable before it started."""
        result = self.run_it(api_key=None)
        self.assertFalse(result["available"])
        self.assertIn("No API key yet", result["problem"])
        self.assertEqual(self.calls, [])

    def test_the_site_key_counts_as_a_key(self):
        self.frappe.conf = {'llm_api_key': SITE_KEY}
        result = self.run_it(api_key=None)
        self.assertTrue(result["available"])
        self.assertEqual(self.calls[0][2]["authorization"], "Bearer " + SITE_KEY)

    def test_a_bad_key_reports_the_status_and_NOT_the_key(self):
        result = self.run_it(api_key=KEY, status=401)
        self.assertFalse(result["available"])
        self.assertIn("401", result["problem"])
        self.assertNotIn(KEY, result["problem"])

    def test_a_network_failure_is_reported_inline_rather_than_raising(self):
        """Same class as the loading-state work: it must not leave the picker
        stuck with nothing said."""
        result = self.run_it(api_key=KEY, raises=OSError("connection refused"))
        self.assertFalse(result["available"])
        self.assertIn("could not be listed", result["problem"])

    def test_no_failure_path_echoes_the_key(self):
        for kwargs in ({"status": 401}, {"status": 500},
                       {"raises": OSError("boom " + KEY + " in error")},
                       {"body": {"data": []}}):
            with self.subTest(kwargs):
                result = self.run_it(api_key=KEY, **kwargs)
                self.assertFalse(result["available"])
                self.assertNotIn(KEY, result["problem"])

    def test_an_empty_list_says_so_rather_than_looking_available(self):
        result = self.run_it(api_key=KEY, body={"object": "list", "data": []})
        self.assertFalse(result["available"])
        self.assertIn("no models", result["problem"])

    def test_it_needs_the_role(self):
        self.frappe._roles = set()
        with self.assertRaises((_ValidationError, Exception)):
            self.run_it(api_key=KEY)


if __name__ == "__main__":
    unittest.main()
