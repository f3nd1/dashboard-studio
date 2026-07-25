"""Tests for the migration-project mapping endpoints.

Covers the behaviour decided in docs/MIGRATION_PROJECT_LIFECYCLE.md: mappings are
shared per data_source (not owned by a project), canvas nodes are per-project and
replaced wholesale, and exactly one lifecycle transition is automatic
(Not Started -> Mapping on first save).

MOCK-BASED, no live Bench: a minimal fake ``frappe`` with a record store is
injected into sys.modules so the real endpoint code runs its real logic. This
verifies the endpoint LOGIC, not a live Frappe site.
"""

import sys
import types
import unittest


class _PermissionError(Exception):
    pass


class _ValidationError(Exception):
    pass


class _FakeDoc:
    """Attribute-and-dict accessible stand-in for a Frappe Document."""

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

    def append(self, key, value):
        self._data.setdefault(key, []).append(dict(value))

    def as_dict(self):
        return dict(self._data)

    def _persist(self):
        if self._store is None:
            return
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
        self._persist()
        return self


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
        if isinstance(doctype, dict):  # creation form
            return _FakeDoc(doctype, store, doctype.get("doctype"))
        data = store.get(doctype, {}).get(name)
        if data is None:
            raise KeyError(f"{doctype} {name} not found")
        return _FakeDoc(data, store, doctype)

    def get_all(doctype, filters=None, fields=None, order_by=None, **kwargs):
        rows = list(store.get(doctype, {}).values())
        for key, value in (filters or {}).items():
            rows = [r for r in rows if r.get(key) == value]
        return [dict(r) for r in rows]

    def _matches(row_value, expected):
        # Supports Frappe's ["in", [...]] filter form as well as equality.
        if isinstance(expected, (list, tuple)) and len(expected) == 2 and expected[0] == "in":
            return row_value in expected[1]
        # Model SQL equality honestly: NULL never equals ''. Collapsing the two
        # here would hide the real MariaDB behaviour this fake exists to catch.
        if row_value is None or expected is None:
            return row_value is None and expected is None
        return str(row_value) == str(expected)

    def _get_value(doctype, filters=None, fieldname="name"):
        for name, row in store.get(doctype, {}).items():
            if all(_matches(row.get(k), v) for k, v in (filters or {}).items()):
                return name if fieldname == "name" else row.get(fieldname)
        return None

    def throw(msg):
        raise _ValidationError(msg)

    frappe.only_for = only_for
    frappe.whitelist = whitelist
    frappe.get_doc = get_doc
    frappe.get_all = get_all
    frappe.throw = throw
    frappe.db = types.SimpleNamespace(get_value=_get_value)
    return frappe


