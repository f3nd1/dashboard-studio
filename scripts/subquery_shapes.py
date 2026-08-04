"""The subquery refusals, grouped by the SHAPE of the wrapper that survived.

    python scripts/subquery_shapes.py path/to/exported_sql/

`bulk_dry_run.py` says how many reports each blocker stops. When the answer is
"one blocker stops hundreds", this says **what those hundreds actually look
like**, so the next wrapper rule is written against a counted shape rather than
whichever example arrived first.

**Read-only.** It reads .sql files and calls `analyze_sql`, which is a pure
function. It creates nothing, needs no Bench, and executes nothing.

It reports FEATURES, not verdicts. Each surviving wrapper is described by what
is factually in it — the clauses the outer query carries, the kind of each item
in its SELECT list, what the inner query does, how deep the nesting goes — and
identical descriptions are grouped. Whether a group is *removable* is a separate
question with a separate proof, and answering it needs a real capture: the three
rules that exist were each written against one.

Deliberately not a to-do list. A group being large says where to look, not that
there is a rule to be had. Two of the three existing rules were possible only
because the wrapper provably returned the same rows as its inner query; a
wrapper that filters or aggregates does not, and no amount of frequency changes
that.

ponytail: no blank lines inside the function, and everything inside one
function with its imports. ``bench console`` runs an embedded IPython where
globals() and locals() are different dicts, so a bare exec(open(...).read())
would leave module-level names unreachable from the functions that need them.
"""

def _shapes():
    # noqa on the block: isort wants a blank line before the first-party
    # import, and a blank line here breaks the piped-paste form.
    import os  # noqa: I001
    import pathlib
    import re
    import sys
    # INSIDE the function on purpose — see the note above about bench console's
    # split namespaces.
    directory = ""
    examples_per_group = 3
    try:
        from dashboard_studio.integrations.metabase import parser
    except ImportError:
        here = globals().get("__file__")
        root = str(pathlib.Path(here).resolve().parents[1]) if here else os.getcwd()
        sys.path.append(root)
        from dashboard_studio.integrations.metabase import parser
    def rewritten(sql):
        """What the three existing rules leave behind — the actual residue."""
        statement, _ = parser.lift_renaming_wrapper(
            parser.drop_passthrough_wrapper(
                parser.unwrap_derived_tables(sql.strip().rstrip(";"))))
        return statement
    def clauses(text):
        found = []
        for name, pattern in (("where", r"\bWHERE\b"), ("group_by", r"\bGROUP\s+BY\b"),
                              ("order_by", r"\bORDER\s+BY\b"), ("limit", r"\bLIMIT\b"),
                              ("having", r"\bHAVING\b"), ("join", r"\bJOIN\b"),
                              ("union", r"\bUNION\b"), ("distinct", r"\bDISTINCT\b")):
            if re.search(pattern, text, re.IGNORECASE):
                found.append(name)
        return found
    def item_kind(item, wrapper):
        text = " ".join(item.split())
        if parser._AGGREGATE_ITEM.match(parser._TRAILING_ALIAS.sub("", text).strip()):
            return "aggregate"
        qualified = re.match(
            r"^(?:`" + re.escape(wrapper) + r"`|" + re.escape(wrapper) + r")\."
            r"`?(?P<column>[A-Za-z_][\w ]*?)`?"
            r"(?:\s+AS\s+`?(?P<alias>[A-Za-z_][\w ]*?)`?)?$", text, re.IGNORECASE)
        if qualified:
            alias = (qualified.group("alias") or "").strip()
            return "same" if not alias or alias == qualified.group("column").strip() \
                else "rename"
        if parser._QUALIFIED.match(parser._TRAILING_ALIAS.sub("", text).strip()):
            return "other_table"
        return "computed"
    def describe(sql):
        """A factual signature for the outermost surviving FROM-subquery."""
        match = parser._FROM_PAREN.search(sql)
        if not match:
            # The subquery is somewhere a wrapper rule never looks: a scalar in
            # the SELECT list, an IN (...), an EXISTS. A different problem
            # wearing the same refusal.
            return "no FROM-subquery — the nesting is elsewhere (IN/EXISTS/scalar)"
        opened = match.end() - 1
        closed = parser._matching_paren(sql, opened)
        if closed < 0:
            return "unbalanced parentheses — not readable as a wrapper"
        head, inner = sql[:match.start()], sql[opened + 1:closed]
        named = parser._WRAPPER_ALIAS.match(sql[closed + 1:])
        wrapper = (named.group(1) or named.group(2)) if named else ""
        tail = sql[closed + 1:][named.end():] if named else sql[closed + 1:]
        items = parser._split_items(re.sub(r"(?is)^\s*SELECT\b", "", head))
        kinds = sorted({item_kind(item, wrapper) for item in items if item.strip()})
        depth = len(re.findall(r"\bSELECT\b", inner, re.IGNORECASE))
        return (f"outer[{'+'.join(clauses(tail)) or 'nothing'}] "
                f"items[{','.join(kinds) or 'none'}] "
                f"inner[{'+'.join(clauses(inner)) or 'nothing'}] "
                f"selects_inside={depth}"
                f"{'' if wrapper else ' (wrapper has no alias)'}")
    directory = directory or next((a for a in sys.argv[1:] if os.path.isdir(a)), "")
    if not directory:
        print("Give me the same directory bulk_dry_run.py reads:")
        print("  python scripts/subquery_shapes.py path/to/exported_sql/")
        return
    files = sorted(pathlib.Path(directory).rglob("*.sql"))
    groups, failed = {}, []
    for path in files:
        try:
            text = path.read_text()
            reasons = parser.analyze_sql(text)["reasons"]
        except Exception as error:  # noqa: BLE001
            failed.append(f"{path.name}: {type(error).__name__}: {error}")
            continue
        if not any("subquery / nested SELECT" in reason for reason in reasons):
            continue
        try:
            signature = describe(rewritten(text))
        except Exception as error:  # noqa: BLE001
            signature = f"could not be described: {type(error).__name__}: {error}"
        groups.setdefault(signature, []).append((len(text), path))
    total = sum(len(rows) for rows in groups.values())
    print("=" * 78)
    print(f"{total} of {len(files)} reports refuse on a subquery, in "
          f"{len(groups)} distinct shapes")
    print("=" * 78)
    print("Each line is what is FACTUALLY in the wrapper the existing rules left")
    print("behind. Grouped by that, largest first. A big group says where to")
    print("look; whether it is removable needs its own proof, on a real capture.")
    print()
    for signature in sorted(groups, key=lambda key: -len(groups[key])):
        rows = sorted(groups[signature])
        print(f"{len(rows):>5}  {signature}")
        for size, path in rows[:examples_per_group]:
            print(f"         {path.name}  ({size} bytes)")
        if len(rows) > examples_per_group:
            print(f"         ...and {len(rows) - examples_per_group} more")
        print()
    if groups:
        biggest = max(groups, key=lambda key: len(groups[key]))
        smallest = sorted(groups[biggest])[0][1]
        print("=" * 78)
        print("Send this one back — it is the SMALLEST file in the LARGEST group,")
        print("so it is the shortest thing that represents the most reports:")
        print(f"   {smallest}")
        print("=" * 78)
    if failed:
        print()
        print(f"Could not be read ({len(failed)}):")
        for line in failed[:20]:
            print("   " + line)
    print()
    print("Nothing was written. No query was executed.")
    return groups


_shapes()
