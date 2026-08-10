"""Which DocTypes might a question be about? Ranked from the schema, not asked.

**This replaced an LLM call, and the reason is auditability rather than cost.**
ADR-023 records the DocType confirm step as the entire defence against the
wrong-table failure — a question about recruitment agents answered from
ERPNext's sales-commission tables, every column real, every type right, nothing
for a referential validator to object to. That defence was returning a
DIFFERENT set of tables on each run of the same question, because the reply was
sampled. A defence that varies run to run is not one, and OpenAI's own `seed`
parameter documents itself as best-effort with determinism "not guaranteed", so
no sampling setting could have fixed it.

The schema is knowable, so this step should never have been a guess. Every
candidate here is ranked from facts already on the site: the DocType's name, its
module, and the labels and fieldnames of its DocFields. Two things follow that
the sampled version could not offer:

  - the same question gives the same answer, every time, and
  - each candidate carries the EVIDENCE it matched on ("field label 'Agent
    Name' matched 'agent'"), so the person confirming has something to check
    rather than a list to rubber-stamp.

The second is the bigger win. ADR-023 deliberately refused to return the model's
rationale, because a rationale describes an intention while the query does
something else. A match on a real field label is not a rationale — it is the
fact itself, and it is checkable.

**Frappe-free and injected**, like `parser.py`: the catalogue is passed in, so
the ranking is unit-testable without a site. `api/propose.py` reads the
catalogue and calls this.

What this does NOT do is understand synonyms: "staff" will not find `Employee`
on its own. That is the honest cost of dropping the model, and it is mitigated
by ranking over field labels as well as table names (an Employee DocType has a
field labelled "Staff Number" more often than not), by returning a generous
list rather than the model's four, and by the manual entry path that already
exists. Whether it needs a re-ranking layer on top is a question to answer by
measuring this against real questions, not by assuming.
"""

from __future__ import annotations

import re

# Words that match everything and therefore mean nothing. A question is a
# sentence, and without this "how many of the students are active" ranks every
# DocType carrying a field labelled "Name" or "Status".
STOPWORDS = frozenset("""
a an and any are as at be been being between by can could did do does for from
get give had has have how i in into is it its list many me most much my of on
or our over please show showed shows since so some than that the their them
then there these they this those to total us was we were what when where which
who whom why will with would you your each per all every not no
count sum average avg total number report chart table data record records
""".split())

# What each kind of match is worth. The ordering is the claim, not the numbers:
# a DocType whose NAME is the thing asked about beats one that merely has a
# field mentioning it, and an exact word beats a word that merely starts the
# same. Nothing here is tuned — these are the ranks in the order a person
# would put them, and the evidence line means a wrong order is visible rather
# than silent.
WEIGHT_NAME = 10.0
WEIGHT_MODULE = 4.0
WEIGHT_LABEL = 3.0
WEIGHT_FIELDNAME = 2.0
# A prefix match ("applicant" against "applicants") is worth a fraction of an
# exact one. Frappe's own plurals are inconsistent enough that dropping this
# loses real tables.
PREFIX_FACTOR = 0.5
# Below this a candidate is not offered at all: one weak fieldname brush is not
# a reason to put a table in front of somebody.
MINIMUM_SCORE = 2.0

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def terms(question: str) -> list[str]:
    """The words worth matching on, singularised, in first-seen order.

    Singular and plural are folded together because a question says "agents"
    and a DocType is called "Agent" — near enough universally, since Frappe
    names DocTypes in the singular. The rules are the three regular English
    ones and nothing cleverer: an irregular plural that fails here degrades to
    a candidate not ranked, which the person can still type in by hand.
    """
    found = []
    for word in _WORD.findall(str(question or "")):
        word = word.lower()
        if word in STOPWORDS or len(word) < 3:
            continue
        for singular in (_singular(word), word):
            if singular and singular not in found:
                found.append(singular)
    return found


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokens(text: str) -> set[str]:
    """The words of a name, each also folded to its singular."""
    out = set()
    for word in _WORD.findall(str(text or "")):
        word = word.lower()
        out.add(word)
        out.add(_singular(word))
    return out


def _score_one(term: str, tokens: set[str]):
    """``(factor, how)`` for one term against one name's words."""
    if term in tokens:
        return 1.0, "matched"
    for token in tokens:
        if len(token) > 3 and (token.startswith(term) or term.startswith(token)):
            return PREFIX_FACTOR, "is close to"
    return 0.0, ""


def rank_doctypes(question: str, catalogue, limit: int = 8):
    """Rank the catalogue against the question. Deterministic, evidence-first.

    `catalogue` is a list of ``{"doctype", "module", "istable", "fields"}``
    where `fields` is a list of ``{"label", "fieldname"}`` — read from the site
    by the caller, never from here.

    Returns ``[{"doctype", "score", "istable", "evidence": [str, ...]}]``,
    highest first. **Ties break by name**, so the order is total and the same
    question cannot produce two different lists — which is the entire point of
    replacing the sampled version, and would be quietly lost to a sort that
    left equal scores in catalogue order.
    """
    wanted = terms(question)
    if not wanted:
        return []
    ranked = []
    for entry in catalogue or []:
        name = str(entry.get("doctype") or "")
        if not name:
            continue
        score, evidence = 0.0, []
        name_tokens = _tokens(name)
        module_tokens = _tokens(entry.get("module"))
        for term in wanted:
            factor, how = _score_one(term, name_tokens)
            if factor:
                score += WEIGHT_NAME * factor
                evidence.append(f"the table name {how} '{term}'")
                continue
            factor, how = _score_one(term, module_tokens)
            if factor:
                score += WEIGHT_MODULE * factor
                evidence.append(f"the module '{entry.get('module')}' {how} '{term}'")
        # Fields are scanned once per table rather than once per term, so a
        # table with 200 fields costs one pass. The first field to match a term
        # is the one reported: a second is the same fact told twice.
        seen_terms = set()
        for field in entry.get("fields") or []:
            if len(seen_terms) == len(wanted):
                break
            label, fieldname = field.get("label"), field.get("fieldname")
            for term in wanted:
                if term in seen_terms:
                    continue
                factor, how = _score_one(term, _tokens(label))
                if factor:
                    score += WEIGHT_LABEL * factor
                    evidence.append(f"the field labelled '{label}' {how} '{term}'")
                    seen_terms.add(term)
                    continue
                factor, how = _score_one(term, _tokens(fieldname))
                if factor:
                    score += WEIGHT_FIELDNAME * factor
                    evidence.append(f"the column '{fieldname}' {how} '{term}'")
                    seen_terms.add(term)
        if score >= MINIMUM_SCORE:
            ranked.append({"doctype": name, "score": round(score, 3),
                           "istable": bool(entry.get("istable")),
                           "evidence": evidence[:4]})
    # Score first, then NAME — never the catalogue's own order, which is
    # whatever the database returned and changes as documents are modified.
    ranked.sort(key=lambda entry: (-entry["score"], entry["doctype"]))
    return ranked[:limit] if limit else ranked