class TestMigrationMappingApi(unittest.TestCase):
    def setUp(self):
        self._saved_modules = {
            k: v for k, v in sys.modules.items()
            if k == "frappe" or k.startswith("dashboard_studio.api")
        }
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)

        # FIXTURE ONLY — invented project/source names, not real UCC data.
        self.store = {
            "DS Migration Project": {
                "P1": {
                    "name": "P1", "project_name": "P1", "data_source": "Metabase (MOCK)",
                    "status": "Not Started", "canvas_nodes": [],
                },
                "P-NOSOURCE": {
                    "name": "P-NOSOURCE", "project_name": "P-NOSOURCE", "data_source": "",
                    "status": "Not Started", "canvas_nodes": [],
                },
            },
            "DS Data Mapping": {},
        }
        self.frappe = _make_fake_frappe(self.store)
        sys.modules["frappe"] = self.frappe
        import dashboard_studio.api.studio as studio

        self.studio = studio
        self._as("Dashboard Studio Editor")

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio.api"):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved_modules)

    def _as(self, *roles):
        self.frappe._roles = set(roles)

    def _mappings(self):
        return list(self.store["DS Data Mapping"].values())

    # ---- role gating ----
    def test_viewer_can_read_but_not_write(self):
        self._as("Dashboard Studio Viewer")
        self.assertIn("project", self.studio.get_migration_project("P1"))
        with self.assertRaises(_PermissionError):
            self.studio.save_migration_mapping_set("P1", [], [])

    def test_no_role_is_rejected(self):
        self._as("Some Other Role")
        with self.assertRaises(_PermissionError):
            self.studio.get_migration_project("P1")
        with self.assertRaises(_PermissionError):
            self.studio.save_migration_mapping_set("P1", [], [])

    # ---- the one automatic transition ----
    def test_first_save_moves_not_started_to_mapping(self):
        result = self.studio.save_migration_mapping_set(
            "P1", [{"external_table": "tabStudent Applicant", "target_doctype": "Student Applicant"}], []
        )
        self.assertEqual(result["status"], "Mapping")
        self.assertEqual(self.store["DS Migration Project"]["P1"]["status"], "Mapping")

    def test_later_states_are_not_auto_advanced(self):
        for state in ("Mapping", "Validating", "Ready to Publish", "Published"):
            self.store["DS Migration Project"]["P1"]["status"] = state
            result = self.studio.save_migration_mapping_set(
                "P1", [{"external_table": "tabX", "target_doctype": "X"}], []
            )
            self.assertEqual(result["status"], state, f"{state} must not auto-advance")

    def test_saving_no_mappings_does_not_advance_status(self):
        result = self.studio.save_migration_mapping_set("P1", [], [])
        self.assertEqual(result["status"], "Not Started")

    # ---- upsert on (data_source, external_table, external_field) ----
    def test_new_mapping_is_inserted_with_project_data_source(self):
        self.studio.save_migration_mapping_set(
            "P1",
            [{"external_table": "tabStudent Applicant", "target_doctype": "Student Applicant"}],
            [],
        )
        rows = self._mappings()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["data_source"], "Metabase (MOCK)")
        self.assertEqual(rows[0]["external_table"], "tabStudent Applicant")
        self.assertEqual(rows[0]["mapping_status"], "Suggested")

    def test_existing_mapping_is_updated_not_duplicated(self):
        row = {"external_table": "tabStudent Applicant", "target_doctype": "Student Applicant"}
        self.studio.save_migration_mapping_set("P1", [row], [])
        self.studio.save_migration_mapping_set(
            "P1", [dict(row, mapping_status="Confirmed")], []
        )
        rows = self._mappings()
        self.assertEqual(len(rows), 1, "same natural key must upsert, not duplicate")
        self.assertEqual(rows[0]["mapping_status"], "Confirmed")

    def test_existing_mapping_with_null_external_field_is_updated(self):
        # A mapping created through the Frappe UI can store NULL rather than ""
        # for a blank Data field; the upsert must still match it.
        self.store["DS Data Mapping"]["pre"] = {
            "name": "pre", "data_source": "Metabase (MOCK)",
            "external_table": "tabStudent Applicant", "external_field": None,
            "target_doctype": "Student Applicant", "mapping_status": "Suggested",
        }
        self.studio.save_migration_mapping_set(
            "P1",
            [{"external_table": "tabStudent Applicant", "target_doctype": "Student Applicant",
              "mapping_status": "Confirmed"}],
            [],
        )
        rows = self._mappings()
        self.assertEqual(len(rows), 1, "NULL external_field must upsert, not duplicate")
        self.assertEqual(rows[0]["mapping_status"], "Confirmed")

    def test_rows_without_external_table_are_skipped(self):
        result = self.studio.save_migration_mapping_set(
            "P1", [{"external_table": "  ", "target_doctype": "X"}, "not-a-dict"], []
        )
        self.assertEqual(result["saved_mappings"], 0)
        self.assertEqual(self._mappings(), [])

    # ---- canvas nodes ----
    def test_canvas_nodes_are_sanitized_and_replaced_wholesale(self):
        self.studio.save_migration_mapping_set(
            "P1", [],
            [
                {"node_id": "src:tabX", "node_type": "Source Table", "pos_x": 20, "pos_y": 16,
                 "parent": "HACK", "doctype": "Evil"},
                {"node_id": "  ", "node_type": "Source Table", "pos_x": 0, "pos_y": 0},
            ],
        )
        nodes = self.store["DS Migration Project"]["P1"]["canvas_nodes"]
        self.assertEqual(
            nodes,
            [{"node_id": "src:tabX", "node_type": "Source Table", "pos_x": 20, "pos_y": 16}],
        )

        self.studio.save_migration_mapping_set(
            "P1", [], [{"node_id": "tgt:Y", "node_type": "Target DocType", "pos_x": 1, "pos_y": 2}]
        )
        nodes = self.store["DS Migration Project"]["P1"]["canvas_nodes"]
        self.assertEqual(len(nodes), 1, "layout is replaced wholesale, not appended")
        self.assertEqual(nodes[0]["node_id"], "tgt:Y")

    # ---- SQL kept as evidence ----
    def test_analyzed_sql_is_recorded_as_evidence(self):
        result = self.studio.save_migration_mapping_set(
            "P1", [], [],
            [{"source_sql": "SELECT COUNT(*) FROM `tabStudent Applicant`",
              "supported": True, "reasons": []},
             {"source_sql": "SELECT ... nested ...", "supported": False,
              "reasons": ["subquery / nested SELECT", "multiple joins (2)"]}],
        )
        self.assertEqual(result["recorded_queries"], 2)
        rows = self.store["DS Migration Project"]["P1"]["source_queries"]
        self.assertEqual(rows[0]["supported"], 1)
        # The unsupported query keeps its reasons — it IS the review evidence.
        self.assertEqual(rows[1]["supported"], 0)
        self.assertEqual(rows[1]["reasons"], "subquery / nested SELECT; multiple joins (2)")

    def test_identical_sql_is_not_recorded_twice(self):
        query = [{"source_sql": "SELECT COUNT(*) FROM `tabX`", "supported": True, "reasons": []}]
        self.studio.save_migration_mapping_set("P1", [], [], query)
        result = self.studio.save_migration_mapping_set("P1", [], [], query)
        self.assertEqual(result["recorded_queries"], 0, "re-saving must not duplicate evidence")
        self.assertEqual(len(self.store["DS Migration Project"]["P1"]["source_queries"]), 1)

    def test_evidence_accumulates_across_saves(self):
        self.studio.save_migration_mapping_set(
            "P1", [], [], [{"source_sql": "SELECT 1 FROM `tabA`", "supported": True}])
        self.studio.save_migration_mapping_set(
            "P1", [], [], [{"source_sql": "SELECT 2 FROM `tabB`", "supported": True}])
        rows = self.store["DS Migration Project"]["P1"]["source_queries"]
        self.assertEqual(len(rows), 2, "evidence appends, it does not replace")

    # ---- guards / reads ----
    def test_project_without_data_source_is_rejected(self):
        with self.assertRaises(_ValidationError):
            self.studio.save_migration_mapping_set(
                "P-NOSOURCE", [{"external_table": "tabX", "target_doctype": "X"}], []
            )

    def test_get_project_returns_mappings_scoped_to_its_data_source(self):
        self.studio.save_migration_mapping_set(
            "P1", [{"external_table": "tabStudent Applicant", "target_doctype": "Student Applicant"}], []
        )
        # A mapping belonging to a different source must not leak into P1.
        self.store["DS Data Mapping"]["other"] = {
            "name": "other", "data_source": "Other Source", "external_table": "tabOther",
        }
        out = self.studio.get_migration_project("P1")
        tables = [m["external_table"] for m in out["mappings"]]
        self.assertEqual(tables, ["tabStudent Applicant"])

    def test_json_string_payloads_are_accepted(self):
        # frappe.call sends arrays as JSON strings.
        result = self.studio.save_migration_mapping_set(
            "P1",
            '[{"external_table": "tabStudent Applicant", "target_doctype": "Student Applicant"}]',
            '[{"node_id": "src:tabStudent Applicant", "node_type": "Source Table", "pos_x": 1, "pos_y": 2}]',
        )
        self.assertEqual(result["saved_mappings"], 1)
        self.assertEqual(len(self.store["DS Migration Project"]["P1"]["canvas_nodes"]), 1)


if __name__ == "__main__":
    unittest.main()
