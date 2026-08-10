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
# An aggregate's argument, admitting EXACTLY ONE nested call — `AVG(CAST(x AS
# double))` — and never two. Bracketless text, or one call whose own argument
# is bracketless; `[^()]` cannot cross a bracket, so `AVG(CAST(ABS(x) AS
# double))` matches nothing and refuses, and `SUM(a) * 100 / COUNT(*)` still
# cannot pass for a plain aggregate. That last one is why this is written out
# rather than loosened to `.*`: as `.*` it read a whole expression as one
# aggregate and dropped the arithmetic in silence.
_ONE_NESTED_ARG = r"(?:[^()]|[A-Za-z_]\w*\s*\([^()]*\))*"

_AGG_PATTERN = re.compile(r"\b(COUNT|SUM|AVG)\s*\(\s*(" + _ONE_NESTED_ARG +
                          r")\s*\)", re.IGNORECASE)
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
    # \bORDER\b truncates the ON clause in the middle of the table name. The
    # next JOIN ends this ON clause too, or join 1 swallows join 2.
    + r"\s+ON\s+(?P<on>.+?)(?=\b(?:(?:LEFT|RIGHT|FULL|INNER|CROSS)\s+)?(?:OUTER\s+)?JOIN\b"
    + r"|\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|$)",
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
# A BARE name has to start with a letter or underscore. Without that,
# `SELECT 1 FROM `tabX`` read as a projection of a column called "1" and the
# wrapper was flattened away — a literal column is not the table's, and the
# outer query may be reading it. A BACKTICKED name may start with a digit:
# backticks are what make it an identifier rather than a literal, and UCC's
# survey DocTypes really do have columns called `1_3_months` and `2k_4k` —
# requiring a letter there made every wrapper touching those tables refuse as
# "not an identity" for a reason no message named.
_PROJECTED = re.compile(
    r"^(?:(?:`[^`]+`|\w+)\.)?"
    r"(?:`(?P<col_q>[\w][\w ]*?)`|(?P<col>[A-Za-z_][\w ]*?))"
    r"(?:\s+AS\s+(?:`(?P<alias_q>[\w][\w ]*?)`|(?P<alias>[A-Za-z_][\w ]*?)))?$",
    re.IGNORECASE)
# ONE aggregate call and nothing else. `.*` between the parentheses matched
# `SUM(a) * 100 / COUNT(*)` — it starts with an aggregate name and ends with
# a bracket — so a whole expression read as a plain aggregate and its
# arithmetic was skipped in silence. No nested parentheses either: an
# aggregate over something this cannot read must reach the expression
# check, which refuses by name.
_AGGREGATE_ITEM = re.compile(r"^(?:COUNT|SUM|AVG|MIN|MAX)\s*\(" +
                             _ONE_NESTED_ARG + r"\)$",
                             re.IGNORECASE | re.DOTALL)
_TRAILING_ALIAS = re.compile(r"\s+AS\s+(?:`(?P<alias_q>[^`]+)`|(?P<alias>\w+))$",
                             re.IGNORECASE)

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


def _clause_text(text: str) -> str:
    """A WHERE/GROUP BY region, cut at the ')' that closes the query it is in.

    The region is found by scanning forward to GROUP BY / ORDER BY / LIMIT / end,
    which sweeps straight past the end of an enclosing subquery: a WHERE inside a
    Metabase wrapper came back as ``… = 'Aggregated Performance Index' ) AS
    `__mb_source```, which is not ``field <op> value`` and refused as unparsed —
    naming a condition that was, on its own, perfectly ordinary.
    """
    depth, i = 0, 0
    while i < len(text):
        char = text[i]
        if char in "`'\"":
            i = _skip_quoted(text, i)
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                return text[:i]
            depth -= 1
        i += 1
    return text


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


# A derived table may only be unwrapped where a table is what the syntax
# expects. See the note in _unwrap_once for what happens otherwise.
_TABLE_POSITION = re.compile(r"\b(?:FROM|JOIN)\s*$", re.IGNORECASE)


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
            column = (projected.group("col_q") or projected.group("col")).strip()
            alias = projected.group("alias_q") or projected.group("alias")
            if alias and alias.strip() != column:
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
        # Only where a TABLE belongs. "This derived table returns exactly the
        # rows of `tabX`" is a fact about a row source, and substituting the
        # table name is only meaningful after FROM or JOIN. Anywhere else the
        # parentheses mean something different, and the swap is a category
        # error that produces valid-looking SQL:
        #
        #   WHERE `name` = ( SELECT `name` FROM `tabChild` )
        #     ->  WHERE `name` = `tabChild`
        #
        # which converted CLEANLY into a filter comparing a column against the
        # literal text "`tabChild`" — a report that returns no rows instead of
        # refusing. Every check downstream was happy, because by then the
        # subquery was gone.
        if char != "(" or not _TABLE_POSITION.search(sql[:i]):
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


# --------------------------------------------------------------------------
# Metabase's OTHER outer wrapper: "re-select a question that is already finished"
#
# When the question aggregates and Metabase does not need to add anything, it
# still wraps the compiled query and re-selects its columns by name:
#
#   SELECT `__mb_source`.`Child_d700d9c7` AS `Child_d700d9c7`,
#          `__mb_source`.`avg`            AS `avg`
#   FROM ( SELECT `Child_70767e69`.`year` AS `Child_d700d9c7`,
#                 AVG(`Child_70767e69`.`value`) AS `avg`
#          FROM `tabParent` LEFT JOIN … WHERE … GROUP BY … ORDER BY … )
#        AS `__mb_source`
#
# This is the MIRROR of lift_renaming_wrapper, not the same rule. There the
# outer aggregates and the inner does not, so the aggregate is folded down onto
# the inner. Here the inner is a complete query — its own join, WHERE, GROUP BY
# and aggregate — and the outer does nothing at all, so it is REMOVED rather
# than lifted. Neither rule can fire on the other's shape: an aggregate is not
# a projection item, and an inner GROUP BY stops the lift.
#
# What makes the removal provable, and each part is checked below:
#   - the outer has no WHERE, GROUP BY, ORDER BY, LIMIT or second table (there
#     is nothing after the wrapper's alias at all), so it changes no rows;
#   - every item is one of the wrapper's own columns under its own name, so it
#     renames nothing;
#   - the set of items equals the set of columns the inner produces, so it
#     drops no column — a narrowing projection would answer a smaller question,
#     which is the fault a dropped computed column and a dropped LIMIT were.
# Together: the outer returns exactly the inner's rows and exactly its columns.
# --------------------------------------------------------------------------


def drop_passthrough_wrapper(sql: str) -> str:
    """Remove an outer wrapper that only re-selects the finished query inside it.

    Returns the statement unchanged when any part of the proof above fails, so
    the subquery check downstream turns it into a named refusal.
    """
    if not isinstance(sql, str):
        raise TypeError("sql must be a string")
    match = _FROM_PAREN.search(sql)
    if not match:
        return sql
    opened = match.end() - 1
    closed = _matching_paren(sql, opened)
    if closed < 0:
        return sql
    head, inner, after = sql[:match.start()], sql[opened + 1:closed], sql[closed + 1:]
    named = _WRAPPER_ALIAS.match(after)
    if not named:
        return sql
    wrapper = named.group(1) or named.group(2)
    # Nothing may follow the wrapper. A WHERE, GROUP BY, ORDER BY or LIMIT out
    # here is the outer query doing something, and this rule holds only while it
    # does nothing whatsoever.
    if after[named.end():].strip():
        return sql
    selected = re.match(r"\s*SELECT\b(.+)$", head, re.IGNORECASE | re.DOTALL)
    if not selected:
        return sql
    # `<wrapper>`.`col` [AS `col`] and nothing else. Qualified by THIS wrapper:
    # an item qualified by anything else is a column from somewhere this rule
    # has not proved anything about.
    # Leading digits allowed in both halves: everything here is qualified by
    # the wrapper's own dot, so nothing that matches can be a bare literal.
    item_pattern = re.compile(
        r"^(?:`" + re.escape(wrapper) + r"`|" + re.escape(wrapper) + r")\."
        r"`?(?P<column>[\w][\w ]*?)`?"
        r"(?:\s+AS\s+`?(?P<alias>[\w][\w ]*?)`?)?$", re.IGNORECASE)
    taken = []
    for item in _split_items(selected.group(1)):
        found = item_pattern.match(" ".join(item.split()))
        if not found:
            return sql
        alias = (found.group("alias") or "").strip()
        if alias and alias != found.group("column").strip():
            return sql
        taken.append(found.group("column").strip())
    produced = _produced_columns(inner)
    if produced is None or sorted(taken) != sorted(produced):
        return sql
    return inner.strip()


