"""How many DocType fields hold numbers in a text field?

Paste into ``bench --site <site> console``, or pipe it in, or exec it from an
open file — all three work (see the note at the bottom about why).

**Read-only.** It reads DocType metadata and samples stored values through
``frappe.get_all``. It writes nothing, changes no field type, and executes no
SQL of its own.

It exists because ONE field — `actual_value` on *Quality Performance Actual
Value Parameter Childtable* — is a Frappe **Data** field holding numbers, which
is why Metabase writes ``* 1`` before averaging it and why the converter has to
emit a `cast` (ADR-009). The real fix is retyping that field to Float or
Currency. Before touching schema anywhere, this reports how many OTHER fields
are in the same state, so the decision is made against the actual scope.

**Evidence, not naming.** A field is judged by the values it holds, not by
whether it is called `..._value` or `..._amount`. A name is reported as a hint
and never as a finding: `reference_no` full of digits is not a number, and
`actual_value` would be missed by any name list anyone would write.

**Mixed fields are the important ones.** A field whose values are 100% numeric
retypes cleanly. A field that is *mostly* numeric is where the money is: today
every non-numeric row silently coerces to 0 in the average, and retyping makes
those rows visible as bad data instead. That is a content decision, not a
schema one, and this tells you which fields have it.

The counts are over a SAMPLE (``LIMIT``, see `sample_size` inside), so read
"12 of 200 sampled are not numbers" as a proportion, not a total.

**Before sending the output back: the non-numeric examples are real values from
live tables.** They are truncated to 20 characters and only shown for fields
that are already mostly numeric — so in practice they read "N/A", "-", "TBC" —
but check them, and redact anything that turns out to be personal data.

ponytail: no blank lines inside the function, and everything inside one
function with its imports. ``bench console`` runs an embedded IPython where
globals() and locals() are different dicts, so a bare exec(open(...).read())
would leave module-level names unreachable from the functions that need them —
that fault has already cost a round trip twice in this project.
"""

def _scan():
    # noqa on the block: isort wants a blank line before the first-party
    # import, and a blank line here breaks the piped-paste form.
    import frappe  # noqa: I001
    # INSIDE the function on purpose — see the note above about bench console's
    # split namespaces. Edit these, not copies at module level.
    #
    # Apps whose DocTypes are somebody else's schema. Frappe's and ERPNext's
    # own text fields are not ours to retype, and they drown out the ones that
    # are. Empty this list to scan everything.
    skip_apps = ["frappe", "erpnext"]
    # Rows read per field. Larger is slower and no more conclusive: a field is
    # either holding numbers or it is not, and 200 rows shows that.
    sample_size = 200
    # Below this, a field is text that happens to contain some digits.
    numeric_share_floor = 0.8
    text_types = ("Data", "Small Text", "Text", "Long Text")
    def looks_numeric(value):
        # Thousands separators count: "1,234.5" is a number typed as text, and
        # that is exactly the shape this is looking for.
        try:
            float(str(value).replace(",", "").strip())
            return True
        except (TypeError, ValueError):
            return False
    print("=" * 78)
    print("Numeric-looking data stored in text fields — READ ONLY, nothing changed")
    print("=" * 78)
    skipped_modules = set()
    for module in frappe.get_all("Module Def", fields=["name", "app_name"]):
        if module.get("app_name") in skip_apps:
            skipped_modules.add(module["name"])
    # Child tables are IN scope on purpose: both live column faults were on one,
    # and `actual_value` is on one.
    doctypes = frappe.get_all("DocType", filters={"issingle": 0},
                              fields=["name", "module", "istable"])
    scanned = [d for d in doctypes if d.get("module") not in skipped_modules]
    print(f"{len(scanned)} DocTypes in scope "
          f"({len(doctypes) - len(scanned)} skipped as {', '.join(skip_apps)})")
    print(f"sampling up to {sample_size} rows per text field")
    print()
    findings = []
    unreadable = []
    for entry in scanned:
        doctype = entry["name"]
        try:
            meta = frappe.get_meta(doctype)
        except Exception as error:
            unreadable.append((doctype, f"{type(error).__name__}: {error}"))
            continue
        # `options` on a Data field is its format (Email, Phone, URL) — already
        # declared as something other than a bare string, so not this problem.
        candidates = [f for f in meta.fields
                      if f.fieldtype in text_types and not getattr(f, "options", None)]
        for field in candidates:
            try:
                rows = frappe.get_all(doctype,
                                      filters={field.fieldname: ["is", "set"]},
                                      fields=[field.fieldname], limit=sample_size)
            except Exception as error:
                unreadable.append((f"{doctype}.{field.fieldname}",
                                   f"{type(error).__name__}: {error}"))
                continue
            values = [r.get(field.fieldname) for r in rows]
            values = [v for v in values if v is not None and str(v).strip() != ""]
            if not values:
                continue
            numeric = [v for v in values if looks_numeric(v)]
            share = len(numeric) / len(values)
            if share < numeric_share_floor:
                continue
            others = [str(v).strip()[:20] for v in values if not looks_numeric(v)]
            findings.append({"doctype": doctype, "field": field.fieldname,
                             "fieldtype": field.fieldtype, "istable": entry.get("istable"),
                             "sampled": len(values), "numeric": len(numeric),
                             "share": share, "others": others[:3]})
    findings.sort(key=lambda f: (-f["share"], -f["sampled"]))
    clean = [f for f in findings if f["share"] == 1.0]
    mixed = [f for f in findings if f["share"] < 1.0]
    print("=" * 78)
    print(f"A. Every sampled value is a number ({len(clean)}) — these retype cleanly")
    print("=" * 78)
    for f in clean:
        child = " [child table]" if f["istable"] else ""
        print(f"   {f['doctype']}.{f['field']}{child}")
        print(f"      {f['fieldtype']}, {f['numeric']}/{f['sampled']} sampled are numbers")
    if not clean:
        print("   none")
    print()
    print("=" * 78)
    print(f"B. Mostly numbers, some not ({len(mixed)}) — READ THESE FIRST")
    print("=" * 78)
    print("   Every value here that is not a number is being coerced to 0 by")
    print("   MySQL today wherever it is aggregated. Retyping the field does not")
    print("   create that problem, it makes it visible.")
    for f in mixed:
        child = " [child table]" if f["istable"] else ""
        print(f"   {f['doctype']}.{f['field']}{child}")
        print(f"      {f['fieldtype']}, {f['numeric']}/{f['sampled']} sampled are numbers")
        print(f"      not numbers, e.g.: {', '.join(repr(o) for o in f['others'])}")
    if not mixed:
        print("   none")
    if unreadable:
        print()
        print("=" * 78)
        print(f"C. Could not be read ({len(unreadable)}) — not a finding either way")
        print("=" * 78)
        for name, error in unreadable:
            print(f"   {name}: {error}")
    print()
    print(f"TOTAL: {len(findings)} text fields hold numbers "
          f"({len(clean)} clean, {len(mixed)} mixed).")
    print("Nothing was written. No field type was changed.")
    print("The examples above are real values — redact anything personal before")
    print("sending this back.")


_scan()
