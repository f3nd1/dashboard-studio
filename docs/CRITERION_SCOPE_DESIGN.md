# Criterion / subcriterion scope — design

**Status:** approved and built. See `dashboard_studio/edutrust.py` for the list,
`DS Dashboard.subcriterion` for the field, and `api/governance.advance_status`
for the publish gate. One correction was applied to §4 after review — see the
box there.
**Question:** how does a DS Dashboard record say which EduTrust criterion and
subcriterion it belongs to, and what does that imply for the publish contract?

Evidence below is from `f3nd1/intelligence-dashboard` @ `49361a8` (the Sophia
runtime) and this repo. Reference mockup:
`prototypes/dashboard_studio_hybrid_ai_prototype_v2.html` (canonical name).

---

## 1. Where the authoritative list actually lives

It lives in **three places on the Sophia side, none of which is a single source
of truth**, plus a fourth that is already stale.

| Location | What it holds | Role |
|---|---|---|
| `custom-html-block/JAVASCRIPT.js` → `CONFIG[criterion].subcriteria` | `[code, label]` pairs | drives the tab bar |
| `custom-html-block/JAVASCRIPT.js` → `CONFIG[criterion].apiSections` | `tab -> subcriterion` map | decides what the client asks the server for |
| `server-scripts/UCC Analytics - Criterion N.py` → `POLICY_REGISTRY` | `code -> {title, policy, version}` | **closest to authoritative** — the server serves it, and it carries the controlling policy document |
| `VERSION.json` → `policy_registries` | policy document codes only | **already stale**: omits `criterion_4` and `criterion_5` entirely |

### The 32 subcriteria, and one divergence

Extracted from both sides and compared:

| Criterion | Sophia frontend (`subcriteria`) | Sophia server (`POLICY_REGISTRY`) | Agree? |
|---|---|---|---|
| 1 | 1.1.1, 1.2.1 | 1.1.1, 1.2.1 | ✅ |
| 2 | 2.1.1, 2.1.2, 2.2.1, 2.3.1, 2.3.2, 2.4.1, 2.4.2, 2.4.3 | same 8 | ✅ |
| 3 | 3.1.1, 3.2.1 | same | ✅ |
| 4 | 4.1.1, 4.2.1, 4.2.2, 4.3.1, 4.4.1, 4.5.1, 4.6.1 | same 7 | ✅ |
| 5 | 5.1.1, 5.1.2, 5.2.1, 5.2.2, 5.3.1, **5.4**, **5.5** | 5.1.1, 5.1.2, 5.2.1, 5.2.2, 5.3.1, **5.4.1**, **5.5.1** | ❌ |
| 6 | 6.1.1, 6.2.1, 6.3.1, 6.4.1, 6.5.3 | same 5 | ✅ |
| 7 | 7.1.1 | 7.1.1 | ✅ |

**32 subcriteria total. Exactly one divergence**, in Criterion 5, and it is
already known and shimmed: `SUBCRITERION_ALIASES = {"5.4": "5.4.1", "5.5":
"5.5.1"}` (`Criterion 5.py:61`). The server canonicalises on the way in and
`standardise_response_contract` writes the canonical code back into
`meta.subcriterion`.

Note also that the numbering is **irregular** — Criterion 6 jumps 6.4.1 → 6.5.3
with no 6.5.1/6.5.2; Criterion 2 has a 2.4.x run of three. The set cannot be
generated algorithmically; it can only be enumerated.

### Is it stable enough to hardcode?

Two opposing pieces of evidence:

- **For:** the codes come from the EduTrust standard, which is external,
  versioned and changes rarely and with notice. They are not app-internal
  identifiers that get refactored.
- **Against:** three copies already exist on the Sophia side and have already
  produced one divergence needing a shim, and `VERSION.json`'s copy is stale.
  Every additional copy is another thing that drifts.

**Reading it at runtime is not currently possible.** Dashboard Studio installs
into a different Frappe app; there is no import path to Sophia's Server Scripts,
and Sophia's own list is embedded in a Custom HTML Block field, not exposed as an
API. Nothing serves the list.

---

## 2. Do validated pairs matter?

**Yes, and the failure is silent — which makes it the strongest argument in this
document.**

Trace what happens if a dashboard is scoped to criterion 5 + subcriterion 4.1.1
and published:

1. Sophia's `apiSection()` (`JAVASCRIPT.js:2232`) looks up `4.1.1` in
   `CONFIG.criterion_5.apiSections`. It is not there.
2. The lookup misses, and the function returns
   `state.lastSection || config.defaultSection` — i.e. **`5.1.1`**.
3. The dashboard renders Criterion 5.1.1's data under a heading that says 4.1.1.

No error, no warning, no empty state. A mismatched pair produces a **confidently
wrong dashboard**, which is precisely the failure mode this project's
flag-don't-guess rule exists to prevent.