def _produced_columns(inner: str) -> list[str] | None:
    """The names a query's SELECT list hands out, or None if one cannot be read.

    None is not "no columns" — it means the caller has not proved what comes
    back and must leave the statement alone.
    """
    match = _SELECT_FROM.match(" ".join(inner.split()))
    if not match:
        return None
    names = []
    for item in _split_items(match.group(1)):
        text = " ".join(item.split())
        aliased = _TRAILING_ALIAS.search(text)
        if aliased:
            names.append((aliased.group("alias_q") or aliased.group("alias")).strip())
            continue
        # No AS: only a bare column names itself. An expression does not, and
        # guessing what the database would call it is how a column goes missing.
        plain = _QUALIFIED.match(text)
        if not plain:
            return None
        names.append(plain.group("column").strip())
    return names


# --------------------------------------------------------------------------
# Metabase's outer wrapper: "aggregate over a joined source"
#
# When a Metabase question aggregates over joined tables, the joins become a
# derived table and the aggregate runs outside it:
#
#   SELECT `__mb_source`.`Child_a3e4a16b`, AVG(`__mb_source`.`Observe Value`)
#   FROM ( SELECT `Child_3c522490`.`metric` AS `Child_a3e4a16b`, …
#          FROM `tabParent` LEFT JOIN … LEFT JOIN … WHERE … ) AS `__mb_source`
#   GROUP BY `__mb_source`.`Child_a3e4a16b`
#
# That wrapper is NOT a passthrough — it renames every column — so the rule in
# unwrap_derived_tables leaves it alone, correctly. But it is still removable,
# for a different and equally provable reason: it neither filters nor
# aggregates, so it returns the same ROWS as the query inside it, and a rename
# is a bijection on columns. Mapping the outer references back through the
# wrapper's own `X AS Y` list therefore recovers the original query exactly.
#
# So the two rules are different things and both are needed: unwrap_ replaces a
# derived table that IS its table; this lifts an aggregate onto the query a
# derived table renames.
# --------------------------------------------------------------------------

_FROM_PAREN = re.compile(r"\bFROM\s*\(", re.IGNORECASE)
_WRAPPER_ALIAS = re.compile(r"\s*(?:AS\s+)?(?:`([^`]+)`|(\w+))", re.IGNORECASE)
# One item of the wrapper's SELECT list: a qualified column, renamed.
#
# `* 1` is Metabase's cast: it writes it to coerce a column to a number before
# aggregating. At UCC the column it does this to (`actual_value`) is a Frappe
# Data field, so Metabase has been averaging a TEXT column by silent coercion
# all along — see ADR-009. The `* 1` is carried through the rewrite rather than
# dropped, so the coercion stays visible to the type check and to the person
# reading the converted query. Refused in a GROUP BY, where grouping by a
# coerced value is not grouping by the column.
_WRAPPER_ITEM = re.compile(
    r"^(?P<expr>(?:`[^`]+`|\w+)\.(?:`[^`]+`|\w+))(?P<arith>\s*\*\s*1)?"
    r"\s+AS\s+(?:`(?P<alias_q>[^`]+)`|(?P<alias>\w+))$", re.IGNORECASE)
# Anything here means the wrapper changes which rows come back, so its contents
# cannot simply be re-pointed at.
_WRAPPER_BLOCKS = re.compile(r"\b(GROUP\s+BY|HAVING|DISTINCT|UNION|LIMIT)\b", re.IGNORECASE)


# A wrapper item that COMPUTES a per-row column, rather than renaming one.
# Metabase writes these to build a chart label or to force a type:
#
#   CONCAT('', YEAR(`tabX`.`d`)) AS `Year`     -> mutate  Year = year(d)
#   CAST(`tabX`.`v` AS double)   AS `v`        -> cast    v -> Decimal
#
# Each becomes an OPERATION placed before the summarize, which is an ordering
# Insights itself stores (`source -> mutate -> summarize`, query s39rc7j648 on
# the live site). Only the forms actually seen are read; anything else refuses
# by name, because this builds text a query engine evaluates.
#
# `year` is lowercase because that is the spelling in a stored expression on
# that site (`year_col = year(custom_proposed_date)`). No other function is
# accepted — the vocabulary widens only to what has been observed.
_CALL = re.compile(r"^(?P<name>[A-Za-z_]\w*)\s*\((?P<args>.*)\)$",
                   re.IGNORECASE | re.DOTALL)
# `CONCAT('', x)` is Metabase making a value into a TEXT label so the chart axis
# is categorical. Insights accepts a numeric grouping — proved by a stored
# Integer dimension — so the wrapper is dropped and the value keeps its own
# type. The values are the same years either way.
_EMPTY_STRING = re.compile(r"^(?:''|\"\")$")
# MySQL date-part function -> Insights expression function. Read from
# `functions.py` at v3.12.2, where each is the same one-argument shape as
# `year`: `def month(column: ir.DateValue): return column.month()`. MySQL's
# MONTH/QUARTER/DAY return the same numbers, so these carry across unchanged.
#
# WEEK is deliberately absent: MySQL's takes a mode argument that decides which
# day starts a week, and `week_of_year` takes none.
_DATE_PARTS = {"YEAR": "year", "MONTH": "month", "QUARTER": "quarter",
               "DAY": "day", "DAYOFMONTH": "day"}

# Functions Insights has under a familiar name that count differently.
_RENUMBERED_DATE_PARTS = ("DAYOFWEEK", "WEEKDAY")

_CAST_TYPES = {"double": "Decimal", "decimal": "Decimal", "float": "Decimal",
               "real": "Decimal", "signed": "Integer", "integer": "Integer",
               "int": "Integer", "unsigned": "Integer", "char": "String"}


# One column reference, anywhere in a string — the scanning counterpart of the
# anchored `_QUALIFIED`. Quoted or qualified only: Metabase always quotes, and a
# bare word left unmatched lands in the residue below, which refuses. That is
# the safe direction.
# The column halves accept a LEADING DIGIT — `1_3_months`, `2k_4k` are real
# columns on UCC's survey DocTypes — because both positions are identifiers by
# construction: one follows a qualifier's dot, the other is inside backticks.
# A bare literal can reach neither. The bare-QUALIFIER half keeps its letter
# start; that one can be a bare word, and `1.5` must not read as column 5 of
# table 1.
_COLUMN_REF = re.compile(r"(?:`[^`]+`|\b[A-Za-z_]\w*)\.`?[\w][\w ]*`?"
                         r"|`[\w][\w ]*`")


# --------------------------------------------------------------------------
# A CASE that maps values to labels
#
# `case(condition, value, *args)` in `functions.py` at v3.12.2 takes the pairs
# FLAT, with an optional trailing else:
#
#   case(age > 30, 'Above 30', age > 20, 'Above 20')
#   case(age > 18, 'Eligible', 'Not Eligible')      <- odd count: the last is else_
#
# and its body is `ibis.cases(*branches)` — with no `else_` when the count is
# even, which is NULL, exactly as a SQL CASE with no ELSE returns NULL.
#
# The comparison spelling is Python's, read off the same docstrings:
# `status == 'Active'`, `age > 18`. Not SQL's single `=`.
#
# What is accepted is deliberately much narrower than what `case` can express,
# because this becomes text a query engine evaluates. A condition is one
# column — or one date part of one column — compared against one literal. A
# result is one literal. Everything else refuses by name.
# --------------------------------------------------------------------------
_CASE = re.compile(r"^CASE\b(?P<body>.+)\bEND$", re.IGNORECASE | re.DOTALL)
_WHEN = re.compile(r"\bWHEN\b(?P<condition>.+?)\bTHEN\b(?P<value>.+?)"
                   r"(?=\bWHEN\b|\bELSE\b|$)", re.IGNORECASE | re.DOTALL)
