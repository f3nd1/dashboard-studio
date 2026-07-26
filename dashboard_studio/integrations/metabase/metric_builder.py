"""Turn an analyze_sql result into the DS Metric it describes.

Frappe-free on purpose: this is the derivation, and it is unit-tested without a
Bench. ``api/studio.py`` does the record writing.

Three rules, settled:

- **Always Draft.** A metric derived from a pasted query has been reviewed by
  nobody. Approval is what stands between an unreviewed number and a published
  EduTrust dashboard, and a parser cannot grant it.
- **``allowed_fields`` comes from the fields the query actually names** — its
  dimension and its measure — and nothing else. A wider allowlist would let a
  later edit reference a field the source query never touched, which is the
  block-by-default rule wearing off.
- **The name is derived, so the same query yields the same metric.** DS Metric
  is ``autoname: field:metric_name``, so a deterministic name IS the reuse
  mechanism: analysing a query twice resolves to the record that already exists.
"""

# SQL aggregate -> DS Metric.calculation_type. Anything else is not something
# this can name honestly, so it is refused rather than filed under Custom.
_CALCULATION = {"COUNT": "Count", "SUM": "Sum", "AVG": "Average"}


def metric_from_analysis(analysis):
    """The DS Metric an analysis describes, or None with a reason.

    Returns ``(fields, reason)``: exactly one is set. ``fields`` is a plain dict
    ready to become a DS Metric.
    """
    if not analysis or not analysis.get("supported"):
        return None, "the query was not translated, so there is nothing to describe"

    doctypes = analysis.get("doctypes") or []
    if len(doctypes) != 1:
        # A join spans two DocTypes and the engine executes none of them today.
        return None, "a metric needs exactly one source DocType"
    source_doctype = doctypes[0]

    aggregations = analysis.get("aggregations") or []
    if len(aggregations) != 1:
        return None, "a metric needs exactly one aggregation"
    function = str(aggregations[0].get("function") or "").upper()
    if function not in _CALCULATION:
        return None, f"aggregation {function or '<none>'} has no DS Metric equivalent"

    group_by = analysis.get("group_by") or []
    if len(group_by) != 1:
        return None, "a metric needs exactly one group-by field"
    dimension = group_by[0]

    # COUNT(*) counts docnames; every other aggregate names its own column.
    argument = str(aggregations[0].get("argument") or "").strip()
    value_field = "name" if function == "COUNT" and argument in ("*", "") else argument
    if not value_field:
        return None, f"{function} has no column to measure"

    # ponytail: filtered queries are refused, not silently unfiltered. Dropping a
    # WHERE clause would produce a metric that counts MORE rows than the query it
    # came from — a wrong number with no error — and keeping it without putting
    # the filter in the name would make "count of admitted applicants" and "count
    # of applicants" the same record. Upgrade path: write analysis["filters"] to
    # DS Metric Filter rows and include them in the name.
    filters = analysis.get("filters") or []
    if filters:
        named = ", ".join(str(f.get("field") or "?") for f in filters)
        return None, (
            f"the query filters on {named}; generating a metric would either drop "
            "the filter or collide with the unfiltered one. Build this metric by hand."
        )

    # Only what the query names, de-duplicated, in a stable order.
    allowed = []
    for field in [dimension, value_field]:
        if field and field not in allowed:
            allowed.append(field)

    return {
        "metric_name": metric_name(_CALCULATION[function], source_doctype, dimension),
        "status": "Draft",
        "source_doctype": source_doctype,
        "calculation_type": _CALCULATION[function],
        "group_by_field": dimension,
        "value_field": value_field,
        "allowed_fields": "\n".join(allowed),
    }, None


def metric_name(calculation_type, source_doctype, dimension):
    """Deterministic, human-readable, and the reuse key.

    Two queries that describe the same measurement resolve to the same name and
    therefore the same record — which is the whole of the "do not create a
    second one" rule. Filters are deliberately NOT in the name: a filtered and
    an unfiltered count are different metrics and must not collide, so a metric
    carrying filters is refused upstream rather than named around.
    """
    return f"{calculation_type} of {source_doctype} by {dimension}"
