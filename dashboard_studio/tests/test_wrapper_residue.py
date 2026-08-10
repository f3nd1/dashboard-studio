"""scripts/wrapper_residue.py — the capture tool for wrapper-rule work.

Its output is the evidence a new rule gets written against, so the tests are
about it being runnable where the files are (bench console, all three paste
modes) and about it printing the three things that matter: the raw SQL, the
residue the existing rules leave, and the refusal reasons — for the card ids
asked for and no guesses about the rest.
"""

import contextlib
import io
import os
import pathlib
import re
import sys
import tempfile
import unittest

SCRIPT = (pathlib.Path(__file__).resolve().parents[2]
          / "scripts" / "wrapper_residue.py")

WRAPPED = ("SELECT `w`.`a` AS `a`, AVG(`w`.`s`) AS `avg` FROM ( SELECT "
           "`tabX`.`a` AS `a`, `J`.`s` AS `s` FROM ( SELECT * FROM `tabX` ) "
           "AS `tabX` INNER JOIN ( SELECT * FROM `tabY` WHERE `docstatus` = 1 ) "
           "AS `J` ON `J`.`parent` = `tabX`.`name` ) AS `w` GROUP BY `w`.`a`")


class _Base(unittest.TestCase):
    def run_script(self, files, argv=None, env=None, namespace_split=True):
        saved_argv, saved_env = list(sys.argv), dict(os.environ)
        with tempfile.TemporaryDirectory() as directory:
            for name, sql in files.items():
                (pathlib.Path(directory) / f"{name}.sql").write_text(sql)
            os.environ.update({k: v.replace("<DIR>", directory)
                               for k, v in (env or {}).items()})
            sys.argv = (["wrapper_residue.py"]
                        + [a.replace("<DIR>", directory) for a in (argv or [])])
            out = io.StringIO()
            try:
                source = SCRIPT.read_text()
                with contextlib.redirect_stdout(out):
                    if namespace_split:
                        exec(compile(source, str(SCRIPT), "exec"), {}, {})
                    else:
                        exec(compile(source, str(SCRIPT), "exec"), {})
            finally:
                os.environ.clear()
                os.environ.update(saved_env)
                sys.argv = saved_argv
            return out.getvalue()


class TestItRuns(_Base):
    def test_runs_under_bench_consoles_split_namespaces(self):
        text = self.run_script({"R--10": WRAPPED},
                               env={"DASHBOARD_STUDIO_SQL_DIR": "<DIR>",
                                    "DASHBOARD_STUDIO_CARDS": "10"})
        self.assertIn("card 10: R--10.sql", text)

    def test_runs_as_a_plain_script_with_argv(self):
        text = self.run_script({"R--10": WRAPPED}, argv=["<DIR>", "10"],
                               namespace_split=False)
        self.assertIn("card 10: R--10.sql", text)

    def test_no_blank_line_inside_an_indented_block(self):
        """IPython reading stdin ends a block at the first blank line."""
        lines = SCRIPT.read_text().splitlines()
        indented = re.compile(r"^\s+\S")
        bad = [i + 1 for i in range(1, len(lines) - 1)
               if not lines[i].strip()
               and indented.match(lines[i - 1]) and indented.match(lines[i + 1])]
        self.assertEqual(bad, [], f"blank line inside a block at {bad}")

    def test_missing_arguments_print_usage_rather_than_crashing(self):
        self.assertIn("Usage", self.run_script({}, argv=[]))


class TestWhatItPrints(_Base):
    def output(self):
        return self.run_script({"R--10": WRAPPED},
                               env={"DASHBOARD_STUDIO_SQL_DIR": "<DIR>",
                                    "DASHBOARD_STUDIO_CARDS": "10,77"})

    def test_the_raw_sql_verbatim(self):
        self.assertIn("( SELECT * FROM `tabX` ) AS `tabX`", self.output())

    def test_the_residue_shows_what_the_rules_left(self):
        """The identity projection unwraps; the filtered one survives. The
        residue is the thing a NEW rule receives, which is the whole point."""
        text = self.output()
        residue = text.split("RESIDUE", 1)[1].split("REASONS", 1)[0]
        self.assertIn("`tabX` AS `tabX`", residue)
        self.assertIn("( SELECT * FROM `tabY` WHERE `docstatus` = 1 )", residue)

    def test_the_refusal_reasons(self):
        self.assertIn("subquery", self.output().split("REASONS", 1)[1])

    def test_a_card_with_no_file_says_so_by_id(self):
        self.assertIn("card 77: NO FILE matching *--77.sql", self.output())

    def test_it_writes_and_executes_nothing(self):
        source = SCRIPT.read_text()
        for forbidden in ("write_text", ".insert(", "requests.", "db.sql(",
                          "convert_sql(", "frappe"):
            self.assertNotIn(forbidden, source,
                             f"wrapper_residue.py contains {forbidden!r}")


if __name__ == "__main__":
    unittest.main()