Two independent free-text fields make this mismatch expressible. That is the
decisive reason not to use two free-text fields.

---

## 3. Does the publish contract need metadata beyond the code?

**For the contract: no.** Sophia already owns `title`, `policy` and `version`
per subcriterion in its own `POLICY_REGISTRY`, and its UI reads them from there.
A published dashboard needs to carry the **code only**; Sophia looks up the rest.
Sending title/policy/version would create a second copy of data Sophia owns —
exactly the drift the "no DS Criterion DocType" instinct is trying to avoid.

**For Dashboard Studio's own UI: yes, one field's worth.** The mockup's hero
reads `Criterion 4 · 4.1.1` and the left panel offers
`4.1.1 · Pre-Course Counselling, Selection and Admissions`. Rendering that needs
the human title locally.

This is the only metadata requirement, it is display-only, and — as shown below
— it does not justify a DocType because it can ride along inside the stored
value itself.

---

## 4. Recommendation

**One `Select` field on DS Dashboard, not two fields, and not a DS Criterion
DocType.**

```
DS Dashboard.subcriterion   Select
  (blank)      <- scope is optional while authoring
  1.1.1
  1.2.1
  ... (32 options, canonical codes, NO labels)
```

> **Correction applied after review.** An earlier draft of this section proposed
> option strings like `4.1.1 · Pre-Course Counselling…` and claimed they carried
> the display title "at no extra storage and with no second copy of policy
> metadata". **That was wrong about Frappe.** A `Select` has no key/label split —
> unlike a `Link`, the chosen option string is written to the column verbatim. A
> labelled option would put a copy of Sophia's title in every DS Dashboard
> record, and a retitle upstream would strand every existing record against an
> option that no longer matches — precisely the drift this document argues
> against two paragraphs earlier.
>
> **Options are bare codes. Titles are resolved at display time** from
> `edutrust.SUBCRITERIA` and returned by `get_studio_dashboard` and
> `list_subcriteria`. The records hold only the code.

The criterion is **derived from the code prefix** (`4.1.1` → `criterion_4`), not
stored. It is deterministic, so a second field would only create the opportunity
for the two to disagree.

### Why this beats two plain fields (your leaning)

Your reasoning for avoiding a DocType is right and I am not challenging it. But
two fields specifically re-introduce the §2 failure: they let someone pair
criterion 5 with 4.1.1, and Sophia will silently render the wrong section. One
field makes an invalid pair **unrepresentable** rather than merely discouraged —
the pair *is* the value, because the criterion is the code's own prefix.

### Why this beats a DS Criterion DocType

A DocType would be justified only if per-subcriterion metadata had to be stored
and edited here. §3 shows it does not: Sophia owns `title`/`policy`/`version`,
and the only local need is a display label, which the Select option string
already contains. A DocType would be a second source of truth for something
Sophia owns, would need seeding and maintaining, and would drift. Agreed —
do not build it.

### The honest cost

Select options are **a fourth hardcoded copy** of the list, and §1 shows copies
drift. There is no way to avoid this today, because nothing serves the list. The
mitigation is not to prevent drift but to **catch it at the boundary that
matters**:

> Enforce truth at publish time, not at authoring time.

The publish step has to reach Sophia anyway. That is where the stored code should
be checked against Sophia's real keys, and where a mismatch must **refuse to
publish with a named reason** rather than emitting a contract Sophia will
silently mis-route. Authoring-time Select options are a usability affordance;
publish-time validation is the control.

### Details to settle when this is built

1. **Store the canonical code.** Use `5.4.1`/`5.5.1`, not the frontend's
   `5.4`/`5.5`. Sophia's server canonicalises anyway, and its alias map is the
   compatibility shim for its own frontend, not a second valid spelling.
2. **Exclude `overview`.** `POLICY_REGISTRY` defines it for C1/C3/C4/C5, but the
   frontend's `apiSections` rewrites `overview` to the first subcriterion for
   every criterion, so nothing ever requests it. A dashboard scoped to
   `overview` would publish to a section Sophia does not route to.
3. **Optional, not required.** A dashboard should be authorable before its scope
   is decided. Making it mandatory blocks `create_dashboard`, which currently
   takes a title only.
4. **Where it surfaces:** the mockup's `.hero-kicker`. Dashboard Studio already
   renders `DS Dashboard.description` in that position (Tier 1-E), so the kicker
   sits directly above it with no new layout.

---

## 5. What this unblocks

Publish-to-Sophia stays blocked behind this decision, correctly. Once the scope
field exists, the remaining unknowns for the contract are: what Sophia consumes
(its `CONFIG` + `LIVE_VISUAL_EXPANSION` shape), how DS Chart rows map to
`LIVE_VISUAL_EXPANSION` entries, and whether publishing writes a Server Script or
only data. None of those are decided here.