_ELSE = re.compile(r"\bELSE\b(?P<value>(?:(?!\bWHEN\b).)+)$", re.IGNORECASE | re.DOTALL)
_COMPARISON = re.compile(r"^(?P<left>.+?)\s*(?P<operator><=|>=|<>|!=|=|<|>)\s*"
                         r"(?P<right>.+)$", re.DOTALL)
# A quoted literal with no quote, backslash or backtick inside it. That is the
# boundary that matters: the expression is a string somebody else evaluates, and
# a literal that cannot terminate itself early cannot become code. Brackets and
# commas inside one are harmless for the same reason.
_SAFE_STRING = re.compile(r"^'(?P<text>[^'\"\\`\r\n]*)'$")
_SAFE_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
_CASE_OPERATORS = {"=": "==", "!=": "!=", "<>": "!=", "<": "<", "<=": "<=",
                   ">": ">", ">=": ">="}


def _case_literal(text: str):
    """``(rendered, kind)`` for a literal, or ``(None, None)``."""
    text = text.strip()
    string = _SAFE_STRING.match(text)
    if string:
        return "'" + string.group("text") + "'", "String"
    if _SAFE_NUMBER.match(text):
        return text, "Decimal" if "." in text else "Integer"
    return None, None


def _case_operand(text: str, aliases: dict, reasons: list):
    """``(rendered, column, table)`` for the left of a comparison, or Nones.

    One column, or one date part of one column. A date part is spelled by the
    same `_DATE_PARTS` table the standalone computed columns use, so `MONTH`
    means `month` here for the same reason it does there.
    """
    text = text.strip()
    call = _CALL.match(text)
    if call:
        name = call.group("name").upper()
        if name not in _DATE_PARTS:
            return None, None, None
        qualifier, column = _split_ref(call.group("args"))
        if not column:
            return None, None, None
        return (f"{_DATE_PARTS[name]}({column})", column,
                _resolve(qualifier, aliases, reasons))
    qualifier, column = _split_ref(text)
    if not column:
        return None, None, None
    return column, column, _resolve(qualifier, aliases, reasons)


def _case_column(text: str, alias: str, aliases: dict, reasons: list):
    """A CASE mapping values to labels -> a `case(...)` mutate."""
    match = _CASE.match(text.strip())
    if not match:
        return None, "CASE without an END"
    body = match.group("body").strip()
    if not re.match(r"^WHEN\b", body, re.IGNORECASE):
        # `CASE x WHEN 1 THEN …` compares x against each value; `CASE WHEN …`
        # evaluates each condition. Reading one as the other silently changes
        # what every branch tests.
        return None, "CASE <expression> WHEN … (the simple form)"
    branches = _WHEN.findall(body)
    if not branches:
        return None, "CASE with no WHEN … THEN"
    otherwise = _ELSE.search(body)
    parts, columns, tables, kinds = [], [], [], set()
    for condition, value in branches:
        comparison = _COMPARISON.match(" ".join(condition.split()))
        if not comparison:
            return None, f"CASE WHEN {' '.join(condition.split())[:40]}"
        if re.search(r"\b(AND|OR|NOT|LIKE|IN|BETWEEN|IS)\b", condition, re.IGNORECASE):
            # One comparison per branch. A compound condition is expressible in
            # the dialect and has not been read, and `IS NULL` / `LIKE` are
            # their own questions — see ADR-014.
            return None, f"CASE WHEN {' '.join(condition.split())[:40]}"
        rendered, column, table = _case_operand(comparison.group("left"), aliases, reasons)
        if not rendered:
            return None, (f"CASE testing {comparison.group('left').strip()[:40]}, "
                          "which is not a column or a date part of one")
        literal, _ = _case_literal(comparison.group("right"))
        if literal is None:
            return None, (f"CASE comparing against {comparison.group('right').strip()[:40]}, "
                          "which is not a plain number or a quoted label")
        result, kind = _case_literal(value)
        if result is None:
            return None, (f"CASE producing {' '.join(value.split())[:40]}, which is not "
                          "a plain number or a quoted label")
        kinds.add(kind)
        columns.append(column)
        tables.append(table)
        parts.append(f"{rendered} {_CASE_OPERATORS[comparison.group('operator')]} "
                     f"{literal}")
        parts.append(result)
    if otherwise:
        result, kind = _case_literal(otherwise.group("value"))
        if result is None:
            return None, (f"CASE ELSE {' '.join(otherwise.group('value').split())[:40]}, "
                          "which is not a plain number or a quoted label")
        kinds.add(kind)
        parts.append(result)
    if kinds == {"Integer", "Decimal"}:
        kinds = {"Decimal"}
    if len(kinds) != 1:
        # A column holds one type. Branches returning a number and a label are
        # two different columns wearing one name.
        return None, ("CASE whose branches return " + " and ".join(sorted(kinds))
                      + " — a column holds one type")
    return {"alias": alias, "kind": "mutate",
            "columns": columns, "tables": tables,
            "expression": "case(" + ", ".join(parts) + ")",
            "data_type": kinds.pop(), "requires": None}, ""


def _computed_column(text: str, alias: str, aliases: dict, reasons: list):
    """``(computed, offending)`` — exactly one is truthy.

    `computed` is ``{alias, kind, columns, tables, expression, data_type,
    requires}`` where kind is "mutate" or "cast"; `offending` names the token
    that stopped it. A `data_type` of None means "type it from the source
    column", which only the translator can do.

    `columns` and `tables` are LISTS — one entry per column the computation
    reads, in the order it reads them. A single-column shape carries a list of
    one rather than a scalar, because the join carries what these name and a
    two-argument function whose second column was dropped there converts
    cleanly and fails the moment the query is opened. `requires` says what kind
    of column those have to be — "number", "date", or None for a computation
    that reads any column safely — and only the translator knows types.
    """
    text = text.strip()
    # `col * 5` — a SCALE FACTOR. Metabase writes it to put a 1-5 rating on a
    # 0-100 scale, and it is not the `* 1` cast of ADR-009: `* 1` leaves every
    # value alone, `* 5` is arithmetic that changes them. It needs no new
    # vocabulary — arithmetic in a mutate expression is what the FIRST captured
    # expression was, `(avg_of_idx + avg_of_docstatus) / 2` — and no new
    # ordering, since ADR-012 established mutate-before-summarize.
    #
    # Exactly one column, with numeric literals around it. The residue after
    # removing the column has to be arithmetic and contain an operator, which
    # is the same allowlist ADR-011 applies to an expression over aggregates,
    # and for the same reason: this becomes text a query engine evaluates.
    if re.match(r"^CASE\b", text, re.IGNORECASE):
        return _case_column(text, alias, aliases, reasons)
    references = _COLUMN_REF.findall(text)
    if references and not _CALL.match(text):
        residue = _COLUMN_REF.sub("", text)
        named = {_split_ref(reference)[1] for reference in references}
        if (_ARITHMETIC_ONLY.match(residue) and any(c in residue for c in "+-*/")
                and len(named) == 1):
            qualifier, column = _split_ref(references[0])
            if column:
                return {"alias": alias, "kind": "mutate",
                        "columns": [column],
                        "tables": [_resolve(qualifier, aliases, reasons)],
                        "expression": _COLUMN_REF.sub(column, text),
                        # Typed from the column it reads: `rating * 5` is a
                        # number only if `rating` is one, and the parser has no
                        # types.
                        "data_type": None, "requires": "number"}, ""
    call = _CALL.match(text.strip())
    if not call:
        return None, text.strip()[:40]
    name, args = call.group("name").upper(), call.group("args").strip()
    if name == "CONCAT":
        parts = _split_items(args)
        if len(parts) == 2 and _EMPTY_STRING.match(parts[0].strip()):
            return _computed_column(parts[1], alias, aliases, reasons)
        return None, "CONCAT"
    if name in _DATE_PARTS:
        qualifier, column = _split_ref(args)
        if not column:
            return None, f"{name} of something that is not a column"
        return {"alias": alias, "kind": "mutate",
                "columns": [column],
                "tables": [_resolve(qualifier, aliases, reasons)],
                "expression": f"{_DATE_PARTS[name]}({column})",
                "data_type": "Integer", "requires": None}, ""
    if name in _RENUMBERED_DATE_PARTS:
        # Refused for a reason worth spelling out, because Insights HAS a
        # function of this name and using it would be wrong. `day_of_week`
        # returns ibis's `day_of_week.index()`, which counts 0 = Monday;
        # MySQL's DAYOFWEEK counts 1 = Sunday. Same idea, different numbers,
        # and every row would be off by a day and a half with nothing failing.
        return None, (f"{name} — Insights numbers the days differently "
                      "(0 = Monday, against MySQL's 1 = Sunday)")
    if name == "DATEDIFF":
        # MySQL: `DATEDIFF(a, b)` is a - b, in whole days. Insights spells the
        # same thing `date_diff(a, b, 'day')` — read from two stored
        # expressions on the live site, `date_diff(modified, creation, 'day')`,
        # where `modified` is always the later date and the values came back
        # POSITIVE. So the argument order carries across unchanged, and the
        # unit is the third argument.
        #
        # `TIMESTAMPDIFF(DAY, a, b)` is NOT accepted: it puts the unit first
        # and subtracts the other way round, so translating it as this would
        # negate every value. It has not been seen in a capture either.
        parts = _split_items(args)
        if len(parts) != 2:
            return None, f"DATEDIFF with {len(parts)} arguments"
        read = [_split_ref(part) for part in parts]
        if not all(column for _, column in read):
            return None, "DATEDIFF of something that is not a column"
        return {"alias": alias, "kind": "mutate",
                "columns": [column for _, column in read],
                "tables": [_resolve(qualifier, aliases, reasons)
                           for qualifier, _ in read],
                "expression": "date_diff({}, {}, 'day')".format(
                    *[column for _, column in read]),
                # A count of whole days.
                "data_type": "Integer", "requires": "date"}, ""
    if name == "CAST":
        cast = re.match(r"^(?P<value>.+?)\s+AS\s+(?P<type>\w+)\s*$", args,
                        re.IGNORECASE | re.DOTALL)
        if not cast:
            return None, "CAST without an AS"
        data_type = _CAST_TYPES.get(cast.group("type").lower())
        if not data_type:
            return None, "CAST to " + cast.group("type")
        qualifier, column = _split_ref(cast.group("value"))
        if not column:
            return None, "CAST of something that is not a column"
        if column != alias:
            # `cast` converts a column IN PLACE — CastArgs is {column,
            # data_type} with nowhere to put a new name. Casting AND renaming
            # is two things, and only one of them is expressible.
            return None, f"CAST renaming '{column}' to '{alias}'"
        return {"alias": alias, "kind": "cast",
                "columns": [column],
                "tables": [_resolve(qualifier, aliases, reasons)],
                "expression": "", "data_type": data_type, "requires": None}, ""
    return None, name


