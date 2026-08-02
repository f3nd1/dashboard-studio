"""Tests for DS Dashboard Section CRUD.

The load-bearing one is deletion: removing a grouping must never destroy the
charts it grouped. MOCK-BASED — endpoint logic only, no live Bench.
"""

import sys
import types
import unittest


class _PermissionError(Exception):
    pass


class _ValidationError(Exception):
    pass


class _MandatoryError(Exception):
    """Stands in for frappe.exceptions.MandatoryError."""


def _doctype_fields(doctype):
    """Field definitions from the real DocType JSON on disk.

    Reading the shipped schema rather than restating it here is what stops the
    fake and the DocType drifting apart — a reqd flag added to the JSON starts
    being enforced in tests with no test change.
    """
    import json as _json
    import os

    folder = doctype.lower().replace(" ", "_")
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "dashboard_studio", "doctype", folder, folder + ".json",
    )
    if not os.path.exists(path):
        return []          # not one of ours (e.g. Version) — nothing to enforce
    with open(path) as handle:
        return _json.load(handle)["fields"]


def _autoname_field(doctype):
    """The field an `autoname: field:x` DocType takes its primary key from.

    Four DS DocTypes name themselves from a field. A fake that invents
    "DS Metric-1" instead hides every de-duplication rule that relies on the
    natural key — see docs/TEST_FAKE_GAPS.md.
    """
    import json as _json
    import os

    folder = doctype.lower().replace(" ", "_")
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "dashboard_studio", "doctype", folder, folder + ".json",
    )
    if not os.path.exists(path):
        return None
    with open(path) as handle:
        autoname = _json.load(handle).get("autoname") or ""
    return autoname.split("field:", 1)[1] if autoname.startswith("field:") else None


