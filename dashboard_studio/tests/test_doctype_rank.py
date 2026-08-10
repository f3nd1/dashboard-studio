"""The DocType shortlist: the same answer every time, with its reasons.

This replaced a sampled LLM reply that returned a different set of tables on
each run of the same question. ADR-023 records that confirm step as the ENTIRE
defence against a query over the wrong table — real numbers about the wrong
thing, passing every referential check — so the property these tests exist to
hold is determinism first and ranking quality second. A ranker that is merely
usually right is still auditable; one that varies is not.
"""

import unittest

from dashboard_studio.integrations.doctype_rank import rank_doctypes, terms


def entry(doctype, module="Core", istable=0, fields=()):
    return {"doctype": doctype, "module": module, "istable": istable,
            "fields": [{"label": label, "fieldname": fieldname}
                       for label, fieldname in fields]}


# A small stand-in for a site: the real failure this feature exists to prevent
# is a question about recruitment agents answered from the sales-commission
# tables, so both live here and both are plausible.
CATALOGUE = [
    entry("Sales Team", "Selling",
          fields=[("Sales Person", "sales_person"),
                  ("Commission Rate", "commission_rate")]),
    entry("Recruitment Agent", "HR",
          fields=[("Agent Name", "agent_name"), ("Country", "country")]),
    entry("Student Applicant", "Education",
          fields=[("Applicant Name", "applicant_name"),
                  ("Agent", "agent"), ("Programme", "programme")]),
    entry("Sales Invoice", "Accounts",
          fields=[("Customer", "customer"), ("Grand Total", "grand_total")]),
    entry("Item Price", "Stock", fields=[("Price List Rate", "price_list_rate")]),
]


class TestItIsDeterministic(unittest.TestCase):
    """The property the whole change exists for."""

    def test_the_same_question_gives_the_same_answer(self):
        first = rank_doctypes("which recruitment agents sent students?", CATALOGUE)
        for _ in range(5):
            self.assertEqual(rank_doctypes("which recruitment agents sent students?",
                                           CATALOGUE), first)

    def test_the_catalogues_OWN_ORDER_cannot_change_the_answer(self):
        """`frappe.get_all` returns DocTypes `modified desc`, so the catalogue
        arrives in a different order as documents change. If that reached the
        result, the shortlist would drift on its own — the same fault as the
        sampled version, wearing different clothes."""
        question = "how many students does each agent have?"
        forwards = rank_doctypes(question, CATALOGUE)
        backwards = rank_doctypes(question, list(reversed(CATALOGUE)))
        self.assertEqual(forwards, backwards)

    def test_equal_scores_break_by_NAME_not_by_position(self):
        catalogue = [entry("Zebra Record", fields=[("Widget", "widget")]),
                     entry("Alpha Record", fields=[("Widget", "widget")])]
        ranked = rank_doctypes("widget", catalogue)
        self.assertEqual([r["doctype"] for r in ranked],
                         ["Alpha Record", "Zebra Record"])
        self.assertEqual(ranked[0]["score"], ranked[1]["score"])


class TestItRanksOnFacts(unittest.TestCase):
    def names(self, question, catalogue=None):
        return [r["doctype"] for r in rank_doctypes(question, catalogue or CATALOGUE)]

    def test_the_recruitment_agent_question_finds_the_recruitment_agent(self):
        """The original incident, as a test. The sales-commission table may
        still appear — it has a 'Sales Person' field and the question says
        nothing to exclude it — but it must not come FIRST."""
        ranked = self.names("how many students did each recruitment agent send?")
        self.assertEqual(ranked[0], "Recruitment Agent")
        self.assertIn("Student Applicant", ranked)

    def test_a_table_name_outranks_a_field_that_merely_mentions_it(self):
        """`Recruitment Agent` IS agents; `Student Applicant` merely has an
        agent field. Both are worth offering, in that order.

        The names here sort the same way as the ranking, so this alone would
        pass with the weights flattened — a mutation run caught exactly that.
        The test below is the one that discriminates; this one stays because
        it is the realistic case.
        """
        ranked = self.names("list the agents")
        self.assertEqual(ranked[0], "Recruitment Agent")
        self.assertLess(ranked.index("Recruitment Agent"),
                        ranked.index("Student Applicant"))

    def test_the_name_wins_even_when_the_alphabet_disagrees(self):
        """Ties break by name, so a test whose expected winner also sorts
        first proves nothing about the weighting. Here the name match sorts
        LAST alphabetically and must still come first."""
        catalogue = [entry("Alpha Record", "Core",
                           fields=[("Agent Name", "agent_name")]),
                     entry("Zebra Agent", "Core")]
        self.assertEqual(self.names("agents", catalogue),
                         ["Zebra Agent", "Alpha Record"])

    def test_a_plural_question_finds_a_singular_table(self):
        """Frappe names DocTypes in the singular and people ask in the plural."""
        self.assertIn("Student Applicant", self.names("how many students?"))
        self.assertIn("Sales Invoice", self.names("show me the invoices"))

    def test_an_unrelated_table_is_not_offered_at_all(self):
        """A weak brush against one fieldname is not a reason to put a table in
        front of somebody — the list is read, and padding it stops it being."""
        self.assertNotIn("Item Price", self.names("how many students?"))

    def test_a_question_with_nothing_to_match_returns_nothing(self):
        """Rather than the whole catalogue in arbitrary order."""
        self.assertEqual(rank_doctypes("how many are there?", CATALOGUE), [])
        self.assertEqual(rank_doctypes("", CATALOGUE), [])

    def test_the_module_counts_when_the_name_does_not(self):
        catalogue = [entry("Applicant Detail", "Education",
                           fields=[("Note", "note")])]
        self.assertEqual(self.names("education records", catalogue),
                         ["Applicant Detail"])


