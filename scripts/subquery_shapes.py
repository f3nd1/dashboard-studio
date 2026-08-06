"""The subquery refusals, grouped by the SHAPE of the wrapper that survived.

    python scripts/subquery_shapes.py path/to/exported_sql/

Under ``bench console`` there is no argv to pass, so set an environment
variable — do NOT set a `directory` variable before exec(), which cannot work
because the function declares its own and shadows it:

    import os
    os.environ['DASHBOARD_STUDIO_SQL_DIR'] = '/full/path/to/exported_sql'
    exec(open('apps/dashboard_studio/scripts/subquery_shapes.py').read())

argv is read ONLY when this file is run as a script. `bench --site grc console`
puts "grc" in sys.argv, and under the sites directory that IS a folder, so
scanning argv for "anything that is a directory" silently read the site folder
and reported a real number for the wrong two files. The resolved path and where
it came from are printed on every run.

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
    script_name = "subquery_shapes.py"
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
        statement = parser.lift_renaming_wrapper(
            parser.drop_passthrough_wrapper(
                parser.unwrap_derived_tables(sql.strip().rstrip(";"))))[0]
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
    basic = {"AVG", "SUM", "COUNT", "MIN", "MAX", "CAST", "+", "-", "*", "/"}
    def vocabulary(head):
        """Which functions and operators the OUTER select list uses.
        This is the part a wrapper rule cannot remove — it has to be
        TRANSLATED into an Insights expression — so what it is built from
        decides whether one capability covers a group or twenty do.
        """
        text = re.sub(r"`[^`]*`", "", head)
        text = re.sub(r"\(\s*\*\s*\)", "()", text)
        found = {name.upper() for name in re.findall(r"\b([A-Za-z_]\w*)\s*\(", text)}
        found |= {op for op in "+-*/" if op in text}
        return found
    def bucket(count):
        return "0" if not count else "1-2" if count <= 2 else "3-6" if count <= 6 else "7+"
    def case_shape(sql):
        """What a CASE-bearing report is built from — features, not a verdict.
        A CASE that scores a survey answer and a CASE that labels a status are
        one refusal message and two different problems. Three things tell them
        apart without reading the SQL: how many branches it has, whether it
        matches against LONG string literals (hardcoded question wording), and
        whether it counts answered-versus-unanswered with COALESCE/NULLIF/IS
        NULL, which is what a composite index does and a categorical label
        does not.
        """
        whens = len(re.findall(r"\bWHEN\b", sql, re.IGNORECASE))
        literals = len([s for s in re.findall(r"'([^']*)'", sql) if len(s) > 40])
        null_logic = bool(re.search(r"\bCOALESCE\b|\bNULLIF\b|\bIS\s+NULL\b",
                                    sql, re.IGNORECASE))
        return (f"branches={bucket(whens):<4} long-literals={bucket(literals):<4} "
                f"null-logic={'yes' if null_logic else 'no'}")
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
    # Where the .sql files are. Resolved in ONE place and PRINTED, because
    # getting it wrong silently reads a different folder and reports a real
    # number for it. Three sources, most deliberate first.
    chosen_from = ""
    if directory:
        chosen_from = "the `directory` variable inside this function"
    elif os.environ.get("DASHBOARD_STUDIO_SQL_DIR"):
        directory = os.environ["DASHBOARD_STUDIO_SQL_DIR"]
        chosen_from = "$DASHBOARD_STUDIO_SQL_DIR"
    elif os.path.basename(sys.argv[0] or "") == script_name and len(sys.argv) > 1:
        directory = sys.argv[1]
        chosen_from = "the command line"
    # argv is read ONLY when this file was run AS a script. Under `bench
    # console` sys.argv belongs to bench — `bench --site grc console` — and
    # scanning it for anything that happens to be a directory found the site
    # folder `grc` and confidently reported on the two files in it.
    if not directory:
        print("I do not know which directory to read. Either:")
        print(f"   python scripts/{script_name} path/to/exported_sql/")
        print("or, under `bench console`, set the environment variable first:")
        print("   import os")
        print("   os.environ['DASHBOARD_STUDIO_SQL_DIR'] = '/full/path/to/exported_sql'")
        print(f"   exec(open('apps/dashboard_studio/scripts/{script_name}').read())")
        print("Setting a `directory` variable before exec() does NOT work: this")
        print("function declares its own, which would shadow it.")
        return
    folder = pathlib.Path(directory).expanduser()
    if not folder.is_dir():
        print(f"Not a directory: {folder}   (from {chosen_from})")
        return
    files = sorted(folder.rglob("*.sql"))
    groups, failed = {}, []
    vocab, arithmetic_only = {}, []
    case_shapes = {}
    for path in files:
        try:
            text = path.read_text()
            reasons = parser.analyze_sql(text)["reasons"]
        except Exception as error:  # noqa: BLE001
            failed.append(f"{path.name}: {type(error).__name__}: {error}")
            continue
        # CASE is counted across EVERY refusing report, not only the ones that
        # also refuse on a subquery: a flat query with a CASE in it is the same
        # question about the same group.
        if any("CASE" in reason for reason in reasons):
            case_shapes.setdefault(case_shape(text), []).append(path.name)
        if not any("subquery / nested SELECT" in reason for reason in reasons):
            continue
        try:
            residue = rewritten(text)
            signature = describe(residue)
            head = re.split(r"\bFROM\b", residue, maxsplit=1, flags=re.IGNORECASE)[0]
            words = vocabulary(head)
        except Exception as error:  # noqa: BLE001
            signature, words = (f"could not be described: "
                                f"{type(error).__name__}: {error}"), set()
        groups.setdefault(signature, []).append((len(text), path))
        for word in words:
            vocab[word] = vocab.get(word, 0) + 1
        if words and words <= basic:
            arithmetic_only.append(path.name)
    total = sum(len(rows) for rows in groups.values())
    print("=" * 78)
    print(f"{total} of {len(files)} reports refuse on a subquery, in "
          f"{len(groups)} distinct shapes")
    print(f"reading {folder.resolve()}   (from {chosen_from})")
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
    if case_shapes:
        print("=" * 78)
        print(f"What the CASE reports are built from ({sum(len(v) for v in case_shapes.values())} reports)")
        print("=" * 78)
        print("   A CASE that scores a survey answer and a CASE that labels a status")
        print("   share one refusal message and are two different problems. Long string")
        print("   literals mean hardcoded text matching; null-logic (COALESCE / NULLIF /")
        print("   IS NULL) means the query counts answered against unanswered, which is")
        print("   what a composite index does and a plain categorical label does not.")
        print()
        for shape in sorted(case_shapes, key=lambda key: -len(case_shapes[key])):
            names = sorted(case_shapes[shape])
            print(f"   {len(names):>5}  {shape}")
            print(f"          e.g. {', '.join(names[:examples_per_group])}")
        print()
    if vocab:
        print("=" * 78)
        print("What the OUTER SELECT is built from — the part no wrapper rule can")
        print("remove, because it has to be TRANSLATED rather than dropped")
        print("=" * 78)
        for word in sorted(vocab, key=lambda key: -vocab[key]):
            print(f"   {vocab[word]:>5}  {word}")
        print()
        print(f"   {len(arithmetic_only)} of {total} use nothing but arithmetic over")
        print("   aggregates (AVG/SUM/COUNT/MIN/MAX, + - * /, CAST). If that number")
        print("   is most of them, ONE expression capability is what they are")
        print("   waiting on. If it is not, the rest of this list is what else")
        print("   would have to be understood — count them before promising any.")
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