# --------------------------------------------------------------------------
# An inline GROUP BY expression, lifted into a named column
#
# Metabase compiles the same question two ways. Wrapped, the expression is a
# named column inside a subquery and the outer query groups by that name —
# `lift_renaming_wrapper` handles that one. FLAT, the function sits inline in
# the SELECT list, the GROUP BY and the ORDER BY at once:
#
#   SELECT MONTH(`t`.`d`) AS `d`, AVG(...) FROM `tabT`
#   GROUP BY MONTH(`t`.`d`) ORDER BY MONTH(`t`.`d`) ASC
#
# Three refusals, one cause. Naming the expression once and pointing all three
# at that name turns it into the shape this converter already emits: a mutate,
# then a summarize grouping by it, then an order_by on it.
#
# **Position, not vocabulary.** Only a call `_computed_column` already accepts
# is lifted, so the allowlist is untouched — DAYOFWEEK and WEEK refuse here for
# exactly the reasons they refuse anywhere else, by name.
# --------------------------------------------------------------------------

# One call over one qualified-or-quoted column. Deliberately NOT anchored: it
# has to find the same expression wherever it appears.
_INLINE_CALL = re.compile(
    r"\b(?P<name>[A-Za-z_]\w*)\s*\(\s*"
    r"(?P<arg>(?:`[^`]+`|\b[A-Za-z_]\w*)\s*\.\s*`[^`]+`|`[^`]+`)\s*\)")


def _clause_span(statement: str, keyword: str):
    """``(start, end)`` of one clause's body, or None."""
    match = re.search(keyword + r"\b(.+?)(?=\bGROUP\s+BY\b|\bORDER\s+BY\b"
                      r"|\bLIMIT\b|$)", statement, re.IGNORECASE | re.DOTALL)
    return (match.start(1), match.end(1)) if match else None


# YEAR() in a GROUP BY is a DIMENSION GRANULARITY, not a computed column.
#
# `Dimension` in `query.types.ts` carries `granularity?: GranularityType`, and
# `ibis_utils.translate_dimension` applies it with `column.truncate("Y")` and
# then casts the result back to the column's own date type. So the dimension
# stays a Date and can be a chart's X axis, which a numeric year cannot: the
# axis only offers date-compatible columns.
#
# It is only equivalent for YEAR. `truncate("Y")` partitions rows by calendar
# year exactly as `YEAR()` does — same rows, same count, only the label differs.
# `truncate("M")` groups month-WITHIN-year, while `MONTH()` pools every January
# across every year: 12 rows against forty-odd. Those are different questions,
# so MONTH, QUARTER and DAY keep the numeric mutate and stay unchartable. That
# is Insights' limit — a month-of-year genuinely is not a date — and regrouping
# to satisfy a chart would answer something nobody asked.
_GRANULARITY_OF = {"YEAR": "year"}


def lift_group_by_expressions(sql: str, aliases: dict | None = None):
    """``(statement, computed, granularities)`` — name each expression, point at it.

    Expressions in the GROUP BY **and in the WHERE** are lifted, and each is
    then rewritten in the SELECT list and the ORDER BY too, so every clause
    reads the same column. The WHERE is included because `ibis_utils.py` applies
    operations in list order and `apply_filter` filters the query *so far* — so
    a filter naming a mutated column works, provided the mutate is emitted
    first, which `sql_ops` now does.

    A `YEAR()` in the GROUP BY comes back in `granularities` instead: the
    grouping is the plain date column with `granularity: "year"`, which stays a
    Date and can therefore be charted. A `YEAR()` in a WHERE still becomes a
    mutate — a granularity is a property of a dimension, and a filter has none.

    The new name is `<function>_of_<column>` rather than whatever the SELECT
    list called it. Metabase names the item after the column it reads —
    `MONTH(`t`.`d`) AS `d`` — and a mutate creating `d` from `d` is either
    self-referential or shadows the source. The generated name cannot collide
    with the column it reads; `sql_ops` refuses if it collides with any other.
    """
    if not isinstance(sql, str):
        raise TypeError("sql must be a string")
    grouping = _clause_span(sql, r"\bGROUP\s+BY")
    where = _clause_span(sql, r"\bWHERE")
    if not grouping and not where:
        return sql, [], {}
    reasons: list[str] = []
    computed, names, granularities = [], {}, {}

    def scan(span, as_granularity):
        if not span:
            return
        for match in _INLINE_CALL.finditer(sql[span[0]:span[1]]):
            _, column = _split_ref(match.group("arg"))
            if not column:
                continue
            name = match.group("name").upper()
            key = (name, column)
            # The two routes are tracked SEPARATELY, and the same call may take
            # both. `WHERE YEAR(d) = 2025 GROUP BY YEAR(d)` needs a granularity
            # on the dimension AND a mutate for the filter to compare against;
            # de-duplicating across both dropped the mutate and left the filter
            # comparing the raw date column to 2025 — a query that converts,
            # runs, and returns nothing. So each route de-duplicates against
            # its own record, and the route is decided first.
            granular = as_granularity and name in _GRANULARITY_OF
            if key in (granularities if granular else names):
                continue
            # The grouping route: no mutate, no new column, just the date
            # column carrying a granularity.
            if granular:
                granularities[key] = {"column": column,
                                      "table": _resolve(match.group("arg").split(".")[0]
                                                        .strip().strip("`"), aliases or {},
                                                        reasons)
                                      if "." in match.group("arg") else None,
                                      "granularity": _GRANULARITY_OF[name]}
                continue
            alias = f"{match.group('name').lower()}_of_{column}"
            built, _offending = _computed_column(match.group(0), alias,
                                                 aliases or {}, reasons)
            # Not translatable: leave it exactly as it was. The reader for that
            # clause then refuses it by name, with the message it always had.
            if not built:
                continue
            names[key] = alias
            computed.append(built)

    scan(grouping, True)
    scan(where, False)
    if not names and not granularities:
        return sql, [], {}

    def rewrite(text: str, as_granularity: bool) -> str:
        def one(match):
            _, column = _split_ref(match.group("arg"))
            key = (match.group("name").upper(), column)
            if as_granularity and key in granularities:
                # `YEAR(`t`.`d`)` -> `` `d` ``. The grouping is the column
                # itself; the granularity is what makes it a year, and `sql_ops`
                # refuses if it cannot attach one.
                return "`" + column + "`"
            alias = names.get(key)
            return f"`{alias}`" if alias else match.group(0)
        return _INLINE_CALL.sub(one, text)

    # Every region that may name it, rebuilt back to front so the earlier spans
    # keep their offsets. The WHERE takes the mutate even where the GROUP BY
    # took a granularity: a granularity is a property of a dimension, and a
    # filter has none.
    spans = [(span, region != "WHERE")
             for span, region in ((_clause_span(sql, r"\bSELECT"), "SELECT"),
                                  (_clause_span(sql, r"\bWHERE"), "WHERE"),
                                  (_clause_span(sql, r"\bGROUP\s+BY"), "GROUP BY"),
                                  (_clause_span(sql, r"\bORDER\s+BY"), "ORDER BY"))
             if span]
    statement = sql
    for (start, end), as_granularity in sorted(spans, reverse=True):
        statement = (statement[:start]
                     + rewrite(statement[start:end], as_granularity)
                     + statement[end:])
    return statement, computed, {entry["column"]: entry["granularity"]
                                 for entry in granularities.values()}


