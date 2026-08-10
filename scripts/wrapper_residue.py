"""Dump named reports RAW, plus the residue the three wrapper rules leave.

    python scripts/wrapper_residue.py path/to/exported_sql/ 2032 1795
    # or under bench console:
    import os
    os.environ['DASHBOARD_STUDIO_SQL_DIR'] = '/full/path/to/exported_sql'
    os.environ['DASHBOARD_STUDIO_CARDS'] = '2032,1795,2076,1820'
    exec(open('apps/dashboard_studio/scripts/wrapper_residue.py').read())

The capture tool for building a wrapper rule. Every wrapper rule in this
project was written against the real SQL, and one was explicitly NOT built
against a reconstruction — so when a shape group is chosen for work, this
prints, for each named card id:

  1. the file's RAW SQL, verbatim;
  2. the RESIDUE — the statement after `unwrap_derived_tables`,
     `drop_passthrough_wrapper` and `lift_renaming_wrapper` have each had
     their say — which is the thing a NEW rule would actually receive, and
     shows exactly where the existing rules declined;
  3. `analyze_sql`'s refusal reasons, so the residue can be read against the
     message it produces.

Cards are named by ID because the export names files `<report>--<id>.sql` and
the report half varies (`- retain`, `- Duplicate`); the id is stable. A card
id matching no file says so rather than printing nothing.

Frappe-free — the parser needs no site — so it runs anywhere the files are.
Read-only: it reads files and prints. Nothing is written, nothing executed.

ponytail: no blank lines inside the function, and everything inside one
function with its imports — bench console's split namespaces and IPython's
blank-line-ends-a-block rule have each cost a round trip already.
"""

def _residue():
    # noqa on the block: isort wants a blank line before the first-party
    # import, and a blank line here breaks the piped-paste form.
    import os  # noqa: I001
    import pathlib
    import sys
    directory = ""
    script_name = "wrapper_residue.py"
    try:
        from dashboard_studio.integrations.metabase import parser
    except ImportError:
        here = globals().get("__file__")
        root = str(pathlib.Path(here).resolve().parents[1]) if here else os.getcwd()
        sys.path.append(root)
        from dashboard_studio.integrations.metabase import parser
    cards = []
    chosen_from = ""
    if os.environ.get("DASHBOARD_STUDIO_SQL_DIR"):
        directory = os.environ["DASHBOARD_STUDIO_SQL_DIR"]
        chosen_from = "$DASHBOARD_STUDIO_SQL_DIR"
    elif os.path.basename(sys.argv[0] or "") == script_name and len(sys.argv) > 1:
        directory = sys.argv[1]
        chosen_from = "the command line"
    if os.environ.get("DASHBOARD_STUDIO_CARDS"):
        cards = [c.strip() for c in os.environ["DASHBOARD_STUDIO_CARDS"].split(",")
                 if c.strip()]
    elif os.path.basename(sys.argv[0] or "") == script_name and len(sys.argv) > 2:
        cards = [c.strip() for c in sys.argv[2:] if c.strip()]
    if not directory or not cards:
        print("Usage: which folder, and which card ids.")
        print(f"   python scripts/{script_name} path/to/exported_sql/ 2032 1795")
        print("or, under bench console, set both first:")
        print("   import os")
        print("   os.environ['DASHBOARD_STUDIO_SQL_DIR'] = '/full/path/to/exported_sql'")
        print("   os.environ['DASHBOARD_STUDIO_CARDS'] = '2032,1795,2076,1820'")
        print(f"   exec(open('apps/dashboard_studio/scripts/{script_name}').read())")
        return
    folder = pathlib.Path(directory).expanduser()
    if not folder.is_dir():
        print(f"Not a directory: {folder}   (from {chosen_from})")
        return
    print(f"Reading {folder.resolve()}   (from {chosen_from})")
    for card in cards:
        matches = sorted(folder.glob(f"*--{card}.sql"))
        print()
        print("#" * 78)
        if not matches:
            print(f"# card {card}: NO FILE matching *--{card}.sql")
            continue
        for path in matches:
            print(f"# card {card}: {path.name}")
            print("#" * 78)
            raw = path.read_text()
            print("--- RAW " + "-" * 70)
            print(raw.strip())
            statement = parser.lift_renaming_wrapper(
                parser.drop_passthrough_wrapper(
                    parser.unwrap_derived_tables(raw.strip().rstrip(";"))))[0]
            print("--- RESIDUE after unwrap/drop/lift " + "-" * 43)
            print(statement.strip())
            reasons = parser.analyze_sql(raw)["reasons"]
            print("--- REASONS " + "-" * 66)
            for reason in reasons or ["(none — this file converts at shape level)"]:
                print(f"   {reason}")
    print()
    print("Read-only. Nothing was written, nothing executed.")


_residue()
