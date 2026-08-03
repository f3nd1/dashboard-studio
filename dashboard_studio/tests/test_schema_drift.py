"""A standing category, not a bug-by-bug list: every column this converter
emits must exist in the table it names.

Twice now a converted query has been written with a column that is not on the
table, and each was found by a person opening the query in Insights and reading
the error:

  "Column '_comments' is not found in table"        — an OPTIONAL framework
      column assumed present on every table.
  "Column 'corrective_action' is not found in table" — a DocType field that
      outlived the column it used to have.

Different causes, one category: something built a column list from a source
that disagrees with the table. Testing the specific column each time only
proves that column is fixed, so these tests do not name a column at all. They
build a table whose schema DRIFTS from its DocType, run whole queries through
the real converter, and assert generically that nothing outside the real column
list appears ANYWHERE in the operations — source, join, select_columns, join
condition, filters, dimensions or measures.

Add a scenario here when a new shape of drift appears. Do not add a test for
the column that happened to expose it.
"""

import unittest

from dashboard_studio.integrations.metabase.parser import analyze_sql
from dashboard_studio.integrations.metabase.sql_ops import (
    columns_from_meta,
    operations_from_sql,
)

# What the DocTypes DEFINE. Deliberately richer than the tables below.
FIELDS = {
    "Parent": [("title", "Data"), ("status", "Select"), ("layout", "Section Break")],
    "Child": [("metric", "Data"), ("score", "Float"),
              # Defined, and long gone from the table — the corrective_action shape.
              ("corrective_action", "Text"), ("data", "Text")],
    "Other": [("code", "Data")],
}

# What the TABLES actually have. Note the drift in BOTH directions: the parent
# carries optional framework columns the child does not, and the child is
# missing two fields its DocType still declares.
FRAMEWORK = ["name", "owner", "creation", "modified", "modified_by",
             "docstatus", "idx", "parent", "parentfield", "parenttype"]
TABLES = {
    "Parent": FRAMEWORK + ["_comments", "_assign", "title", "status"],
    "Child": FRAMEWORK + ["metric", "score"],
    "Other": FRAMEWORK + ["code"],
}

COLUMNS = {name: columns_from_meta(FIELDS[name], TABLES[name]) for name in TABLES}


def columns_named_in(operation):
    """Every column name an operation mentions, wherever it hides.

    Written as a walk rather than a list of known keys: an operation shape this
    does not recognise contributes nothing, which would make the assertion pass
    vacuously — so unknown shapes raise instead.
    """
    kind = operation.get("type")
    if kind == "source":
        return []
    if kind == "filter":
        return [operation["column"]["column_name"]]
    if kind == "join":
        condition = operation["join_condition"]
        return ([c["column_name"] for c in operation["select_columns"]]
                + [condition["left_column"]["column_name"],
                   condition["right_column"]["column_name"]])
    if kind == "summarize":
        return ([m["column_name"] for m in operation["measures"]]
                + [d["column_name"] for d in operation["dimensions"]])
    raise AssertionError(
        f"operation type '{kind}' is not covered by the drift check — add it, "
        "or a column could reach Insights through it unchecked")


class _Drift(unittest.TestCase):
    def convert(self, sql):
        result = operations_from_sql(analyze_sql(sql), COLUMNS)
        self.assertTrue(result["supported"], result["reasons"])
        return result["operations"]

    def assert_every_column_is_real(self, operations):
        """No column anywhere that the tables do not have.

        `count` is Insights' own name for a bare COUNT measure and is not a
        column of anything — it is the one name allowed through.
        """
        real = {column for table in TABLES.values() for column in table} | {"count"}
        for operation in operations:
            for column in columns_named_in(operation):
                self.assertIn(column, real,
                              f"'{column}' is not a column of any table in this query, "
                              f"and it reached the {operation['type']} operation")