class _FakeDoc:
    def __init__(self, data, store=None, doctype=None):
        object.__setattr__(self, "_data", dict(data))
        object.__setattr__(self, "_store", store)
        object.__setattr__(self, "_doctype", doctype or data.get("doctype"))

    def __getattr__(self, key):
        try:
            return self._data[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self._data[key] = value

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def as_dict(self):
        return dict(self._data)

    def _persist(self):
        table = self._store.setdefault(self._doctype, {})
        name = self._data.get("name")
        if not name:
            name = f"{self._doctype}-{len(table) + 1}"
            self._data["name"] = name
        table[name] = dict(self._data)

    def save(self):
        self._persist()
        return self

    def insert(self):
        # Frappe raises MandatoryError on insert when a reqd field is empty.
        # Without this the fake accepted documents a real site rejects — which
        # is how create_chart shipped inserting a DS Chart with no metric and
        # passed nine tests before failing on the first live Bench call.
        #
        # ponytail: insert only, not save(). Docs loaded from the fixture store
        # and re-saved are not re-checked; extend if a save-path gap turns up.
        for field in _doctype_fields(self._doctype):
            if not field.get("reqd"):
                continue
            value = self._data.get(field["fieldname"])
            if value is None or value == "":
                raise _MandatoryError(
                    f"[{self._doctype}]: {field['fieldname']}"
                )
        self._persist()
        return self


class _Row(dict):
    """Row that supports attribute access, like Frappe's _dict."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)


def _make_fake_frappe(store):
    frappe = types.ModuleType("frappe")
    frappe.PermissionError = _PermissionError
    frappe._roles = set()

    def only_for(roles, message=None):
        if isinstance(roles, str):
            roles = (roles,)
        if not (set(roles) & frappe._roles):
            raise _PermissionError(f"need one of {roles}")

    def whitelist(*a, **k):
        def deco(fn):
            return fn

        return deco

    def get_doc(doctype, name=None):
        if isinstance(doctype, dict):
            return _FakeDoc(doctype, store, doctype.get("doctype"))
        data = store.get(doctype, {}).get(name)
        if data is None:
            raise KeyError(f"{doctype} {name} not found")
        return _FakeDoc(data, store, doctype)

    def get_all(doctype, filters=None, fields=None, order_by=None, **kwargs):
        if doctype == "DS Metric":
            frappe._metric_reads = getattr(frappe, "_metric_reads", 0) + 1
        rows = list(store.get(doctype, {}).values())
        for key, value in (filters or {}).items():
            # TEST-FAKE GAP, fixed: only equality was understood, so every
            # batched ["in", [...]] read matched NOTHING and returned an empty
            # set without complaining — including publish_readiness's, which
            # reaches here through get_studio_dashboard. Third fake in this repo
            # with the same hole; each one is declared separately, which is why.
            if isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == "in":
                rows = [r for r in rows if r.get(key) in value[1]]
            else:
                rows = [r for r in rows if r.get(key) == value]
        return [_Row(r) for r in rows]

    def set_value(doctype, name, field, value):
        store.setdefault(doctype, {}).setdefault(name, {})[field] = value

    def get_value(doctype, name, field):
        return store.get(doctype, {}).get(name, {}).get(field)

    def get_meta(doctype):
        """Meta backed by the real DocType JSON, so Select options cannot drift."""
        fields = _doctype_fields(doctype)

        class _Meta:
            def get_field(self, fieldname):
                for field in fields:
                    if field["fieldname"] == fieldname:
                        return types.SimpleNamespace(**field)
                return None

        return _Meta()

    def delete_doc(doctype, name):
        store.get(doctype, {}).pop(name, None)

    def throw(msg):
        raise _ValidationError(msg)

    frappe.only_for = only_for
    frappe.whitelist = whitelist
    frappe.get_doc = get_doc
    frappe.get_all = get_all
    frappe.delete_doc = delete_doc
    frappe.throw = throw
    frappe.get_meta = get_meta
    frappe.MandatoryError = _MandatoryError
    frappe.db = types.SimpleNamespace(set_value=set_value, get_value=get_value)
    return frappe


class TestSectionApi(unittest.TestCase):
    def setUp(self):
        self._saved = {
            k: v for k, v in sys.modules.items()
            if k == "frappe" or k.startswith("dashboard_studio.api")
        }
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)

        # FIXTURE ONLY — invented dashboard, sections and charts.
        self.store = {
            "DS Dashboard Section": {
                "sec-a": {"name": "sec-a", "dashboard": "D1", "section_title": "Intake", "sort_order": 1},
                "sec-b": {"name": "sec-b", "dashboard": "D1", "section_title": "Outcomes", "sort_order": 2},
                "sec-other": {"name": "sec-other", "dashboard": "D2", "section_title": "Elsewhere",
                              "sort_order": 1},
            },
            "DS Chart": {
                "c1": {"name": "c1", "dashboard": "D1", "section": "sec-a", "chart_title": "Keep me"},
                "c2": {"name": "c2", "dashboard": "D1", "section": "sec-a", "chart_title": "Keep me too"},
                "c3": {"name": "c3", "dashboard": "D1", "section": "sec-b", "chart_title": "Elsewhere"},
            },
        }
        self.frappe = _make_fake_frappe(self.store)
        sys.modules["frappe"] = self.frappe
        import dashboard_studio.api.studio as studio

        self.studio = studio
        self.frappe._roles = {"Dashboard Studio Editor"}

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    # ---- role gating ----
    def test_viewer_cannot_write_sections(self):
        self.frappe._roles = {"Dashboard Studio Viewer"}
        for call in (
            lambda: self.studio.create_section("D1", "New"),
            lambda: self.studio.update_section("sec-a", {"section_title": "X"}),
            lambda: self.studio.reorder_sections("D1", ["sec-b", "sec-a"]),
            lambda: self.studio.delete_section("sec-a"),
        ):
            with self.assertRaises(_PermissionError):
                call()

    # ---- create ----
    def test_create_appends_after_existing_sections(self):
        created = self.studio.create_section("D1", "  Archive  ")
        self.assertEqual(created["section_title"], "Archive", "title is trimmed")
        self.assertEqual(created["sort_order"], 3, "appended after sort_order 2")
        self.assertEqual(created["dashboard"], "D1")

    def test_create_on_empty_dashboard_starts_at_one(self):
        self.assertEqual(self.studio.create_section("D-empty", "First")["sort_order"], 1)

    def test_blank_title_is_rejected(self):
        with self.assertRaises(_ValidationError):
            self.studio.create_section("D1", "   ")

    # ---- update ----
    def test_rename_and_collapse_default(self):
        self.studio.update_section("sec-a", {"section_title": "Admissions", "is_collapsed_default": 1})
        row = self.store["DS Dashboard Section"]["sec-a"]
        self.assertEqual(row["section_title"], "Admissions")
        self.assertEqual(row["is_collapsed_default"], 1)

    def test_update_ignores_fields_outside_the_allowlist(self):
        self.studio.update_section("sec-a", {"dashboard": "D2", "sort_order": 99, "section_title": "Ok"})
        row = self.store["DS Dashboard Section"]["sec-a"]
        self.assertEqual(row["dashboard"], "D1", "dashboard is not client-writable")
        self.assertEqual(row["sort_order"], 1, "sort_order changes only via reorder")

    def test_rename_to_blank_is_rejected(self):
        with self.assertRaises(_ValidationError):
            self.studio.update_section("sec-a", {"section_title": "  "})

    # ---- reorder ----
    def test_reorder_assigns_positions(self):
        result = self.studio.reorder_sections("D1", ["sec-b", "sec-a"])
        self.assertEqual(result["reordered"], 2)
        self.assertEqual(self.store["DS Dashboard Section"]["sec-b"]["sort_order"], 1)
        self.assertEqual(self.store["DS Dashboard Section"]["sec-a"]["sort_order"], 2)

    def test_reorder_rejects_sections_from_another_dashboard(self):
        with self.assertRaises(_ValidationError):
            self.studio.reorder_sections("D1", ["sec-a", "sec-other"])
        self.assertEqual(self.store["DS Dashboard Section"]["sec-a"]["sort_order"], 1,
                         "nothing applied when the request is rejected")

    # ---- delete: the charts must survive ----
    def test_delete_unassigns_charts_and_never_deletes_them(self):
        result = self.studio.delete_section("sec-a")
        self.assertEqual(result["unassigned_charts"], 2)
        self.assertNotIn("sec-a", self.store["DS Dashboard Section"], "section removed")
        # Both charts still exist, now ungrouped.
        self.assertIn("c1", self.store["DS Chart"])
        self.assertIn("c2", self.store["DS Chart"])
        self.assertEqual(self.store["DS Chart"]["c1"]["section"], "")
        self.assertEqual(self.store["DS Chart"]["c2"]["section"], "")
        # A chart in a different section is untouched.
        self.assertEqual(self.store["DS Chart"]["c3"]["section"], "sec-b")

    def test_delete_empty_section_reports_zero_charts(self):
        self.store["DS Dashboard Section"]["sec-empty"] = {
            "name": "sec-empty", "dashboard": "D1", "section_title": "Empty", "sort_order": 9
        }
        self.assertEqual(self.studio.delete_section("sec-empty")["unassigned_charts"], 0)


if __name__ == "__main__":
    unittest.main()
