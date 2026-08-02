from __future__ import annotations

import re

TABLE_PATTERN = re.compile(r"`tab([^`]+)`", re.IGNORECASE)

# Aggregations we can translate into a Dashboard Studio metric today.
_AGG_PATTERN = re.compile(r"\b(COUNT|SUM|AVG)\s*\(\s*([^)]*?)\s*\)", re.IGNORECASE)
_JOIN_PATTERN = re.compile(r"\bJOIN\b", re.IGNORECASE)

# A table alias is the bare word after a table name. No keyword exclusion list:
# a keyword swallowed here only ever adds an unreachable key to the alias map
# (nobody writes ``WHERE.column``), and the one place it could truncate a real
# match — the alias slot in _JOIN_TABLE — is already covered by the required
# ``ON`` after it, which makes the regex backtrack. An exclusion list was tried
# and removed: no statement's analysis changed with or without it.
_ALIAS = r"(?:\s+(?:AS\s+)?`?(\w+)`?)?"

_FROM_TABLE = re.compile(r"\bFROM\s+`tab([^`]+)`" + _ALIAS, re.IGNORECASE)
# JOIN `tabX` [alias] ON <condition>. The strategy word in front of it decides
# the Insights join type, so it is captured rather than skipped over.
_JOIN_TABLE = re.compile(
    r"\b(?:(LEFT|RIGHT|FULL|INNER|CROSS)\s+)?(?:OUTER\s+)?JOIN\s+`tab([^`]+)`" + _ALIAS
    # GROUP/ORDER need their BY: "Purchase Order" is a real DocType, and a bare
    # \bORDER\b truncates the ON clause in the middle of the table name.
    + r"\s+ON\s+(.+?)(?=\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|$)",
    re.IGNORECASE | re.DOTALL,
)

# SQL join keyword -> Insights JoinType. A bare JOIN is an INNER JOIN in MySQL,
# which is what the site runs — that is the SQL standard's default, not a guess
# of ours. CROSS has no Insights equivalent and refuses by name.
JOIN_STRATEGIES = {"INNER": "inner", "LEFT": "left", "RIGHT": "right", "FULL": "full"}

# ``a.`col` `` / ``  `tabX`.`col` `` / ``col`` -> qualifier + column. Anchored at
# both ends on purpose: a function call, an arithmetic expression or a literal
# does not match, and therefore refuses rather than being half-read.
_QUALIFIED = re.compile(r"^(?:(?:`tab([^`]+)`|`?(\w+)`?)\.)?`?([\w ]+?)`?$", re.IGNORECASE)
# A join side must be qualified — ``ON ref = a.po`` does not say which table
# `ref` belongs to, and there is no safe way to pick one.
_ON_SIDE = re.compile(r"^(?:`tab([^`]+)`|`?(\w+)`?)\.`?([\w ]+?)`?$", re.IGNORECASE)

