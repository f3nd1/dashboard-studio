from __future__ import annotations

import re

# A Frappe table is `tab<DocType>` with a LOWERCASE `tab` — Frappe creates them
# that way, and Metabase's compiled SQL quotes the real name. The prefix is
# therefore matched case-sensitively everywhere, via (?-i:tab) where the rest of
# the pattern still needs IGNORECASE for its keywords.
#
# This is load-bearing, not tidiness. Metabase names a derived table after the
# HUMANIZED table name, so joining `tabAssessment Result Detail` produces the
# alias `TabAssessment Result Detail - Name` — capital T. Matched
# case-insensitively, that alias read as a table called "Assessment Result
# Detail - Name": a name in no alias map, so the join refused while insisting
# the query did not contain the shape it plainly contained, and a DocType that
# does not exist, which `_table_columns` would then refuse on.
_TAB = r"(?-i:tab)"
TABLE_PATTERN = re.compile(r"`" + _TAB + r"([^`]+)`")

# Aggregations we can translate into a Dashboard Studio metric today.
_AGG_PATTERN = re.compile(r"\b(COUNT|SUM|AVG)\s*\(\s*([^)]*?)\s*\)", re.IGNORECASE)
_JOIN_PATTERN = re.compile(r"\bJOIN\b", re.IGNORECASE)

# A table alias is the word after a table name, bare or backticked. Metabase
# names its derived tables things like `Student Applicant Model - Name`, so the
# backticked form has to allow spaces and punctuation — \w+ alone silently
# failed to see them, and every later lookup of that alias then failed too.
#
# No keyword exclusion list: a keyword swallowed here only ever adds an
# unreachable key to the alias map (nobody writes ``WHERE.column``), and the one
# place it could truncate a real match — the alias slot in _JOIN_TABLE — is
# already covered by the required ``ON`` after it, which makes the regex
# backtrack. An exclusion list was tried and removed: no statement's analysis
# changed with or without it.
_ALIAS = r"(?:\s+(?:AS\s+)?(?:`(?P<alias_q>[^`]+)`|(?P<alias>\w+)))?"

# A column's qualifier: a real table, a backticked alias, or a bare alias. Named
# groups because each pattern below uses this exactly once, and positional
# numbering across three alternatives is how a group index silently goes stale.
_QUALIFIER = (r"(?:`" + _TAB + r"(?P<table>[^`]+)`"
              r"|`(?P<alias_q>[^`]+)`|(?P<alias>\w+))")

_FROM_TABLE = re.compile(r"\bFROM\s+`" + _TAB + r"([^`]+)`" + _ALIAS, re.IGNORECASE)
# JOIN `tabX` [alias] ON <condition>. The strategy word in front of it decides
# the Insights join type, so it is captured rather than skipped over.
_JOIN_TABLE = re.compile(
    r"\b(?:(?P<strategy>LEFT|RIGHT|FULL|INNER|CROSS)\s+)?(?:OUTER\s+)?"
    r"JOIN\s+`" + _TAB + r"(?P<joined>[^`]+)`" + _ALIAS
    # GROUP/ORDER need their BY: "Purchase Order" is a real DocType, and a bare
    # \bORDER\b truncates the ON clause in the middle of the table name.
    + r"\s+ON\s+(?P<on>.+?)(?=\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|$)",
    re.IGNORECASE | re.DOTALL,
)

# SQL join keyword -> Insights JoinType. A bare JOIN is an INNER JOIN in MySQL,
# which is what the site runs — that is the SQL standard's default, not a guess
# of ours. CROSS has no Insights equivalent and refuses by name.
JOIN_STRATEGIES = {"INNER": "inner", "LEFT": "left", "RIGHT": "right", "FULL": "full"}

# ``a.`col` `` / ``  `tabX`.`col` `` / ``col`` -> qualifier + column. Anchored at
# both ends on purpose: a function call, an arithmetic expression or a literal
# does not match, and therefore refuses rather than being half-read.
_QUALIFIED = re.compile(r"^(?:" + _QUALIFIER + r"\.)?`?(?P<column>[\w ]+?)`?$", re.IGNORECASE)
# A join side must be qualified — ``ON ref = a.po`` does not say which table
# `ref` belongs to, and there is no safe way to pick one.
_ON_SIDE = re.compile(r"^" + _QUALIFIER + r"\.`?(?P<column>[\w ]+?)`?$", re.IGNORECASE)

