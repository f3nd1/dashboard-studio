"""One read-only GET against Metabase. Nothing else, deliberately.

**This module can only read.** There is no method parameter, no generic
``request()`` helper, and no second function — a later caller cannot pass
``"POST"`` to something that only knows ``GET``. That is the point: Dashboard
Studio must never be the thing that changed a card in Metabase, and the cheapest
way to guarantee it is to not own the capability.

**The endpoint that must never be called from here.** ``POST /api/card/:id/query``
returns fresh columns and data, and it is exactly what someone will reach for the
first time ``result_metadata`` comes back empty. It executes SQL against UCC's
production database on Metabase's connection. It is not implemented here and must
not be added. "Studio files it, something else runs it" is the same boundary the
Insights handoff is built on, pointing the other way.

**Credentials.** ``site_config.json`` carries ``metabase_url`` and
``metabase_api_key``; both are per-site, outside this repo, and cannot be swept
into a fixture export. The key is an ordinary secret and is treated as one: never
returned to the browser (the SPA calls our endpoint, our endpoint calls Metabase),
never logged, and never echoed back in a refusal — including the 401 path, where
including the request for context would put the key straight into a user's
browser via ``_server_messages``.

**The key's group is a REQUIREMENT, not a description of what is deployed.**
Metabase scopes an API key to the group it was created in and has no read-only
key flag, so the only thing that can stop a write on the Metabase side is the
group. This module cannot check that and does not try.

Read that literally: if the configured key belongs to Administrators, or to any
group with `create-queries: query-builder-and-native`, then **nothing on the
Metabase side restricts it** and the GET-only shape below is the *only*
protection — not the second line, the sole one. It would also mean that key can
already run arbitrary SQL against the connected database through
``POST /api/dataset``, whether or not this app ever calls it.

Verify the group before trusting the sentence above. An earlier version of this
docstring asserted the view-only group as though it were a fact about the
deployment; it was always a requirement someone had to meet.

ponytail: config keys rather than a Settings DocType. A DocType with a Password
field would let an admin rotate the key without bench access; add it when
somebody needs to, not before.
"""

import frappe
import requests

CARD_PATH = "{base}/api/card/{card_id}"

# Long enough for a slow Metabase Cloud response, short enough that a hung
# request does not hold a Frappe worker open indefinitely.
TIMEOUT_SECONDS = 20


def _credentials():
    """``(base_url, api_key)``, or a refusal naming what is missing."""
    base = (frappe.conf.get("metabase_url") or "").strip().rstrip("/")
    key = (frappe.conf.get("metabase_api_key") or "").strip()
    if not base or not key:
        missing = " and ".join(
            name for name, value in (("metabase_url", base), ("metabase_api_key", key))
            if not value
        )
        frappe.throw(
            f"Metabase is not configured on this site: {missing} is missing from "
            "site_config.json. An administrator sets it with `bench set-config`; "
            "the key must belong to a Metabase group with view-only access."
        )
    return base, key


def fetch_card(card_id):
    """GET one card by id and return its decoded JSON.

    ``card_id`` is coerced to an int before it reaches the URL, so nothing a
    caller supplies can steer the request at a different endpoint.
    """
    try:
        card_id = int(card_id)
    except (TypeError, ValueError):
        frappe.throw("A Metabase card id is a number, like 2774.")
    if card_id <= 0:
        frappe.throw("A Metabase card id is a positive number, like 2774.")

    base, key = _credentials()
    try:
        response = requests.get(
            CARD_PATH.format(base=base, card_id=card_id),
            headers={"X-API-Key": key, "Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        # The exception text can carry the URL; the URL does not carry the key,
        # but neither is worth putting in front of a user. Say what failed.
        frappe.throw(
            "Could not reach Metabase. Check that this site can reach the "
            "Metabase host and that metabase_url is right."
        )

    if response.status_code in (401, 403):
        frappe.throw(
            "Metabase refused the API key — it is wrong, revoked, or its group "
            "cannot see this card. Nothing about the key is shown here on purpose."
        )
    if response.status_code == 404:
        frappe.throw(f"Metabase has no card {card_id}, or this key cannot see it.")
    if response.status_code != 200:
        frappe.throw(f"Metabase answered {response.status_code} for card {card_id}.")

    try:
        card = response.json()
    except ValueError:
        frappe.throw("Metabase did not answer with JSON. Check that metabase_url "
                     "points at Metabase itself and not at a proxy or login page.")
    if not isinstance(card, dict):
        frappe.throw(f"Metabase did not return a card for {card_id}.")
    return card