def lift_renaming_wrapper(sql: str, aliases: dict | None = None):
    """Fold a renaming wrapper into the query it wraps.

    Returns ``(statement, reasons, computed)``, where `computed` is the wrapper
    items that COMPUTE a column rather than renaming one. Each becomes an
    operation before the summarize; the alias travels on as an ordinary column
    name, which is what lets the outer GROUP BY and aggregate reference it. Every bail-out returns the statement as it
    was, so the subquery check downstream turns it into a named reason; the
    reasons list is for the one case where a generic "subquery" would hide
    something specific worth reading.
    """
    if not isinstance(sql, str):
        raise TypeError("sql must be a string")
    reasons: list[str] = []
    computed: list[dict] = []
    aliases = aliases or {}
    match = _FROM_PAREN.search(sql)
    if not match:
        return sql, reasons, computed
    opened = match.end() - 1
    closed = _matching_paren(sql, opened)
    if closed < 0:
        return sql, reasons, computed
    head, inner, after = sql[:match.start()], sql[opened + 1:closed], sql[closed + 1:]

    named = _WRAPPER_ALIAS.match(after)
    if not named:
        return sql, reasons, computed
    wrapper = named.group(1) or named.group(2)
    tail = after[named.end():]

    # The outer query may only group, sort and select. Its own WHERE would have
    # to be ANDed with the inner one, and a second derived table is a different
    # shape entirely.
    if re.search(r"\bWHERE\b", tail, re.IGNORECASE) or "(" in tail:
        return sql, reasons, computed
    if len(re.findall(r"\bSELECT\b", head, re.IGNORECASE)) != 1:
        return sql, reasons, computed
    # Exactly one SELECT inside: a second means a per-table wrapper this pass
    # could not flatten, so the joins are not readable and there is nothing to
    # lift onto. (A bare "( in source" check was written alongside this and
    # removed — it caught nothing this did not, and a stray parenthesis in an
    # ON clause fails the join parse downstream anyway, which is a refusal.)
    if len(re.findall(r"\bSELECT\b", inner, re.IGNORECASE)) != 1:
        return sql, reasons, computed
    if _WRAPPER_BLOCKS.search(inner):
        return sql, reasons, computed

    inner_from = re.search(r"\bFROM\b", inner, re.IGNORECASE)
    if not inner_from:
        return sql, reasons, computed
    items, source = inner[:inner_from.start()], inner[inner_from.start():]
    if not re.match(r"\s*SELECT\b", items, re.IGNORECASE):
        return sql, reasons, computed
    renames = {}
    for item in _split_items(items.strip()[len("SELECT"):]):
        text = " ".join(item.split())
        parsed = _WRAPPER_ITEM.match(text)
        if not parsed:
            # Not a rename. It may still be a computed column this can turn
            # into an operation — `CONCAT('', YEAR(d)) AS Year` and
            # `CAST(v AS double) AS v` are the forms Metabase writes.
            named_item = _TRAILING_ALIAS.search(text)
            if not named_item:
                return sql, reasons, computed
            item_alias = (named_item.group("alias_q") or named_item.group("alias")).strip()
            built, offending = _computed_column(
                _TRAILING_ALIAS.sub("", text).strip(), item_alias, aliases, reasons)
            if not built:
                reasons.append(
                    f"the wrapper computes '{item_alias}' using {offending}, which "
                    "this converter does not translate — `year(...)`, "
                    "`DATEDIFF(later, earlier)`, a scale factor like `col * 5` and "
                    "a numeric `CAST` are the calculated columns it reads, because "
                    "those are the ones Insights has been seen to store"
                )
                return sql, reasons, computed
            computed.append(built)
            # The alias travels on as a plain column name: the operation this
            # becomes creates a real column by that name before the summarize.
            renames[item_alias] = (f"`{item_alias}`", False)
            continue
        alias = parsed.group("alias_q") or parsed.group("alias")
        # The `* 1` is kept in the mapped text: dropping it here would hide a
        # cast the query asked for, and the aggregate would then be typed as
        # though the column were numeric.
        renames[alias] = (parsed.group("expr") + (parsed.group("arith") or ""),
                          bool(parsed.group("arith")))

    reference = re.compile(
        r"(?:`" + re.escape(wrapper) + r"`|\b" + re.escape(wrapper) + r"\b)"
        r"\.(?:`(?P<quoted>[^`]+)`|(?P<bare>\w+))")

    # Grouping by `x * 1` is not grouping by x unless x is a number, and the
    # types are not known here. Refuse rather than find out in the chart.
    grouping = re.search(r"\bGROUP\s+BY\b(.+?)(?=\bORDER\s+BY\b|\bLIMIT\b|$)",
                         tail, re.IGNORECASE | re.DOTALL)
    if grouping:
        for found in reference.finditer(grouping.group(1)):
            name = found.group("quoted") or found.group("bare")
            entry = renames.get(name)
            if entry and entry[1]:
                reasons.append(
                    f"the query groups by '{name}', which is {entry[0]} — a value "
                    "coerced to a number, not the column itself. Aggregating a "
                    "coerced column is translated; grouping by one is not, because "
                    "every row that is not a number coerces to the same 0"
                )
                return sql, reasons, computed

    unmapped = []

    def swap(found):
        name = found.group("quoted") or found.group("bare")
        entry = renames.get(name)
        if not entry:
            unmapped.append(name)
            return found.group(0)
        return entry[0]

    rewritten_head = reference.sub(swap, head)
    rewritten_tail = reference.sub(swap, tail)
    if unmapped:
        return sql, reasons, computed
    return (rewritten_head.rstrip() + " " + source.strip() + " "
            + rewritten_tail.strip()).strip(), reasons, computed


# A SELECT item that computes over aggregates — `( AVG(a) + AVG(b) ) / 2.0`.
#
# Insights stores one of these as a `mutate`, and its expression is a PLAIN TEXT
# math string referencing the measure names the preceding `summarize` defines:
#
#   {"type": "mutate", "new_name": "combined_avg", "data_type": "Auto",
#    "expression": {"type": "expression",
#                   "expression": "(avg_of_idx + avg_of_docstatus) / 2"}}
#
# read out of a hand-built query's own Operations JSON at v3.12.2, not guessed.
#
# The aggregate calls are replaced by numbered slots and what REMAINS must be
# arithmetic and nothing else. That is an allowlist, deliberately: this builds a
# string Insights will evaluate, so a token nobody has read the meaning of must
# not travel into it. CAST, YEAR, CONCAT, a bare column, a string literal — all
# refuse BY NAME, and the name is the token that stopped it.
_SLOT = "@@{}@@"
_SLOT_ANY = re.compile(r"@@\d+@@")
_ARITHMETIC_ONLY = re.compile(r"^[\s0-9.+\-*/()]*$")


