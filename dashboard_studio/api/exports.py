"""List and read the Metabase export `metabase_export_sql.py` wrote — READ ONLY.

The exported `.sql`/`.json` pairs live on the SERVER, in the bench's sites
directory. The first version of this feature used a browser `<input type=file>`,
which cannot reach them: a file input opens the *client's* filesystem, so a click
opened the user's own Mac Downloads folder. That is a browser security boundary,
not a path to configure — it could never have worked, for anyone. The list has
to come from the server, which is what this module is.

**Nothing here writes, and nothing here joins a path from user input.** Both
matter, and the second is the one that would hurt: `site_config.json` lives one
directory above this folder and holds `metabase_api_key`, so a traversal bug
here is a credential disclosure. The protection is structural rather than
careful — a requested report name is only ever COMPARED against the names found
by listing the folder, never concatenated onto it, so there is no string a
caller can send that becomes a different path. `../../x` matches no entry and
reads nothing. Keep that shape; do not "simplify" it into a `folder / name`.
"""

import pathlib

import frappe

from dashboard_studio.roles import DS_WRITE_ROLES

# Where `metabase_export_sql.py` puts its output: `out_dir = "metabase_sql"`,
# relative to the directory `bench console` runs in, which is the bench's
# `sites/`. Set `dashboard_studio_sql_dir` in site_config.json to point
# somewhere else; the resolved path is returned on every call, because a
# silently wrong folder reports a real number for the wrong set of files —
# the same fault `bulk_dry_run.py` shipped twice.
_CONF_KEY = "dashboard_studio_sql_dir"
_DEFAULT_FOLDER = "metabase_sql"

# A .sql export is a few KB. Anything past this is not a report and is not
# going to be sent to a browser.
_MAX_BYTES = 2 * 1024 * 1024

# How many matches to return. The real export is ~1775 files; a list that long
# is not a list, and the search box is the way through it.
_MAX_RESULTS = 50


def _folder():
    """``(path, problem)`` — where the exports are, or why they cannot be read."""
    configured = (frappe.conf.get(_CONF_KEY) or "").strip()
    if configured:
        folder = pathlib.Path(configured).expanduser()
    else:
        try:
            # `frappe.get_site_path()` is the site directory; its parent is the
            # bench's `sites/`, which is where the exporter's relative default
            # lands. Guarded because a failure here must read as "not
            # configured" rather than a traceback in a search box.
            site = pathlib.Path(frappe.get_site_path()).resolve()
            folder = site.parent / _DEFAULT_FOLDER
        except Exception:
            return None, (
                f"No export folder is configured. Add \"{_CONF_KEY}\": "
                "\"/full/path/to/metabase_sql\" to site_config.json.")
    if not folder.is_dir():
        return None, (
            f"No export folder at {folder}. Run scripts/metabase_export_sql.py "
            f"to create it, or set \"{_CONF_KEY}\" in site_config.json to where "
            "the exports already are.")
    return folder, None


def _entries(folder):
    """Every exported report in the folder, newest name order, with its sidecar.

    Keyed by the file STEM — `Quality Index--2424` — because that is what pairs
    a `.sql` with its `.json`, and it is the only thing a caller may name.
    """
    found = {}
    for path in sorted(folder.glob("*.sql")):
        if not path.is_file() or not _inside(path, folder):
            continue
        sidecar = path.with_suffix(".json")
        found[path.stem] = sidecar.is_file() and _inside(sidecar, folder)
    return found


def _inside(path, folder):
    """Is this entry's REAL target still in the export folder?

    Comparing names already means a caller cannot name anything outside. This
    closes the other half: a `.sql` SYMLINK inside the folder pointing at
    `../<site>/site_config.json` would be listed by `glob` and read like any
    other export, which would hand `metabase_api_key` to a browser. Only
    somebody who can already write into the export folder could plant one — but
    "you would need write access first" is the argument every traversal bug
    makes, and the check is three lines.
    """
    try:
        return path.resolve().parent == folder.resolve()
    except OSError:
        return False


