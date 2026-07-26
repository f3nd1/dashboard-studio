"""Tests for the export-only publish path.

The load-bearing behaviour is what it REFUSES. Every refusal is asserted from
both directions: it fires when it should, and the export succeeds once the cause
is removed. Runs the real endpoint over the real demo seed, so the fixture is
the same data the pipeline walk used.

MOCK-BASED for Frappe — no live Bench.
"""

import json
import sys
import unittest

from dashboard_studio.tests import test_demo_seed as seedmod


class TestSophiaExport(unittest.TestCase):
    def setUp(self):
        self._saved = {
            k: v for k, v in sys.modules.items()
            if k == "frappe" or k.startswith("dashboard_studio.")
        }
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        self.store = {}
        self.frappe = seedmod._make_fake_frappe(self.store)
        sys.modules["frappe"] = self.frappe
        import dashboard_studio.demo as demo

        self.seed = demo.seed_demo_data()
        import dashboard_studio.api.sophia_export as export

        self.export = export
        self.A = self.seed["path_a_dashboard"]
        self.B = self.seed["path_b_dashboard"]

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("dashboard_studio."):
                sys.modules.pop(key, None)
        sys.modules.update(self._saved)

    def _chart(self, title):
        for name, row in self.store["DS Chart"].items():
            if row["chart_title"] == title:
                return name, row
        raise AssertionError(f"no chart titled {title}")

    # ------------------------------------------------------------- succeeding
    def test_path_a_exports(self):
        result = self.export.export_dashboard(self.A)
        self.assertTrue(result["ok"], result["refusals"])
        self.assertEqual(result["artefact"]["criterion"]["subcriterion"], "4.1.1")
        self.assertEqual(
            result["artefact"]["criterion"]["subcriterion_title"],
            "Pre-Course Counselling, Selection and Admissions",
        )

    def test_chart_type_is_translated_to_the_sophia_plugin(self):
        artefact = self.export.export_dashboard(self.A)["artefact"]
        self.assertEqual([v["type"] for v in artefact["live_visual_expansion"]], ["bar"])

    def test_json_is_data_not_javascript(self):
        """A chart title carrying markup must not come back as executable text."""
        name, row = self._chart("DEMO Applicants by status")
        row["chart_title"] = 'DEMO </script><img src=x onerror=alert(1)>'
        result = self.export.export_dashboard(self.A)
        self.assertTrue(result["ok"], result["refusals"])
        # json.dumps escapes it; round-tripping returns the literal text, and the
        # emitted string never contains a raw closing script tag.
        self.assertNotIn("</script>", result["json"])
        back = json.loads(result["json"])
        self.assertEqual(back["live_visual_expansion"][0]["title"], row["chart_title"])

    def test_expected_metrics_are_carried(self):
        artefact = self.export.export_dashboard(self.A)["artefact"]
        row = artefact["expected_metrics"][0]
        self.assertEqual(row["metric"], "DEMO Applicants by status")
        self.assertEqual(row["metric_status"], "Approved")

    def test_positional_binding_is_stated_in_the_artefact(self):
        artefact = self.export.export_dashboard(self.A)["artefact"]
        self.assertTrue(any("BY POSITION" in u for u in artefact["unresolved"]))

    # -------------------------------------------------------------- refusing
    def test_refuses_a_dashboard_that_is_not_publish_ready(self):
        result = self.export.export_dashboard(self.B)
        self.assertFalse(result["ok"])
        self.assertIsNone(result["artefact"])
        self.assertEqual(
            sorted({r["rule"] for r in result["refusals"]}),
            ["chart_not_validated", "chart_type_unsupported", "chart_without_metric"],
        )

    def test_refuses_an_unknown_subcriterion_by_name(self):
        self.store["DS Dashboard"][self.A]["subcriterion"] = "9.9.9"
        result = self.export.export_dashboard(self.A)
        self.assertFalse(result["ok"])
        messages = " ".join(r["message"] for r in result["refusals"])
        self.assertIn("9.9.9", messages)
        self.assertIn("scope_unknown", [r["rule"] for r in result["refusals"]])

    def test_refuses_a_missing_subcriterion(self):
        self.store["DS Dashboard"][self.A]["subcriterion"] = ""
        result = self.export.export_dashboard(self.A)
        self.assertFalse(result["ok"])
        self.assertIn("scope", [r["rule"] for r in result["refusals"]])

    def test_refuses_a_chart_type_sophia_cannot_draw(self):
        name, row = self._chart("DEMO Applicants by status")
        row["chart_type"] = "Line Chart"
        result = self.export.export_dashboard(self.A)
        self.assertFalse(result["ok"])
        refusal = [r for r in result["refusals"] if r["rule"] == "chart_type_unsupported"][0]
        self.assertIn("Line Chart", refusal["message"])
        self.assertIn("no line plugin", refusal["message"])

    def test_refusal_lists_every_cause_not_just_the_first(self):
        self.store["DS Dashboard"][self.A]["subcriterion"] = ""
        name, row = self._chart("DEMO Applicants by status")
        row["chart_type"] = "Table"
        result = self.export.export_dashboard(self.A)
        rules = sorted(r["rule"] for r in result["refusals"])
        self.assertEqual(rules, ["chart_type_unsupported", "scope"])

    def test_export_never_writes_anything(self):
        before = json.dumps(self.store, sort_keys=True, default=str)
        self.export.export_dashboard(self.A)
        self.export.export_dashboard(self.B)
        self.assertEqual(json.dumps(self.store, sort_keys=True, default=str), before)


class TestSophiaPluginTable(unittest.TestCase):
    def test_table_matches_the_doctype_select(self):
        """The copy in sophia.py and the DS Chart Select must not drift apart."""
        import json as _json
        import pathlib

        from dashboard_studio import sophia

        path = pathlib.Path(__file__).resolve().parents[1] / (
            "dashboard_studio/doctype/ds_chart/ds_chart.json"
        )
        schema = _json.loads(path.read_text())
        options = [
            f for f in schema["fields"] if f["fieldname"] == "chart_type"
        ][0]["options"].split("\n")
        self.assertEqual([o for o in options if o], list(sophia.CHART_PLUGINS))

    def test_three_types_have_no_plugin_and_each_says_why(self):
        from dashboard_studio import sophia

        self.assertEqual(sophia.unsupported_types(), ["KPI Card", "Line Chart", "Table"])
        for name in sophia.unsupported_types():
            self.assertTrue(sophia.refusal_for(name))


if __name__ == "__main__":
    unittest.main()