# `CAST(<expression> AS <type>)` around an expression over aggregates. There is
# no cast FUNCTION in Insights' expression language — `functions.py` at v3.12.2
# defines 85 of them and none casts — and the `cast` OPERATION converts a named
# column, so there is nowhere to put this one. It is removable instead, but only
# where removing it is an identity.
#
# To a FLOAT type it is: the thing inside is arithmetic over aggregates, which
# is numeric by the time it converts, and widening a number to a float leaves it
# alone. That is the whole of Metabase's `CAST(… AS double)`, which it writes to
# force float division.
#
# To an INTEGER type it is not — `CAST(5/2 AS signed)` is 2 — and to `char` it
# is not either. Those still refuse.
_VALUE_PRESERVING_CAST = ("double", "decimal", "float", "real")
_CAST_TAIL = re.compile(r"\s+AS\s+(?P<type>\w+)\s*$", re.IGNORECASE)


def _strip_value_preserving_cast(text: str) -> str:
    """Replace every `CAST(x AS double)` with `(x)`. Anything else is untouched.

    Metabase does NOT always write the cast outermost — report 1680 has
    ``CAST( AVG(a) + AVG(b) AS double ) / 2.0``, where it wraps one operand of a
    division. So this rewrites in place rather than peeling a wrapper off.

    **The parentheses are the whole point.** Dropping them turns that into
    ``AVG(a) + AVG(b) / 2.0``, which is a perfectly valid expression, converts
    without complaint, and is a different number. Keeping the brackets the CAST
    already had makes the rewrite an identity in the arithmetic as well as in
    the type.
    """
    out, index = [], 0
    while True:
        found = re.compile(r"\bCAST\s*\(", re.IGNORECASE).search(text, index)
        if not found:
            out.append(text[index:])
            return "".join(out)
        depth, cursor = 1, found.end()
        while cursor < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[cursor], 0)
            cursor += 1
        if depth:
            # Unbalanced: not something to rewrite blind.
            out.append(text[index:])
            return "".join(out)
        inner = text[found.end():cursor - 1]
        tail = _CAST_TAIL.search(inner)
        if not tail or tail.group("type").lower() not in _VALUE_PRESERVING_CAST:
            out.append(text[index:cursor])
            index = cursor
            continue
        out.append(text[index:found.start()])
        out.append("(" + _strip_value_preserving_cast(inner[:tail.start()]).strip() + ")")
        index = cursor


def _expression_from_item(text: str, aliases: dict, reasons: list):
    """``(expression, offending_tokens)`` — exactly one of them is truthy."""
    text = _strip_value_preserving_cast(text)
    template, aggregates = text, []
    for index, match in enumerate(list(_AGG_PATTERN.finditer(text))):
        aggregates.append(_aggregation_from(match.group(1), match.group(2),
                                            aliases, reasons))
        template = template.replace(match.group(0), _SLOT.format(index), 1)
    residue = _SLOT_ANY.sub("", template)
    if not aggregates:
        # Arithmetic on literals alone is not something to build a summarize
        # around, and without an aggregate there are no measure names to
        # reference.
        return None, ["no aggregate"]
    if not _ARITHMETIC_ONLY.match(residue):
        return None, sorted(set(re.findall(r"[A-Za-z_]\w*", residue))) or ["?"]
    return {"template": template, "aggregates": aggregates}, []


def _parse_select_list(statement: str, aliases: dict,
                       reasons: list) -> tuple[list[dict], list[str]]:
    """``(expressions, problems)`` for the SELECT list.

    The rest of the SELECT list is not otherwise read — operations come from
    the FROM, the WHERE, the GROUP BY and the aggregate — so a computed column
    used to vanish without a word, and the converted query answered a smaller
    question than the report it came from. Now it is either translated into a
    `mutate` or refused, never dropped.
    """
    match = re.search(r"\bSELECT\b(.+?)\bFROM\b", statement, re.IGNORECASE | re.DOTALL)
    if not match:
        return [], []
    expressions, problems = [], []
    for item in _split_items(match.group(1)):
        text = " ".join(item.split())
        named = _TRAILING_ALIAS.sub("", text).strip()
        if text == "*" or _AGGREGATE_ITEM.match(named) or _QUALIFIED.match(named):
            continue
        label = text[len(named):].strip()[3:].strip().strip("`") or named
        expression, offending = _expression_from_item(named, aliases, reasons)
        if expression:
            expressions.append(dict(expression, label=label))
            continue
        if offending == ["no aggregate"]:
            problems.append(
                f"the SELECT list computes '{label}', which has no aggregate in it — "
                "this converter translates arithmetic OVER aggregates, so there is "
                "nothing here for a summarize to produce"
            )
            continue
        message = (
            f"the SELECT list computes '{label}' using {', '.join(offending)}, which "
            "this converter does not translate — arithmetic over aggregates is "
            "translated (+ - * / and numbers), and nothing else is, because the "
            "expression becomes text that Insights evaluates"
        )
        if "CAST" in offending:
            # Worth saying, because the obvious next thought is "there is a cast
            # operation already". There is, and it converts a COLUMN; there is
            # no operation that casts the result of an expression.
            message += (
                ". A `cast` operation converts a column, not the result of an "
                "expression, so the two are not interchangeable here"
            )
        problems.append(message)
    return expressions, problems


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


def _build_join(scope: list, joined: str, strategy: str, clause: str, aliases: dict):
    """One ON clause -> the two named columns Insights needs, or a reason why not.

    The result is oriented by TABLE: ``join_column`` always belongs to the table
    being joined and ``source_column`` to one already in scope, whichever side
    of the ``=`` they were typed on. Insights' join_condition means exactly that
    — its left_column is a column of the result so far — and orienting by
    writing order instead would silently swap them for half of all real queries.

    ``scope`` is the FROM table plus every table joined before this one, in
    order. That is what makes N joins the same problem as one: each join adds
    its table to the scope the next one may attach to, and Insights takes them
    as N separate join operations anyway.
    """
    join_type = JOIN_STRATEGIES.get(strategy)
    if not join_type:
        return None, f"{strategy} JOIN has no Insights equivalent"
    if joined in scope:
        # Two copies of one table — a self join, or the same child table joined
        # twice. `columns` is keyed by DocType, so the two cannot be told apart.
        return None, (
            f"this query joins {joined} more than once (or to itself), and the columns "
            "of the two copies cannot be told apart from the SQL"
        )

    parts = clause.split("=")
    if len(parts) != 2:
        return None, (
            f"the join condition '{clause}' is not a single equality — this converter "
            "translates only `a.column = b.column`"
        )
    sides = {}
    for side in (_on_side(parts[0], aliases), _on_side(parts[1], aliases)):
        if side:
            sides[side["doctype"]] = side["column"]
    if joined not in sides or len(sides) != 2:
        return None, (
            f"the join condition '{clause}' does not name one column from {joined} and "
            "one from a table already in the query — this converter translates only "
            "`a.column = b.column`"
        )
    source_table = next(table for table in sides if table != joined)
    if source_table not in scope:
        return None, (
            f"the join condition '{clause}' attaches {joined} to {source_table}, which "
            "this query has not joined yet"
        )
    return {
        "doctype": joined,
        "join_type": join_type,
        "on": clause,
        "source_table": source_table,
        "source_column": sides[source_table],
        "join_column": sides[joined],
    }, None