class TestNothingUnrealReachesTheOperations(_Drift):
    """One assertion, many query shapes. A shape that starts emitting a column
    from somewhere other than the validated schema fails here without anybody
    knowing which column it would have been."""

    QUERIES = {
        "a plain count":
            "SELECT COUNT(*) FROM `tabParent`",
        "a filter and a grouping":
            "SELECT `status`, COUNT(*) FROM `tabParent` WHERE `title` = 'x' "
            "GROUP BY `status`",
        "a join, whose select_columns carries the whole joined table":
            "SELECT COUNT(*) FROM `tabParent` LEFT JOIN `tabChild` c "
            "ON c.`parent` = `tabParent`.`name`",
        "two joins":
            "SELECT COUNT(*) FROM `tabParent` LEFT JOIN `tabChild` c "
            "ON c.`parent` = `tabParent`.`name` LEFT JOIN `tabOther` o "
            "ON o.`parent` = `tabParent`.`name`",
        "an aggregate and a grouping across a join":
            "SELECT c.`metric`, AVG(c.`score`) FROM `tabParent` "
            "LEFT JOIN `tabChild` c ON c.`parent` = `tabParent`.`name` "
            "WHERE `tabParent`.`status` = 'Open' GROUP BY c.`metric`",
        "a framework column the joined table DOES have":
            "SELECT COUNT(*) FROM `tabParent` LEFT JOIN `tabChild` c "
            "ON c.`parent` = `tabParent`.`name` WHERE c.`idx` > 1",
    }

    def test_every_shape(self):
        for description, sql in self.QUERIES.items():
            with self.subTest(description):
                self.assert_every_column_is_real(self.convert(sql))


class TestTheDriftItselfIsRefusedByName(_Drift):
    """A column that is only in the DocType must refuse — not be dropped
    quietly, because a query missing a filter answers a different question."""

    def refusal(self, sql):
        result = operations_from_sql(analyze_sql(sql), COLUMNS)
        self.assertFalse(result["supported"], "a phantom column was translated")
        return " | ".join(result["reasons"])

    def test_a_filter_on_a_phantom_column(self):
        self.assertIn("not a column", self.refusal(
            "SELECT COUNT(*) FROM `tabParent` LEFT JOIN `tabChild` c "
            "ON c.`parent` = `tabParent`.`name` WHERE c.`corrective_action` = 'x'"))

    def test_a_grouping_by_a_phantom_column(self):
        self.assertIn("not a column", self.refusal(
            "SELECT c.`data`, COUNT(*) FROM `tabParent` LEFT JOIN `tabChild` c "
            "ON c.`parent` = `tabParent`.`name` GROUP BY c.`data`"))

    def test_an_aggregate_over_a_phantom_column(self):
        self.assertIn("not a column", self.refusal(
            "SELECT AVG(c.`corrective_action`) FROM `tabParent` "
            "LEFT JOIN `tabChild` c ON c.`parent` = `tabParent`.`name`"))

    def test_a_join_on_a_phantom_column(self):
        self.assertIn("not a column", self.refusal(
            "SELECT COUNT(*) FROM `tabParent` LEFT JOIN `tabChild` c "
            "ON c.`corrective_action` = `tabParent`.`name`"))

    def test_an_optional_framework_column_the_JOINED_table_lacks(self):
        """The parent has `_comments`; the child does not. Same category,
        opposite direction to the one above."""
        self.assertIn("not a column", self.refusal(
            "SELECT COUNT(*) FROM `tabParent` LEFT JOIN `tabChild` c "
            "ON c.`parent` = `tabParent`.`name` WHERE c.`_comments` = 'x'"))

    def test_a_layout_field_is_not_a_column(self):
        self.assertIn("not a column", self.refusal(
            "SELECT `layout`, COUNT(*) FROM `tabParent` GROUP BY `layout`"))


class TestTheCheckItselfCannotPassVacuously(_Drift):
    """Guards on the guard. Both of these have gone wrong before: an assertion
    that reads no columns, and a walker that silently skips a shape."""

    def test_the_walker_reads_columns_out_of_every_shape(self):
        operations = self.convert(
            "SELECT c.`metric`, AVG(c.`score`) FROM `tabParent` "
            "LEFT JOIN `tabChild` c ON c.`parent` = `tabParent`.`name` "
            "WHERE `tabParent`.`status` = 'Open' GROUP BY c.`metric`")
        self.assertEqual([op["type"] for op in operations],
                         ["source", "join", "filter", "summarize"])
        for operation in operations:
            if operation["type"] != "source":
                self.assertTrue(columns_named_in(operation),
                                f"the walker found no columns in a {operation['type']}")

    def test_an_unknown_operation_shape_fails_loudly(self):
        with self.assertRaises(AssertionError):
            columns_named_in({"type": "mutate", "new_name": "x"})

    def test_a_phantom_column_WOULD_be_caught(self):
        """The assertion has to be able to fail. Fed an operation naming a
        DocType-only column, it must not pass."""
        with self.assertRaises(AssertionError):
            self.assert_every_column_is_real([
                {"type": "filter", "operator": "=", "value": "x",
                 "column": {"type": "column", "column_name": "corrective_action"}}])


if __name__ == "__main__":
    unittest.main()