class TestTheEvidence(unittest.TestCase):
    """The reason this beats a rationale: it is the fact itself, checkable.

    ADR-023 refused to return the model's reasoning because a rationale
    describes an intention while the query does something else. "The field
    labelled 'Agent Name' matched 'agent'" is not an intention.
    """

    def only(self, question, catalogue):
        ranked = rank_doctypes(question, catalogue)
        self.assertEqual(len(ranked), 1, ranked)
        return ranked[0]

    def test_a_name_match_says_so(self):
        found = self.only("agents", [entry("Recruitment Agent", "HR")])
        self.assertIn("the table name matched 'agent'", found["evidence"])

    def test_a_field_label_match_names_the_LABEL_a_person_would_recognise(self):
        found = self.only("agents", [entry("Student Applicant", "Education",
                                           fields=[("Agent Name", "agent_name")])])
        self.assertIn("the field labelled 'Agent Name' matched 'agent'",
                      found["evidence"])

    def test_a_column_match_names_the_column(self):
        """A field with no label falls back to its column name."""
        found = self.only("programme", [entry("Enrolment", "Education",
                                              fields=[(None, "programme")])])
        self.assertIn("the column 'programme' matched 'programme'",
                      found["evidence"])

    def test_a_PARTIAL_word_says_it_is_only_close(self):
        """Somebody typing "assess" should still find `Assessment Result`, and
        the evidence must not claim more than happened — it is a near miss, and
        the person confirming is the one who decides whether it is the right
        table."""
        found = self.only("assess results", [entry("Assessment Result", "Education")])
        self.assertIn("the table name is close to 'assess'", found["evidence"])

    def test_ONE_weak_column_brush_is_not_enough_to_be_offered(self):
        """`student_id` is close to "student", and that alone is not a reason
        to put a table in front of somebody. The list is read only while it is
        short enough to be read."""
        self.assertEqual(
            rank_doctypes("students", [entry("Login Audit", "Core",
                                             fields=[(None, "student_id")])]), [])

    def test_every_candidate_carries_at_least_one_reason(self):
        for found in rank_doctypes("students and agents", CATALOGUE):
            self.assertTrue(found["evidence"], found)

    def test_a_child_table_is_flagged_as_one(self):
        """Joining one multiplies rows (`rows_multiplied_by`), so the page can
        say which candidates are child tables rather than leaving it to be
        discovered in the number."""
        found = self.only("survey answers",
                          [entry("Survey Answer", "Education", istable=1)])
        self.assertTrue(found["istable"])


class TestTermsFromAQuestion(unittest.TestCase):
    def test_stopwords_and_short_words_are_dropped(self):
        """Without this, "how many of the students are active" ranks every
        table with a field labelled Name or Status."""
        found = terms("how many of the students are active?")
        self.assertIn("student", found)
        self.assertNotIn("how", found)
        self.assertNotIn("many", found)
        self.assertNotIn("the", found)

    def test_counting_words_are_dropped_too(self):
        """Every question here asks for a count or an average; a DocType called
        `Report` or a field labelled `Total` would otherwise top every list."""
        for word in ("count", "total", "average", "number", "report"):
            self.assertNotIn(word, terms(f"what is the {word} of students"))

    def test_the_plural_and_the_singular_are_both_kept(self):
        """The singular does the matching; the original stays because a table
        really can be named in the plural."""
        self.assertEqual(terms("agencies"), ["agency", "agencies"])
        self.assertEqual(terms("classes"), ["class", "classes"])
        self.assertEqual(terms("students"), ["student", "students"])

    def test_a_double_s_is_not_stripped(self):
        """`address` is not a plural of `addres`."""
        self.assertIn("address", terms("home address"))
        self.assertNotIn("addres", terms("home address"))

    def test_the_order_is_first_seen(self):
        self.assertEqual(terms("students and agents"),
                         ["student", "students", "agent", "agents"])


class TestLayoutFieldsCannotRank(unittest.TestCase):
    """A Section Break labelled "Student Details" has no column behind it.

    The filter is applied by the caller when it reads the catalogue, so this
    pins the rule rather than the implementation: given a catalogue that
    contains only data fields, a layout label cannot contribute.
    """

    def test_the_reader_excludes_them(self):
        """Read from the syntax tree: `api/propose.py` imports frappe, and
        there is no site here."""
        import ast
        import pathlib
        tree = ast.parse((pathlib.Path(__file__).resolve().parents[1]
                          / "api" / "propose.py").read_text())
        excluded = [ast.literal_eval(node.value) for node in ast.walk(tree)
                    if isinstance(node, ast.Assign)
                    and any(getattr(t, "id", "") == "NO_DATA_FIELDS"
                            for t in node.targets)]
        self.assertEqual(len(excluded), 1)
        for fieldtype in ("Section Break", "Column Break", "Tab Break", "HTML"):
            self.assertIn(fieldtype, excluded[0])

    def test_a_layout_label_would_otherwise_have_ranked(self):
        """The check has to bite: a Section Break labelled "Student Details"
        scores exactly as a real field would, which is why it is filtered at
        the source rather than here."""
        self.assertTrue(rank_doctypes(
            "students", [entry("Login Audit", "Core",
                               fields=[("Student Details", "sb_1")])]))


if __name__ == "__main__":
    unittest.main()
