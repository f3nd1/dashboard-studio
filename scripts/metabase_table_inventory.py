"""Which physical tables UCC's Metabase cards actually read.

Paste into ``bench --site <site> console``, or pipe it in, or exec it from an
open file — all three work (see the note at the bottom about why).

**Read-only, GET only.** Two list calls plus one GET per card. Nothing is
written to Metabase and nothing is executed anywhere. The Metabase URL and key
come from site_config, so the key is never pasted into a shell.

It exists to answer one question: if the Metabase database login is narrowed
from ``GRANT SELECT ON db.* `` to specific tables, which tables must be on the
list? The error direction is asymmetric and drives everything here —
**a surplus table costs one extra GRANT, a missing one silently breaks a
dashboard** — so anything that cannot be resolved is printed loudly rather than
quietly dropped, and the suggested GRANT block is withheld unless the
unresolved list is empty.

Read the UNRESOLVED section before using the output. Cards built on other cards
are counted on the other card's pass, which is correct but only obvious once
said out loud.

ponytail: no blank lines inside the function, and everything inside one
function with its imports. ``bench console`` runs an embedded IPython where
globals() and locals() are different dicts, so a bare exec(open(...).read())
would leave module-level names unreachable from the functions that need them —
that fault already cost one round trip on scripts/insights_v3_probe.py.
"""


def _inventory():
    # noqa on the block: isort wants a blank line before the first-party
    # import, and a blank line here breaks the piped-paste form.
    import frappe  # noqa: I001
    import requests
    from dashboard_studio.integrations.metabase.card import referenced_tables
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
    # ---- the id -> physical name map, one call ----------------------------
    tables = get("/api/table")
    table_names = {}
    for row in tables:
        if isinstance(row, dict) and row.get("id") is not None:
            table_names[row["id"]] = row.get("name") or f"<table {row['id']}>"
    print(f"Metabase knows {len(table_names)} tables.")
    # ---- every card --------------------------------------------------------
    cards = get("/api/card")
    print(f"Metabase has {len(cards)} cards. Fetching each one...")
    used = {}
    unresolved = []
    archived = 0
    native = 0
    failed = 0
    for index, summary in enumerate(cards, start=1):
        card_id = summary.get("id")
        if summary.get("archived"):
            archived += 1
            continue
        try:
            card = get(f"/api/card/{card_id}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            unresolved.append(f"card {card_id}: could not fetch ({exc})")
            continue
        if card.get("query_type") == "native":
            native += 1
        found, problems = referenced_tables(card, table_names)
        for name in found:
            used.setdefault(name, []).append(card_id)
        unresolved.extend(problems)
        if index % 200 == 0:
            print(f"  ...{index}/{len(cards)}")
    # ---- report ------------------------------------------------------------
    print("\n" + "=" * 78)
    print(f"{len(used)} tables referenced by {len(cards) - archived} live cards "
          f"({native} native SQL, {archived} archived skipped, {failed} unfetchable)")
    print("=" * 78)
    for name in sorted(used):
        ids = used[name]
        sample = ", ".join(str(i) for i in ids[:6]) + ("..." if len(ids) > 6 else "")
        print(f"  {name:44} {len(ids):4} cards   [{sample}]")
    print("\n" + "=" * 78)
    print(f"UNRESOLVED - {len(unresolved)} item(s). Read these before narrowing anything.")
    print("=" * 78)
    for line in unresolved[:80]:
        print("  " + line)
    if len(unresolved) > 80:
        print(f"  ...and {len(unresolved) - 80} more")
    # ---- the GRANT block, withheld unless everything resolved --------------
    print("\n" + "=" * 78)
    if unresolved:
        print("NO GRANT BLOCK PRINTED.")
        print("Something above could not be resolved, and a table missing from a")
        print("GRANT breaks a dashboard with a permission error rather than a")
        print("visible gap. Resolve those first, or keep the database-wide")
        print("GRANT SELECT, which is already a large improvement over a login")
        print("that can write.")
    else:
        print("Every card resolved. Suggested grants, to review before running:")
        print("=" * 78)
        db = "sms.unitedceres.edu.sg"
        print(f"  REVOKE SELECT ON `{db}`.* FROM 'metabase_ro'@'%';")
        for name in sorted(used):
            print(f"  GRANT SELECT ON `{db}`.`{name}` TO 'metabase_ro'@'%';")
        print("  FLUSH PRIVILEGES;")
        print("\n  Metabase also re-syncs schema periodically. If sync starts")
        print("  failing after this, put the database-wide SELECT back - a")
        print("  narrower grant is not worth a broken metadata sync.")
    print("\nNote: a card built on another card is counted on that other card's")
    print("pass, so it contributes no tables of its own. That is correct, not a")
    print("gap - the underlying tables are still in the list above.")
    return used, unresolved


_inventory()
