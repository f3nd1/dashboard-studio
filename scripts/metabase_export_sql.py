"""Export every Metabase card's SQL to a folder, ready for bulk_dry_run.py.

Paste into ``bench --site <site> console``, or pipe it in, or exec it from an
open file — all three work (see the note at the bottom about why).

    exec(open('scripts/metabase_export_sql.py').read())
    python scripts/bulk_dry_run.py metabase_sql/

**Nothing is written to Metabase and no query is executed anywhere.** It reads
cards (GET) and, for GUI-built cards, asks Metabase to COMPILE the question to
SQL without running it (POST /api/dataset/native). The Metabase URL and key come
from site_config, so the key is never pasted into a shell and is never printed —
not even on the error paths, where "helpful" context is how a key reaches a
browser.

**Why a POST at all, when everything else here is GET-only.** A GUI-built card
holds MBQL, not SQL; there is no GET that returns its compiled form. ADR-006
named this exact endpoint as the sanctioned route — *"a human copying it from
the View-SQL panel today, or `POST /api/dataset/native` if that permission is
ever granted"* — because taking Metabase's own compiled SQL keeps Metabase the
authority on what a question computes. It compiles and returns text; it does not
execute. Its dangerous neighbours are one word away, so:

  - the ONLY path this file ever POSTs to is `native_path` below, checked at
    the call and asserted by its test;
  - `POST /api/dataset` and `POST /api/card/:id/query` EXECUTE against the
    production database and must never appear here. The test greps for them.
  - set `compile_gui_cards = False` for a GET-only run. GUI cards are then
    skipped by name and counted, and nothing POSTs at all.

If the key's group does not permit compilation, Metabase answers 403 and those
cards are skipped with a note rather than the run failing. The durable control
on the Metabase side is still a SELECT-only database login, not this file.

**The output is one .sql file per card**, named `<card name>--<id>.sql` so a
refusal in the dry run leads straight back to the card. Existing files are
overwritten.
"""

