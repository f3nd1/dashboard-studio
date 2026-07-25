"""EduTrust criterion and subcriterion scope.

⚠️  THIS IS A COPY. The authoritative list lives on the Sophia side, in the
``POLICY_REGISTRY`` dict at the top of each of the seven Server Scripts
``UCC Analytics - Criterion 1.py`` … ``Criterion 7.py`` in the
``f3nd1/intelligence-dashboard`` repository. It is duplicated here because
nothing serves it: Sophia's own list is embedded in a Custom HTML Block field
and in Server Script source, neither of which this app can import or call.

**Recheck this file whenever Sophia's registries change.** A code that exists
here but not in Sophia's ``apiSections`` does not fail loudly — Sophia falls back
to the criterion's default section and renders the wrong subcriterion's data
under the right heading. That silent mis-route is the reason publishing
validates against this list rather than trusting it.

Do NOT source this from ``VERSION.json``. Its ``policy_registries`` block omits
criterion_4 and criterion_5 entirely and is already stale against the scripts.

Deliberately excluded:

- ``overview``. Sophia's POLICY_REGISTRY defines it for criteria 1, 3, 4 and 5,
  but its frontend rewrites ``overview`` to the criterion's first subcriterion
  for every criterion, so nothing ever requests it. A dashboard scoped to
  ``overview`` would publish to a section Sophia does not route to.
- The frontend spellings ``5.4`` and ``5.5``. Criterion 5's Server Script
  canonicalises those to ``5.4.1``/``5.5.1`` via ``SUBCRITERION_ALIASES``; the
  alias map is a compatibility shim for Sophia's own frontend, not a second
  valid spelling. Canonical codes only.

Frappe-free on purpose, so the mapping is unit-testable without a Bench.
"""

# code -> subcriterion title, taken verbatim from POLICY_REGISTRY[code]["title"].
SUBCRITERIA = {
    "1.1.1": "Leadership and Corporate Governance",
    "1.2.1": "Strategic Planning",
    "2.1.1": "Staff Selection and Management",
    "2.1.2": "Staff Training and Development",
    "2.2.1": "Internal and External Communication",
    "2.3.1": "Data and Information Management",
    "2.3.2": "Knowledge Management",
    "2.4.1": "Feedback Management",
    "2.4.2": "Student Satisfaction Survey",
    "2.4.3": "Staff Satisfaction Survey",
    "3.1.1": "Selection and Appointment of External Recruitment Agents",
    "3.2.1": "Management and Evaluation of Recruitment Agents",
    "4.1.1": "Pre-Course Counselling, Selection and Admissions",
    "4.2.1": "Student Contract",
    "4.2.2": "Fee Collection and Fee Protection Scheme",
    "4.3.1": "Course Transfer, Deferment and Withdrawal",
    "4.4.1": "Refund",
    "4.5.1": "Student Support Services",
    "4.6.1": "Student Conduct and Attendance",
    "5.1.1": "Course Design and Development",
    "5.1.2": "Course Review",
    "5.2.1": "Course Planning",
    "5.2.2": "Course Delivery",
    "5.3.1": "Partnerships",
    "5.4.1": "Student Learning",
    "5.5.1": "Student Assessment",
    "6.1.1": "Internal Assessment and Quality Audits",
    "6.2.1": "Management Review",
    "6.3.1": "Innovation and Continual Improvement",
    "6.4.1": "Provider's Accreditation and Evaluation",
    "6.5.3": "Hazard Identification and Risk Assessment",
    "7.1.1": "Measurement of Outcomes",
}

# Criterion titles, for display alongside the derived criterion number.
CRITERIA = {
    "1": "Leadership and Strategic Planning",
    "2": "Corporate Administration",
    "3": "External Recruitment Agents",
    "4": "Student Protection and Support Services",
    "5": "Academic Systems and Processes",
    "6": "Quality Assurance, Innovation and Continual Improvement",
    "7": "Performance Outcomes",
}


def criterion_of(subcriterion: str) -> str | None:
    """Criterion number for a subcriterion code, from its prefix.

    The prefix *is* the criterion, so it is derived rather than stored — a second
    stored field would only create the chance for the two to disagree, and a
    mismatched pair is exactly what Sophia resolves silently and wrongly.
    """
    if subcriterion not in SUBCRITERIA:
        return None
    return subcriterion.split(".")[0]


def describe(subcriterion: str) -> dict | None:
    """Everything needed to render a scope, or None if the code is unknown.

    Only the code is ever stored; the labels are resolved here so a retitle on
    the Sophia side does not strand records against stale text.
    """
    number = criterion_of(subcriterion)
    if number is None:
        return None
    return {
        "subcriterion": subcriterion,
        "subcriterion_title": SUBCRITERIA[subcriterion],
        "criterion": number,
        "criterion_title": CRITERIA.get(number, ""),
        "label": f"Criterion {number} · {subcriterion}",
    }