_CONDITION = re.compile(
    r"^\s*(?:" + _QUALIFIER + r"\.)?`?(?P<column>[\w ]+?)`?"
    r"\s*(?P<operator>=|!=|<>|>=|<=|>|<|\bLIKE\b|\bIN\b)\s*(?P<value>.+?)\s*$",
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


# --------------------------------------------------------------------------
# Metabase's own wrapper subqueries
#
# Metabase compiles a drag-and-drop question into SQL that wraps each joined
# table in derived tables. The real thing is checked in at
# reference/metabase/duration_from_counselling_to_admission.sql, and it nests
# two of them:
#
#   LEFT JOIN (
#     SELECT `__mb_source`.`name` AS `name`, … every column …
#     FROM ( select * from `tabStudent Applicant` ) AS `__mb_source`
#   ) AS `Student Applicant Model - Name` ON …
#
# Both levels are pure projections of one table. A projection with no WHERE, no
# GROUP BY, no aggregate, no DISTINCT, no LIMIT, no join and no item that
# renames or computes returns exactly the rows of the table it reads, so
# replacing it with that table is an identity — provable, not hopeful. That is
# the ONLY shape flattened here. Anything else stays a subquery and is refused
# by name, because a WHERE or an aggregate in there changes which rows come back
# and flattening it would answer a different question without failing.
# --------------------------------------------------------------------------

_SELECT_FROM = re.compile(r"^SELECT\s+(.+?)\s+FROM\s+(.+)$", re.IGNORECASE | re.DOTALL)

# The FROM source must be `tabX` and NOTHING else, optionally aliased (the alias
# is inside the derived table and goes away with it). Anchored at both ends, and
# that anchoring is the guard: a WHERE, a GROUP BY, a LIMIT, a JOIN, a UNION and
# a nested subquery all sit after the table name, so all of them fail to match
# and the wrapper is left alone.
#
# A keyword blocklist was written alongside this and removed: every case it
# caught was already caught here or by _PROJECTED, and a redundant check that
# cannot be made to fail is one a later reader would wrongly trust.
_ONLY_TABLE = re.compile(r"^`" + _TAB + r"([^`]+)`(?:\s+(?:AS\s+)?(?:`[^`]+`|\w+))?$",
                         re.IGNORECASE)
# One projected column: `q`.`col` [AS `col`]. The alias must repeat the column
# name or it is a rename, not a passthrough.
#
# The name has to START with a letter or underscore, which is what every Frappe
# column does. Without that, `SELECT 1 FROM `tabX`` read as a projection of a
# column called "1" and the wrapper was flattened away — a literal column is not
# the table's, and the outer query may be reading it.
_PROJECTED = re.compile(
    r"^(?:(?:`[^`]+`|\w+)\.)?`?([A-Za-z_][\w ]*?)`?(?:\s+AS\s+`?([A-Za-z_][\w ]*?)`?)?$",
    re.IGNORECASE)
_AGGREGATE_ITEM = re.compile(r"^(?:COUNT|SUM|AVG|MIN|MAX)\s*\(.*\)$", re.IGNORECASE | re.DOTALL)
_TRAILING_ALIAS = re.compile(r"\s+AS\s+(?:`[^`]+`|\w+)$", re.IGNORECASE)

# Metabase appends its own absolute row cap to every question it compiles — the
# real sample carries LIMIT 1048575 on a report nobody limited. That exact value
# is dropped as the export cap it is; ANY other LIMIT refuses by name, because a
# "top 10" converted without its limit counts every row instead, silently.
#
# ponytail: an exact match on the observed constant, not a threshold. Read off
# Metabase's compiled output in reference/, not from Metabase's source. The
# residual case — a report genuinely truncated at 1,048,575 rows — is what the
# verification gate is for: the two numbers would differ and it would refuse.
METABASE_ROW_CAP = 1048575
_LIMIT = re.compile(r"\bLIMIT\s+(\d+)", re.IGNORECASE)


def _skip_quoted(text: str, i: int) -> int:
    """Index just past the quoted run starting at ``i``, which is a quote."""
    end = text.find(text[i], i + 1)
    return len(text) if end < 0 else end + 1


def _matching_paren(text: str, start: int) -> int:
    """Index of the ')' closing the '(' at ``start``, or -1.

    Backticked identifiers and string literals are skipped, via the same helper
    _split_items uses — there the skipping is load-bearing and tested (a comma
    inside a name splits the projection in half). Here it only ever prevents a
    MISSED flattening: a mis-paired bracket yields text that is not a
    passthrough, so the wrapper is left alone and refused. Failure direction is
    refusal, which is why there is no test pinning it.
    """
    depth, i = 0, start
    while i < len(text):
        char = text[i]
        if char in "`'\"":
            i = _skip_quoted(text, i)
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _split_items(text: str) -> list[str]:
    """A comma-separated list -> its items, ignoring commas inside () or ``."""
    items, current, depth, i = [], [], 0, 0
    while i < len(text):
        char = text[i]
        if char in "`'\"":
            end = _skip_quoted(text, i)
            current.append(text[i:end])
            i = end
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(char)
        i += 1
    items.append("".join(current))
    return [item.strip() for item in items if item.strip()]


def _passthrough_table(inner: str) -> str | None:
    """The single table a pure-projection subquery reads, or None.

    None means "not provably the same thing as a table", and the caller must
    leave it alone.
    """
    match = _SELECT_FROM.match(" ".join(inner.split()))
    if not match:
        return None
    items, source = match.group(1).strip(), match.group(2).strip()
    base = _ONLY_TABLE.match(source)
    if not base:
        return None
    if items != "*":
        for item in _split_items(items):
            projected = _PROJECTED.match(item)
            if not projected:
                return None
            alias = projected.group(2)
            if alias and alias.strip() != projected.group(1).strip():
                return None
    return "`tab" + base.group(1) + "`"


def _unwrap_once(sql: str) -> str:
    """Replace the first passthrough derived table found, or return sql as-is."""
    i = 0
    while i < len(sql):
        char = sql[i]
        if char in "`'\"":
            i = _skip_quoted(sql, i)
            continue
        if char != "(":
            i += 1
            continue
        close = _matching_paren(sql, i)
        if close < 0:
            return sql
        table = _passthrough_table(sql[i + 1:close])
        if table:
            return sql[:i] + table + sql[close + 1:]
        # Not a passthrough — but something nested inside it might be.
        i += 1
    return sql


def unwrap_derived_tables(sql: str) -> str:
    """Flatten Metabase's passthrough wrappers; leave every other subquery alone.

    Runs innermost-outwards by repetition: the outer wrapper only becomes a
    passthrough once the inner one it reads has been replaced by a table.
    """
    if not isinstance(sql, str):
        raise TypeError("sql must be a string")
    # The real ones nest two deep. The cap is a runaway guard, not a limit on
    # what is legitimate — anything still wrapped after it stays a subquery and
    # is refused, which is the safe direction.
    for _ in range(8):
        rewritten = _unwrap_once(sql)
        if rewritten == sql:
            break
        sql = rewritten
    return sql


def _select_problems(statement: str) -> list[str]:
    """Items in the SELECT list this converter would silently drop.

    The SELECT list is not otherwise read — operations come from the FROM, the
    WHERE, the GROUP BY and the aggregate. So a computed column used to vanish
    without a word, and the converted query answered a smaller question than the
    report it came from.
    """
    match = re.search(r"\bSELECT\b(.+?)\bFROM\b", statement, re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    problems = []
    for item in _split_items(match.group(1)):
        text = " ".join(item.split())
        named = _TRAILING_ALIAS.sub("", text).strip()
        if text == "*" or _AGGREGATE_ITEM.match(named) or _QUALIFIED.match(named):
            continue
        label = text[len(named):].strip()[3:].strip().strip("`") or named
        problems.append(
            f"the SELECT list computes '{label}', which this converter does not "
            "translate — Insights would get the query without that column"
        )
    return problems


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
    return _qualifier_of(match), match.group("column").strip()


def _qualifier_of(match):
    """The qualifier a match found, however it was spelled."""
    return (match.group("table") or match.group("alias_q") or match.group("alias"))


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
    doctype = aliases.get((_qualifier_of(match) or "").lower())
    if not doctype:
        return None
    return {"doctype": doctype, "column": match.group("column").strip()}


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
        qualifier = _qualifier_of(cm)
        # Lowercase to match the engine's ALLOWED_OPERATORS convention.
        field = cm.group("column").strip()
        op, value = cm.group("operator").lower(), cm.group("value").strip()
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
    # Metabase's own passthrough wrappers come off FIRST, so every check below
    # reads the query somebody actually asked for rather than the scaffolding
    # Metabase compiled around it. Only provable identities are removed; a
    # wrapper that filters or aggregates survives and is refused as a subquery.
    statement = unwrap_derived_tables(sql.strip().rstrip(";"))

    # Subquery / nested SELECT: more than one SELECT keyword.
    subquery = len(re.findall(r"\bSELECT\b", statement, re.IGNORECASE)) > 1
    if subquery:
        reasons.append("subquery / nested SELECT")
    else:
        # Only meaningful once there is one SELECT list to read.
        reasons.extend(_select_problems(statement))

    for value in _LIMIT.findall(statement):
        if int(value) != METABASE_ROW_CAP:
            reasons.append(
                f"LIMIT {value} — this converter does not translate a row limit, and "
                "dropping it would count every row instead of that many"
            )

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
    if join_count == 1 and not subquery:
        if not join_match or not from_match:
            reasons.append("join present but not a simple `tab<DocType>` … ON <a> = <b>")
        else:
            join, problem = _build_join(
                source_doctype,
                _dt(join_match.group("joined")),
                (join_match.group("strategy") or "INNER").upper(),
                " ".join(join_match.group("on").split()),
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
    for match, doctype in (
        (from_match, source_doctype),
        (join_match, _dt(join_match.group("joined")) if join_match else None),
    ):
        if not doctype:
            continue
        aliases[doctype.lower()] = doctype
        alias = (match.group("alias_q") or match.group("alias")) if match else None
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
