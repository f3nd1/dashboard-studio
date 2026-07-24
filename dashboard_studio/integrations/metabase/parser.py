from __future__ import annotations

import re

TABLE_PATTERN = re.compile(r"`tab([^`]+)`", re.IGNORECASE)

# Aggregations we can translate into a Dashboard Studio metric today.
_AGG_PATTERN = re.compile(r"\b(COUNT|SUM|AVG)\s*\(\s*([^)]*?)\s*\)", re.IGNORECASE)
_JOIN_PATTERN = re.compile(r"\bJOIN\b", re.IGNORECASE)
# A single simple join: JOIN `tabX` [alias] ON <a> = <b>
_SIMPLE_JOIN = re.compile(
    r"\bJOIN\s+`tab([^`]+)`(?:\s+\w+)?\s+ON\s+(.+?)(?=\bWHERE\b|\bGROUP\b|\bORDER\b|\bLIMIT\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_CONDITION = re.compile(
    r"^\s*(?:`tab[^`]+`\.)?`?([\w ]+?)`?\s*(=|!=|<>|>=|<=|>|<|\bLIKE\b|\bIN\b)\s*(.+?)\s*$",
    re.IGNORECASE,
)

# Constructs this conservative analyzer will not guess at — flagged for manual
# review instead of mistranslated (same precedent as the duration query).
_UNSUPPORTED_MARKERS = (
    (re.compile(r"\bOVER\s*\(", re.IGNORECASE), "window function (OVER)"),
    (re.compile(r"\bUNION\b", re.IGNORECASE), "UNION"),
    (re.compile(r"\bHAVING\b", re.IGNORECASE), "HAVING clause"),
    (re.compile(r"\bCASE\b", re.IGNORECASE), "CASE expression"),
    (re.compile(r"\bDISTINCT\b", re.IGNORECASE), "DISTINCT"),
)


def discover_frappe_doctypes(sql: str) -> list[str]:
    """Return unique Frappe DocType candidates referenced as `tab<DocType>`."""
    if not isinstance(sql, str):
        raise TypeError("sql must be a string")
    return list(dict.fromkeys(match.strip() for match in TABLE_PATTERN.findall(sql) if match.strip()))


def _strip_qualifier(expr: str) -> str:
    """`tabStudent Applicant`.`academic_year` -> academic_year (bare field)."""
    expr = expr.strip().rstrip(",").strip()
    expr = re.sub(r"`tab[^`]+`\.", "", expr)
    return expr.strip().strip("`").strip()


def _parse_filters(sql: str) -> list[dict]:
    m = re.search(
        r"\bWHERE\b(.+?)(?=\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|$)",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return []
    filters = []
    # Naive split on AND — sufficient for the simple flat WHERE clauses in scope.
    for part in re.split(r"\bAND\b", m.group(1), flags=re.IGNORECASE):
        cm = _CONDITION.match(part)
        if not cm:
            continue
        field, op, value = cm.group(1).strip(), cm.group(2).upper(), cm.group(3).strip()
        filters.append({"field": field, "operator": op, "value": value.strip("'\"")})
    return filters


def _parse_group_by(sql: str) -> list[str]:
    m = re.search(r"\bGROUP\s+BY\b(.+?)(?=\bORDER\s+BY\b|\bLIMIT\b|$)", sql, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    return [_strip_qualifier(p) for p in m.group(1).split(",") if _strip_qualifier(p)]


def analyze_sql(sql: str) -> dict:
    """Conservatively analyze a single Metabase SELECT statement.

    Returns a structured description when the query fits the supported shape
    (single-table or single simple-JOIN SELECT with COUNT/SUM/AVG, a flat WHERE,
    and an optional single-column GROUP BY). Anything outside that — subqueries,
    multiple joins, window functions, UNION/HAVING/CASE/DISTINCT — is NOT guessed
    at: ``supported`` is False and ``reasons`` explains why, for manual review.

    This is a pragmatic regex analyzer, not a full SQL parser. It errs toward
    flagging: when in doubt it declines rather than mistranslating.
    """
    if not isinstance(sql, str):
        raise TypeError("sql must be a string")

    reasons: list[str] = []
    statement = sql.strip().rstrip(";")

    # Subquery / nested SELECT: more than one SELECT keyword.
    if len(re.findall(r"\bSELECT\b", statement, re.IGNORECASE)) > 1:
        reasons.append("subquery / nested SELECT")

    join_count = len(_JOIN_PATTERN.findall(statement))
    if join_count > 1:
        reasons.append(f"multiple joins ({join_count})")

    for pattern, message in _UNSUPPORTED_MARKERS:
        if pattern.search(statement):
            reasons.append(message)

    doctypes = [_dt(t) for t in discover_frappe_doctypes(statement)]
    aggregations = [
        {"function": fn.upper(), "argument": arg.strip() or "*"}
        for fn, arg in _AGG_PATTERN.findall(statement)
    ]

    join = None
    if join_count == 1 and "subquery / nested SELECT" not in reasons:
        jm = _SIMPLE_JOIN.search(statement)
        if jm:
            join = {"doctype": _dt(jm.group(1)), "on": " ".join(jm.group(2).split())}
        else:
            reasons.append("join present but not a simple `tab<DocType>` ... ON <a>=<b>")

    return {
        "supported": not reasons,
        "reasons": reasons,
        "doctypes": doctypes,
        "aggregations": aggregations,
        "filters": _parse_filters(statement),
        "group_by": _parse_group_by(statement),
        "join": join,
    }


def analyze_sql_file(text: str) -> list[dict]:
    """Analyze every statement in a multi-query .sql export.

    Splits on ';' (naive — assumes no ';' inside string literals, true for the
    reference samples) and skips blank/comment-only fragments.
    """
    out = []
    for raw in text.split(";"):
        stmt = "\n".join(
            line for line in raw.splitlines() if not line.strip().startswith("--")
        ).strip()
        if re.search(r"\bSELECT\b", stmt, re.IGNORECASE):
            out.append(analyze_sql(stmt))
    return out


def _dt(table_or_name: str) -> str:
    from dashboard_studio.integrations.metabase.mapper import table_to_doctype

    return table_to_doctype(table_or_name)