# What a WHERE condition contains when it does not fit `column <op> value`.
# Named in the refusal rather than left as "unparsed", because a message that
# says only "could not be read" files every one of these into a single opaque
# group — and that group then reads as a parser bug worth chasing when most of
# it is ordinary unsupported SQL. Order matters: the first match wins, so the
# constructs that carry other constructs inside them come first.
_WHY_UNPARSED = (
    (re.compile(r"\(\s*SELECT\b", re.IGNORECASE), "a subquery"),
    (re.compile(r"\bCASE\b", re.IGNORECASE), "a CASE expression"),
    (re.compile(r"\bEXISTS\b", re.IGNORECASE), "EXISTS"),
    (re.compile(r"\bNOT\s+LIKE\b|\bLIKE\b", re.IGNORECASE), "LIKE"),
    (re.compile(r"\bNOT\s+IN\b|\bIN\s*\(", re.IGNORECASE), "IN"),
    (re.compile(r"\bBETWEEN\b", re.IGNORECASE), "BETWEEN"),
    (re.compile(r"\bIS\s+(?:NOT\s+)?NULL\b", re.IGNORECASE), "IS NULL"),
    (re.compile(r"\bREGEXP\b|\bRLIKE\b", re.IGNORECASE), "REGEXP"),
    (re.compile(r"^\s*NOT\b", re.IGNORECASE), "NOT"),
    (re.compile(r"[A-Za-z_]\w*\s*\(", re.IGNORECASE), "a function call"),
)


def _why_unparsed(part: str) -> str:
    """Name the construct that stopped a WHERE condition being read."""
    text = " ".join(part.split())
    for pattern, what in _WHY_UNPARSED:
        if pattern.search(text):
            return (f"unparsed WHERE condition using {what}, which this converter "
                    f"does not translate: {text[:60]}")
    return f"unparsed WHERE condition: {text[:60]}"


def _unwrap_parens(text: str) -> str:
    """`( a = 1 )` -> `a = 1`, repeatedly. Anything else comes back unchanged.

    Only ever applied where the logical operator is uniform, so the brackets are
    grouping that changes nothing. A mixed clause refuses before this runs, and
    that is what makes discarding them safe.
    """
    text = text.strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        for index, character in enumerate(text):
            depth += {"(": 1, ")": -1}.get(character, 0)
            if depth == 0 and index < len(text) - 1:
                return text  # the first bracket closes early: not a wrapper
        text = text[1:-1].strip()
    return text