def _report_name(stem):
    """`Quality Index--2424` -> `Quality Index`. The `--NNNN` is the card id."""
    name, _, tail = stem.rpartition("--")
    return name if name and tail.isdigit() else stem


@frappe.whitelist()
def list_exported_reports(search: str = None):
    """Exported reports whose name contains `search` — names only, no contents.

    Read-only, and it reads a directory listing rather than any file. The reply
    always carries `directory` so a wrong folder is visible on screen instead of
    looking like an empty export.
    """
    frappe.only_for(DS_WRITE_ROLES)
    folder, problem = _folder()
    if problem:
        return {"available": False, "problem": problem, "reports": [],
                "total": 0, "shown": 0}

    entries = _entries(folder)
    if not entries:
        return {"available": False, "directory": str(folder), "reports": [],
                "total": 0, "shown": 0,
                "problem": f"No .sql exports in {folder}. Run "
                           "scripts/metabase_export_sql.py to fill it."}

    wanted = str(search or "").strip().lower()
    matched = [(stem, has_sidecar) for stem, has_sidecar in entries.items()
               if wanted in _report_name(stem).lower() or wanted in stem.lower()]
    # Sidecar-carrying reports first: those are the ones that produce a chart,
    # which is the whole reason this list exists.
    matched.sort(key=lambda pair: (not pair[1], _report_name(pair[0]).lower()))
    return {
        "available": True,
        "directory": str(folder),
        "total": len(matched),
        "shown": min(len(matched), _MAX_RESULTS),
        "reports": [{"stem": stem, "report": _report_name(stem),
                     "has_sidecar": has_sidecar}
                    for stem, has_sidecar in matched[:_MAX_RESULTS]],
    }


@frappe.whitelist()
def read_exported_report(stem: str):
    """One report's SQL and its sidecar, or a refusal. Reads nothing else.

    `stem` is COMPARED against the folder's own listing and never joined to it.
    That is what makes an arbitrary string safe here — see the module docstring
    for why it matters that `site_config.json` is one directory up.
    """
    frappe.only_for(DS_WRITE_ROLES)
    folder, problem = _folder()
    if problem:
        frappe.throw(problem)

    wanted = str(stem or "").strip()
    if wanted not in _entries(folder):
        # Deliberately the same message whether the name was a typo or an
        # attempt to leave the folder: this reply must not report on what does
        # or does not exist elsewhere on the disk.
        frappe.throw(f"There is no exported report called '{wanted}' in {folder}.")

    # Found BY LISTING, so this path came from the filesystem, not the caller.
    sql_path = next(p for p in folder.glob("*.sql")
                    if p.stem == wanted and _inside(p, folder))
    if sql_path.stat().st_size > _MAX_BYTES:
        frappe.throw(f"'{wanted}' is larger than a report should be "
                     f"({sql_path.stat().st_size} bytes) and was not read.")

    card, card_problem = None, None
    # `_inside` again, not just in the listing: this glob is its own lookup, and
    # a symlinked sidecar is the same disclosure by a second door.
    sidecar = next((p for p in folder.glob("*.json")
                    if p.stem == wanted and _inside(p, folder)), None)
    if sidecar is not None and sidecar.stat().st_size <= _MAX_BYTES:
        try:
            card = frappe.parse_json(sidecar.read_text())
        except Exception:
            # Unreadable is not a chart to guess at — the SQL still converts.
            card, card_problem = None, (
                f"The chart settings beside '{wanted}' are not readable JSON, so "
                "the chart will be left at Insights' default.")
    if card is not None and not isinstance(card, dict):
        card, card_problem = None, (
            f"The chart settings beside '{wanted}' are not a settings object, so "
            "the chart will be left at Insights' default.")

    return {"stem": wanted, "report": _report_name(wanted),
            "sql": sql_path.read_text(), "card": card,
            "card_problem": card_problem,
            "sidecar": sidecar.name if sidecar is not None and card else None}