def _export():
    # noqa on the block: isort wants a blank line before the first-party
    # import, and a blank line here breaks the piped-paste form.
    import frappe  # noqa: I001
    import json
    import pathlib
    import re
    import requests
    # INSIDE the function on purpose — `bench console` is an embedded IPython
    # where globals() and locals() are different dicts, so a module-level name
    # is unreachable from here. Edit these, not copies above.
    out_dir = "metabase_sql"
    # False = GET-only: GUI cards are skipped by name and nothing is POSTed.
    compile_gui_cards = True
    # Stop after this many cards. Set it low for a first run to see what the
    # calls actually return before doing 200 of them; 0 means all.
    card_limit = 0
    # The ONE path this file may POST to. It compiles MBQL to SQL and returns
    # the text; it does not execute. Anything else — /api/dataset,
    # /api/card/<id>/query — runs the query against production.
    native_path = "/api/dataset/native"
    base = (frappe.conf.get("metabase_url") or "").strip().rstrip("/")
    key = (frappe.conf.get("metabase_api_key") or "").strip()
    if not base or not key:
        print("metabase_url / metabase_api_key missing from site_config.json.")
        return
    headers = {"X-API-Key": key, "Accept": "application/json"}
    def get(path):
        response = requests.get(base + path, headers=headers, timeout=60)
        if response.status_code != 200:
            # Never echo the key or the headers; the path is enough to act on.
            raise RuntimeError(f"GET {path} -> {response.status_code}")
        return response.json()
    def compile_to_sql(dataset_query):
        """MBQL -> SQL text. Compiles; does not execute."""
        # Checked here rather than trusted from the variable: an edit that
        # points `native_path` at an executing endpoint has to delete this line
        # too, and deleting a line that says what it protects is a decision
        # rather than an accident.
        if native_path != "/api/dataset/native":
            raise RuntimeError("refusing to POST anywhere but the compile endpoint")
        response = requests.post(base + native_path, headers=headers,
                                 json=dataset_query, timeout=60)
        if response.status_code == 403:
            raise PermissionError("403")
        if response.status_code != 200:
            raise RuntimeError(f"POST {native_path} -> {response.status_code}")
        body = response.json()
        # The key has moved between versions; both spellings are read rather
        # than one guessed, because a miss here looks like an empty card.
        return body.get("query") or (body.get("native") or {}).get("query")
    def filename(card):
        name = card.get("name") or f"card {card.get('id')}"
        slug = re.sub(r"[^\w\- ]+", "-", name).strip().strip("-").strip()
        slug = re.sub(r"\s+", " ", slug)[:80].strip() or "card"
        return f"{slug}--{card.get('id')}.sql"
    def sidecar(card):
        """What the chart needs, written beside the SQL in the SAME run.
        Three keys, each read straight off the card: the per-series display
        type and label somebody set (`series_settings`), the card-level
        `display` those series inherit from, and the card id for traceability.
        Written in the same pass as the .sql so the pair is GUARANTEED to
        correspond — matching a pasted query back to a card later would mean
        comparing SQL text, and this export is full of near-identical variants
        of one report, so a wrong match would apply another report's chart
        settings in silence. No row data: `visualization_settings` describes
        the chart rather than its contents, and only these two keys are copied
        out of it rather than the block wholesale."""
        settings = card.get("visualization_settings")
        settings = settings if isinstance(settings, dict) else {}
        series = settings.get("series_settings")
        return {
            "card_id": card.get("id"),
            "display": card.get("display"),
            "series_settings": series if isinstance(series, dict) else {},
        }
    folder = pathlib.Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    print("=" * 78)
    print(f"Exporting Metabase SQL to {folder.resolve()}")
    print("=" * 78)
    cards = get("/api/card")
    if card_limit:
        cards = cards[:card_limit]
        print(f"card_limit is {card_limit} — this is a trial run, not the whole set.")
    print(f"{len(cards)} cards to look at.")
    written, archived, refused_permission, failed = [], [], [], []
    templated, not_compiled = [], []
    for index, summary in enumerate(cards, start=1):
        card_id = summary.get("id")
        if summary.get("archived"):
            archived.append(card_id)
            continue
        try:
            card = get(f"/api/card/{card_id}")
        except Exception as error:  # noqa: BLE001
            failed.append(f"card {card_id}: could not fetch ({error})")
            continue
        query = card.get("dataset_query") or {}
        sql = None
        if (query.get("type") or card.get("query_type")) == "native":
            sql = (query.get("native") or {}).get("query")
            if not sql:
                failed.append(f"card {card_id}: native card with no SQL in it")
                continue
        elif not compile_gui_cards:
            not_compiled.append(f"card {card_id} ({card.get('name')})")
            continue
        else:
            try:
                sql = compile_to_sql(query)
            except PermissionError:
                refused_permission.append(f"card {card_id} ({card.get('name')})")
                continue
            except Exception as error:  # noqa: BLE001
                failed.append(f"card {card_id}: could not compile ({error})")
                continue
            if not sql:
                failed.append(f"card {card_id}: compiled to nothing")
                continue
        path = folder / filename(card)
        path.write_text(sql)
        written.append(path.name)
        # The sidecar carries the chart settings; `bulk_dry_run.py` reads
        # `*.sql` and never sees it.
        path.with_suffix(".json").write_text(json.dumps(sidecar(card), indent=2))
        # `{{param}}` and `[[optional]]` are Metabase's template syntax, not
        # SQL. Counted here so the dry run's refusals for them are expected
        # rather than a mystery.
        if "{{" in sql or "[[" in sql:
            templated.append(path.name)
        if index % 25 == 0:
            print(f"  ...{index}/{len(cards)}")
    print()
    print("=" * 78)
    print(f"{len(written)} .sql files written to {folder.resolve()}")
    print("=" * 78)
    print(f"   {len(archived)} archived, skipped")
    print(f"   {len(not_compiled)} GUI-built, and compile_gui_cards is off")
    print(f"   {len(refused_permission)} refused by Metabase permissions")
    print(f"   {len(failed)} failed")
    if templated:
        print(f"   {len(templated)} contain Metabase template tags ({{{{param}}}}),")
        print("   which are not SQL — expect those to refuse in the dry run")
    if not_compiled:
        print()
        print("NOT COMPILED: these are GUI-built cards, and compile_gui_cards is")
        print("off, so nothing was POSTed. They hold MBQL rather than SQL, so")
        print("there is nothing to export without asking Metabase to compile")
        print("them — turn the switch on, or export these by hand.")
        for line in not_compiled[:20]:
            print("   " + line)
        if len(not_compiled) > 20:
            print(f"   ...and {len(not_compiled) - 20} more")
    if refused_permission:
        print()
        print("PERMISSION: Metabase answered 403 when asked to compile these to")
        print("SQL. The API key's group does not allow it. Either grant that")
        print("group query-builder access, or export those cards by hand from")
        print("the View-SQL panel. Nothing else in this run is affected.")
        for line in refused_permission[:10]:
            print("   " + line)
        if len(refused_permission) > 10:
            print(f"   ...and {len(refused_permission) - 10} more")
    if failed:
        print()
        print(f"FAILED ({len(failed)}) — read these, they are not the same as a refusal")
        for line in failed[:20]:
            print("   " + line)
        if len(failed) > 20:
            print(f"   ...and {len(failed) - 20} more")
    print()
    print("Next:")
    print(f"   python scripts/bulk_dry_run.py {folder}")
    print("Nothing was written to Metabase. No query was executed.")
    return written, failed


_export()