_CONDITION = re.compile(
    r"^\s*(?:(?:`tab([^`]+)`|`?(\w+)`?)\.)?`?([\w ]+?)`?"
    r"\s*(=|!=|<>|>=|<=|>|<|\bLIKE\b|\bIN\b)\s*(.+?)\s*$",
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


def _split_ref(expr: str) -> tuple[str | None, str | None]:
    """``a.`fee``` -> ("a", "fee"); ```fee``` -> (None, "fee"); junk -> (None, None).

    The qualifier comes back as written — an alias or a DocType name — and is
    resolved against the aliases this statement actually defines. Returning it
    rather than discarding it is what lets a joined query say which table a
    column belongs to.
    """
    match = _QUALIFIED.match(str(expr).strip().rstrip(",").strip())
    if not match:
        return None, None
    return match.group(1) or match.group(2), match.group(3).strip()


def _resolve(qualifier, aliases, reasons):
    """A qualifier -> the DocType it names, or None (unqualified).

    An unknown qualifier is a reason, not a shrug: it means the column belongs
    to a table this analysis never saw, and typing it against the wrong table
    is how a filter ends up selecting different rows.
    """
    if not qualifier:
        return None
    doctype = aliases.get(qualifier.lower())
    if not doctype:
        reasons.append(f"'{qualifier}' is not a table or alias this query defines")
    return doctype


def _on_side(text: str, aliases: dict) -> dict | None:
    match = _ON_SIDE.match(str(text).strip())
    if not match:
        return None
    qualifier = match.group(1) or match.group(2)
    doctype = aliases.get((qualifier or "").lower())
    if not doctype:
        return None
    return {"doctype": doctype, "column": match.group(3).strip()}


def _build_join(source: str, joined: str, strategy: str, clause: str, aliases: dict):
    """The ON clause -> the two named columns Insights needs, or a reason why not.

    The result is oriented by TABLE: ``source_column`` always belongs to the
    FROM table and ``join_column`` always to the joined one, whichever side of
    the ``=`` they were typed on. Insights' join_condition means exactly that,
    and orienting by writing order instead would silently swap them for half of
    all real queries.
    """
    join_type = JOIN_STRATEGIES.get(strategy)
    if not join_type:
        return None, f"{strategy} JOIN has no Insights equivalent"
    if source == joined:
        return None, (
            f"this query joins a table to itself ({source}), and which side of the "
            "condition is which cannot be told apart from the SQL"
        )

    parts = clause.split("=")
    if len(parts) != 2:
        return None, (
            f"the join condition '{clause}' is not a single equality — this converter "
            "translates only `a.column = b.column`"
        )
    left, right = _on_side(parts[0], aliases), _on_side(parts[1], aliases)
    sides = {}
    for side in (left, right):
        if side:
            sides[side["doctype"]] = side["column"]
    if set(sides) != {source, joined}:
        return None, (
            f"the join condition '{clause}' does not name one column from {source} and "
            f"one from {joined} — this converter translates only `a.column = b.column`"
        )
    return {
        "doctype": joined,
        "join_type": join_type,
        "on": clause,
        "source_column": sides[source],
        "join_column": sides[joined],
    }, None


def _parse_filters(sql: str, aliases: dict, reasons: list) -> tuple[list[dict], list[str]]:
    """Parse the WHERE clause into filters, plus reasons for anything unparsable.

    Flag-don't-guess: an OR clause or a condition that doesn't fit the simple
    ``field <op> value`` shape makes the whole query unsupported — a dropped or
    mangled condition would migrate a metric that counts the wrong rows.
    """
    m = re.search(
        r"\bWHERE\b(.+?)(?=\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|$)",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return [], []
    clause = m.group(1)
    # OR cannot map to the engine's AND-only conditions. Checked textually, so a
    # literal " OR " inside a string value also flags — conservative by design.
    if re.search(r"\bOR\b", clause, re.IGNORECASE):
        return [], ["OR in WHERE clause"]
    filters, problems = [], []
    # Naive split on AND — sufficient for the simple flat WHERE clauses in scope.
    for part in re.split(r"\bAND\b", clause, flags=re.IGNORECASE):
        cm = _CONDITION.match(part)
        if not cm:
            problems.append(f"unparsed WHERE condition: {' '.join(part.split())[:60]}")
            continue
        qualifier = cm.group(1) or cm.group(2)
        # Lowercase to match the engine's ALLOWED_OPERATORS convention.
        field, op, value = cm.group(3).strip(), cm.group(4).lower(), cm.group(5).strip()
        filters.append({"field": field, "operator": op, "value": value.strip("'\""),
                        "table": _resolve(qualifier, aliases, reasons)})
    return filters, problems


def _parse_group_by(sql: str, aliases: dict, reasons: list) -> list[dict]:
    m = re.search(r"\bGROUP\s+BY\b(.+?)(?=\bORDER\s+BY\b|\bLIMIT\b|$)", sql, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    out = []
    for part in m.group(1).split(","):
        if not part.strip():
            continue
        qualifier, field = _split_ref(part)
        if not field:
            continue
        out.append({"field": field, "table": _resolve(qualifier, aliases, reasons)})
    return out


def _parse_aggregations(sql: str, aliases: dict, reasons: list) -> list[dict]:
    out = []
    for function, argument in _AGG_PATTERN.findall(sql):
        argument = argument.strip()
        if not argument or argument == "*":
            out.append({"function": function.upper(), "argument": "*", "table": None})
            continue
        qualifier, column = _split_ref(argument)
        out.append({"function": function.upper(), "argument": column or argument,
                    "table": _resolve(qualifier, aliases, reasons)})
    return out


def analyze_sql(sql: str) -> dict:
    """Conservatively analyze a single Metabase SELECT statement.

    Returns a structured description when the query fits the supported shape
    (single-table or single simple-JOIN SELECT with COUNT/SUM/AVG, a flat WHERE,
    and an optional GROUP BY). Anything outside that — subqueries, multiple
    joins, window functions, UNION/HAVING/CASE/DISTINCT — is NOT guessed at:
    ``supported`` is False and ``reasons`` explains why, for manual review.

    A join comes back as ``{doctype, join_type, source_column, join_column}``
    with the two sides already oriented by table, which is what Insights'
    ``join_condition`` needs. Every ON clause that cannot be oriented with
    certainty refuses by name instead.

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

    # The source is the FROM table, NOT the first `tab…` in the text: a column of
    # the joined table can appear in the SELECT list first, and building the
    # query on that side is a different question with the same row count.
    from_match = _FROM_TABLE.search(statement)
    source_doctype = _dt(from_match.group(1)) if from_match else (doctypes[0] if doctypes else None)

    join_match = _JOIN_TABLE.search(statement) if join_count == 1 else None
    # Built before the join is validated so that a query whose ON clause is
    # refused still resolves its WHERE aliases — otherwise one bad join buries
    # its real reason under a pile of "unknown alias".
    aliases = _aliases(from_match, source_doctype, join_match)

    join = None
    if join_count == 1 and "subquery / nested SELECT" not in reasons:
        if not join_match or not from_match:
            reasons.append("join present but not a simple `tab<DocType>` … ON <a> = <b>")
        else:
            join, problem = _build_join(
                source_doctype,
                _dt(join_match.group(2)),
                (join_match.group(1) or "INNER").upper(),
                " ".join(join_match.group(4).split()),
                aliases,
            )
            if problem:
                reasons.append(problem)

    filters, filter_problems = _parse_filters(statement, aliases, reasons)
    reasons.extend(filter_problems)

    return {
        "supported": not reasons,
        "reasons": reasons,
        "doctypes": doctypes,
        "source_doctype": source_doctype,
        "aggregations": _parse_aggregations(statement, aliases, reasons),
        "filters": filters,
        "group_by": _parse_group_by(statement, aliases, reasons),
        "join": join,
    }


def _aliases(from_match, source_doctype, join_match) -> dict:
    """``{alias or table name (lowercased): DocType}`` for this statement.

    Both spellings are keys because real SQL uses both: Metabase writes
    ```tabPurchase Order`.`ref``` and a person writes ``b.`ref```.
    """
    aliases: dict[str, str] = {}
    for match, doctype, alias_group in (
        (from_match, source_doctype, 2),
        (join_match, _dt(join_match.group(2)) if join_match else None, 3),
    ):
        if not doctype:
            continue
        aliases[doctype.lower()] = doctype
        alias = match.group(alias_group) if match else None
        if alias:
            aliases[alias.lower()] = doctype
    return aliases


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