def _parse_filters(sql: str, aliases: dict,
                   reasons: list) -> tuple[list[dict], list[str], str]:
    """``(filters, problems, logic)`` for the WHERE clause; logic is And or Or.

    Flag-don't-guess: a condition that doesn't fit the simple ``field <op>
    value`` shape makes the whole query unsupported — a dropped or mangled
    condition would migrate a metric that counts the wrong rows.

    **AND and OR in one clause refuse.** Insights' `FilterGroupArgs` is
    ``{ logical_operator; filters: FilterArgs[] }`` and `FilterArgs` is a rule
    or an expression — never another group — so the structure is one flat list
    under one operator, with no nesting to put a precedence in. `a AND b OR c`
    means `(a AND b) OR c` in SQL, and there is no shape here that says so.
    """
    m = re.search(
        r"\bWHERE\b(.+?)(?=\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|$)",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return [], [], "And"
    clause = _clause_text(m.group(1))
    # Textual, so a literal " OR " inside a string value counts too —
    # conservative by design, and it refuses rather than mis-grouping.
    has_or = bool(re.search(r"\bOR\b", clause, re.IGNORECASE))
    has_and = bool(re.search(r"\bAND\b", clause, re.IGNORECASE))
    if has_or and has_and:
        return [], ["AND and OR in one WHERE clause — Insights' filter group is one "
                    "flat list under one operator, with nowhere to put the precedence "
                    "that decides which conditions bind together"], "And"
    logic = "Or" if has_or else "And"
    clause = _unwrap_parens(clause)
    filters, problems = [], []
    # Naive split on the one operator in play — sufficient for the flat WHERE
    # clauses in scope, and a mixed clause has already refused above.
    for part in re.split(r"\bOR\b" if has_or else r"\bAND\b", clause, flags=re.IGNORECASE):
        part = _unwrap_parens(part)
        # NOT whitespace-normalised. `\s*` around the operator already spans a
        # newline, so a condition wrapped across lines parses as it is; joining
        # the lines first would rewrite a multi-line string literal instead.
        cm = _CONDITION.match(part)
        if not cm:
            problems.append(_why_unparsed(part))
            continue
        qualifier = _qualifier_of(cm)
        # Lowercase to match the engine's ALLOWED_OPERATORS convention.
        field = cm.group("column").strip()
        op, value = cm.group("operator").lower(), cm.group("value").strip()
        filters.append({"field": field, "operator": op, "value": value.strip("'\""),
                        "table": _resolve(qualifier, aliases, reasons)})
    return filters, problems, logic


def _parse_group_by(sql: str, aliases: dict, reasons: list) -> tuple[list[dict], list[str]]:
    m = re.search(r"\bGROUP\s+BY\b(.+?)(?=\bORDER\s+BY\b|\bLIMIT\b|$)", sql, re.IGNORECASE | re.DOTALL)
    if not m:
        return [], []
    out: list[dict] = []
    problems: list[str] = []
    for part in _split_items(_clause_text(m.group(1))):
        item = part.strip().rstrip(",").strip()
        if not item:
            continue
        qualifier, field = _split_ref(item)
        # An item that is not exactly one column is REFUSED, not skipped.
        # `_QUALIFIED` is anchored, so ``col * 1`` reads as nothing at all — and
        # it used to be dropped in silence, which turned a grouping by a coerced
        # value (0 for every row that is not a number) into a grouping by the
        # raw column: a different question, answered without a word.
        if not field:
            problems.append(
                f"the query groups by '{item}', which is not a plain column — this "
                "converter groups by columns only, and dropping the rest of an "
                "expression would answer a different question"
            )
            continue
        out.append({"field": field, "table": _resolve(qualifier, aliases, reasons)})
    return out, problems


# ``AVG(`x`.`col` * 1)`` — Metabase's cast to a number. Recognised so the
# coercion travels with the aggregate instead of being silently unwound into a
# plain column reference, which would type it as whatever the column is.
_TIMES_ONE = re.compile(r"^(?P<expr>.+?)\s*\*\s*1$")
# The other spelling of the same thing. ADR-009 reads `col * 1` on a text
# column as a cast, because that is what Metabase means by it; `CAST(col AS
# double)` says so outright. MySQL agrees on the values — both take a leading
# numeric prefix and give 0 for anything else — so this is ADR-009's argument
# with the implication removed, and it emits ADR-009's cast operation
# unchanged, disclosure and all.
#
# Only a FLOAT target. To `signed` it truncates and to `char` it stringifies;
# neither is this, and both keep refusing.
_CAST_ARG = re.compile(r"^CAST\s*\(\s*(?P<expr>.+?)\s+AS\s+(?P<type>\w+)\s*\)$",
                       re.IGNORECASE | re.DOTALL)


def _aggregation_from(function: str, argument: str, aliases: dict, reasons: list) -> dict:
    """One ``COUNT|SUM|AVG(...)`` call -> the dict the translator reads.

    One function, because the same call is read twice — once as the query's
    aggregate and once inside a computed SELECT item — and the two descriptions
    have to be identical or the expression's slots would not line up with the
    measures the summarize defines.
    """
    argument = argument.strip()
    if not argument or argument == "*":
        return {"function": function.upper(), "argument": "*", "table": None,
                "coerced": False}
    coerced = _TIMES_ONE.match(argument)
    if not coerced:
        cast = _CAST_ARG.match(argument.strip())
        if cast and cast.group("type").lower() in _VALUE_PRESERVING_CAST:
            coerced = cast
    if coerced:
        argument = coerced.group("expr").strip()
    qualifier, column = _split_ref(argument)
    return {"function": function.upper(), "argument": column or argument,
            "table": _resolve(qualifier, aliases, reasons),
            "coerced": bool(coerced)}


def _parse_aggregations(sql: str, aliases: dict, reasons: list) -> list[dict]:
    return [_aggregation_from(function, argument, aliases, reasons)
            for function, argument in _AGG_PATTERN.findall(sql)]


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
    # Three rewrites, in order, and each proves a different identity.
    # unwrap_ replaces a derived table that IS its table. drop_ removes an outer
    # wrapper that does nothing but re-select the finished query inside it.
    # lift_ folds an outer AGGREGATE onto the query a wrapper only renames.
    # Both of the last two need unwrap_ to have run, because a wrapper whose
    # joins are still wrapped has nothing readable inside it; and drop_ runs
    # before lift_ so that a wrapper it removes cannot be mistaken for one to
    # lift onto. They cannot both fire on the same statement: drop_ requires an
    # outer that does nothing, lift_ an outer that aggregates.
    flattened = drop_passthrough_wrapper(unwrap_derived_tables(sql.strip().rstrip(";")))
    # The lift resolves the qualifier of a computed column against the tables
    # the statement names, so it needs an alias map before the final one exists.
    # Built from the flattened text, which already has the real table names in
    # it — the wrapper aliases it would add are exactly the ones being removed.
    provisional = _aliases(_FROM_TABLE.search(flattened),
                           _dt((_FROM_TABLE.search(flattened) or [None, ""]).group(1))
                           if _FROM_TABLE.search(flattened) else None,
                           list(_JOIN_TABLE.finditer(flattened)))
    statement, lift_reasons, computed = lift_renaming_wrapper(flattened, provisional)
    reasons.extend(lift_reasons)
    # AFTER the wrapper rules: a wrapped query's expression is the wrapper's
    # business, and only what is left flat at this point is inline.
    statement, inline, granularities = lift_group_by_expressions(statement, provisional)
    computed = list(computed) + inline

    # Subquery / nested SELECT: more than one SELECT keyword.
    subquery = len(re.findall(r"\bSELECT\b", statement, re.IGNORECASE)) > 1
    if subquery:
        # Named for what it is to somebody who never wrote a subquery: Metabase
        # compiled one, and this one is not a plain passthrough of a single
        # table, so it cannot be flattened away without changing the answer.
        reasons.append(
            "subquery / nested SELECT — a subquery here is only removed when it is a "
            "plain projection of one table; this one filters, aggregates or joins, so "
            "removing it would change which rows are counted"
        )
    # The SELECT list is read further down, once the aliases exist: a computed
    # item may be an expression over aggregates, and reading its aggregates
    # needs to know which table each column belongs to.

    # A row limit IS an operation: `Limit = { type: 'limit'; limit: number }`,
    # read from `query.types.ts` at v3.12.2. It used to refuse because dropping
    # it would have counted every row instead of that many — that was the right
    # answer while there was nowhere to put it, and it is not any more.
    #
    # Metabase's own export cap is still dropped rather than translated: nobody
    # asked for it, it is not part of the question, and putting it on every
    # converted query would be noise that looks like a decision.
    limits = [int(value) for value in _LIMIT.findall(statement)
              if int(value) != METABASE_ROW_CAP]
    if len(set(limits)) > 1:
        reasons.append(
            f"{len(set(limits))} different LIMITs in one statement "
            f"({', '.join(str(v) for v in sorted(set(limits)))}) — which one bounds "
            "the result depends on where each one sits, and that is not read here"
        )
    limit = limits[0] if limits else None

    order_by, order_problems = _parse_order_by(statement)
    reasons.extend(order_problems)

    join_count = len(_JOIN_PATTERN.findall(statement))

    for pattern, message in _UNSUPPORTED_MARKERS:
        if pattern.search(statement):
            reasons.append(message)

    doctypes = [_dt(t) for t in discover_frappe_doctypes(statement)]

    # The source is the FROM table, NOT the first `tab…` in the text: a column of
    # the joined table can appear in the SELECT list first, and building the
    # query on that side is a different question with the same row count.
    from_match = _FROM_TABLE.search(statement)
    source_doctype = _dt(from_match.group(1)) if from_match else (doctypes[0] if doctypes else None)

    join_matches = list(_JOIN_TABLE.finditer(statement))
    # Built before the joins are validated so that a query whose ON clause is
    # refused still resolves its WHERE aliases — otherwise one bad join buries
    # its real reason under a pile of "unknown alias".
    aliases = _aliases(from_match, source_doctype, join_matches)

    joins = []
    if join_count and not subquery:
        if len(join_matches) != join_count or not from_match:
            reasons.append("join present but not a simple `tab<DocType>` … ON <a> = <b>")
        else:
            scope = [source_doctype]
            for match in join_matches:
                built, problem = _build_join(
                    scope,
                    _dt(match.group("joined")),
                    (match.group("strategy") or "INNER").upper(),
                    " ".join(match.group("on").split()),
                    aliases,
                )
                if problem:
                    reasons.append(problem)
                    joins = []
                    break
                joins.append(built)
                scope.append(built["doctype"])

    # Qualifiers that resolve to nothing are collected APART from the real
    # reasons. When a subquery survived, every alias inside it — Metabase's
    # `__mb_source` above all — is unknown by construction, and repeating
    # "'__mb_source' is not a table or alias" three times buries the one line
    # that says what is actually wrong under an internal name nobody typed.
    alias_reasons: list[str] = []
    filters, filter_problems, filter_logic = _parse_filters(statement, aliases, alias_reasons)
    reasons.extend(filter_problems)
    aggregations = _parse_aggregations(statement, aliases, alias_reasons)
    group_by, group_problems = _parse_group_by(statement, aliases, alias_reasons)
    reasons.extend(group_problems)
    expressions: list[dict] = []
    if not subquery:
        # Only meaningful once there is one SELECT list to read.
        expressions, select_problems = _parse_select_list(statement, aliases,
                                                          alias_reasons)
        reasons.extend(select_problems)
        # An aggregate inside a computed item is not ALSO a standalone
        # aggregate. Removed one-for-one so the "only one aggregate" rule keeps
        # counting the query's own aggregates and nothing else.
        for expression in expressions:
            for aggregate in expression["aggregates"]:
                if aggregate in aggregations:
                    aggregations.remove(aggregate)
    if not subquery:
        reasons.extend(alias_reasons)

    # De-duplicated, order preserved: the same fault found in the WHERE, the
    # GROUP BY and the aggregate is one thing wrong, not three.
    reasons = list(dict.fromkeys(reasons))
    return {
        "supported": not reasons,
        "reasons": reasons,
        "doctypes": doctypes,
        "source_doctype": source_doctype,
        "aggregations": aggregations,
        "expressions": expressions,
        "computed": computed,
        "filters": filters,
        "filter_logic": filter_logic,
        "group_by": group_by,
        "joins": joins,
        "order_by": order_by,
        "limit": limit,
        "granularities": granularities,
    }


_ORDER_ITEM = re.compile(r"^(?P<ref>.+?)(?:\s+(?P<direction>ASC|DESC))?$",
                         re.IGNORECASE | re.DOTALL)


def _parse_order_by(statement: str):
    """``([{column, direction}], problems)`` for the ORDER BY, if there is one.

    `OrderBy = { type: 'order_by' } & OrderByArgs` and `OrderByArgs =
    { column: Column; direction: 'asc' | 'desc' }` — read from `query.types.ts`
    at v3.12.2. Until that was read, an ORDER BY was discarded in silence, which
    cost a chart its reading order.

    The QUALIFIER is deliberately ignored. By this point a wrapper has been
    flattened or lifted, so an item may still be written `__mb_source`.`x`, and
    what has to exist is the output column `x` — which the translator checks
    against the names the summarize defines, where the ordering actually
    applies. Anything that is not a plain column refuses: ordering by an
    expression is a different operation, and guessing at one silently reorders
    the rows a chart reads.
    """
    match = re.search(r"\bORDER\s+BY\b(.+?)(?=\bLIMIT\b|$)", statement,
                      re.IGNORECASE | re.DOTALL)
    if not match:
        return [], []
    order_by, problems = [], []
    for item in _split_items(match.group(1)):
        text = " ".join(item.split())
        if not text:
            continue
        parsed = _ORDER_ITEM.match(text)
        direction = (parsed.group("direction") or "asc").lower()
        _, column = _split_ref(parsed.group("ref").strip())
        if not column:
            problems.append(
                f"ORDER BY '{parsed.group('ref').strip()}', which is not a plain "
                "column — Insights orders by a named column, and translating an "
                "expression as one would reorder the rows a chart reads"
            )
            continue
        order_by.append({"column": column, "direction": direction})
    return order_by, problems


def _aliases(from_match, source_doctype, join_matches) -> dict:
    """``{alias or table name (lowercased): DocType}`` for this statement.

    Both spellings are keys because real SQL uses both: Metabase writes
    ```tabPurchase Order`.`ref``` and a person writes ``b.`ref```.
    """
    pairs = [(from_match, source_doctype)]
    pairs += [(m, _dt(m.group("joined"))) for m in (join_matches or [])]
    aliases: dict[str, str] = {}
    for match, doctype in pairs:
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
