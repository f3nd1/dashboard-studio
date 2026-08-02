"""A fake Frappe, good enough for the endpoints this app still has.

Lifted out of test_insights_handoff.py during the scope cut so it could outlive
it. It models the parts that have actually caught bugs: only_for raising, get_doc
in both its signatures, writes landing in the store rather than on the object,
and the varchar(140) limit that Frappe enforces by ABORTING an insert rather
than trimming — which is how a long title once reached a user.
"""

import types
import unittest  # noqa: F401  (imported by the modules that use this fake)


class _PermissionError(Exception):
    pass


class _ValidationError(Exception):
    pass


_PREFIX = {"Insights Query v3": "s39rc7j64", "Insights Chart v3": "tt51l7mma"}


class _FakeDoc:
    def __init__(self, data, store, doctype=None):
        object.__setattr__(self, "_data", dict(data))
        object.__setattr__(self, "_store", store)
        object.__setattr__(self, "_doctype", doctype or data.get("doctype"))

    def __getattr__(self, key):
        try:
            return self._data[key]
        except KeyError:
            raise AttributeError(key)

    # Assignment has to land in _data, not on the Python object: without this a
    # `doc.chart_type = "Bar"` would set an attribute the store never sees and
    # every write assertion would pass while writing nothing.
    def __setattr__(self, key, value):
        self._data[key] = value

    def get(self, key, default=None):
        return self._data.get(key, default)

    # Frappe refuses an over-long Data value and aborts the insert; it does not
    # trim. Modelled here so a code path that sends one fails in this suite
    # rather than on the live site, which is how the title crash reached a user.
    DATA_FIELD_LIMIT = 140
    DATA_FIELDS = ("title",)

    def _check_lengths(self):
        for fieldname in self.DATA_FIELDS:
            value = self._data.get(fieldname)
            if isinstance(value, str) and len(value) > self.DATA_FIELD_LIMIT:
                raise _ValidationError(
                    f"Value too big: {fieldname} is {len(value)} characters, "
                    f"max {self.DATA_FIELD_LIMIT}"
                )

    def insert(self):
        self._check_lengths()
        doctype = self._data["doctype"]
        table = self._store.setdefault(doctype, {})
        # Real v3 names, so nothing can quietly depend on the v2 "QRY-" prefix:
        # a Workbook is autoincrement (so "1", "2"), a query and a chart get a
        # random-looking hash ("s39rc7j648"). Named here, never by title, because
        # that is what forces the reuse key to be the SQL.
        # Skip past names already in the store. Counting rows collided with a
        # pre-seeded workbook and silently OVERWROTE it, which would have made a
        # broken create look like a working one.
        index = len(table) + 1
        while True:
            candidate = (str(index) if doctype == "Insights Workbook"
                         else f"{_PREFIX.get(doctype, 'x')}{index}k7a2d")
            if candidate not in table:
                break
            index += 1
        self._data["name"] = candidate
        table[self._data["name"]] = dict(self._data)
        return self

    def save(self):
        self._check_lengths()
        self._store.setdefault(self._doctype, {})[self._data["name"]] = dict(self._data)
        return self


def _make_fake_frappe(store, roles, doctypes=("Insights Query v3",), sources=("Site DB",)):
    frappe = types.ModuleType("frappe")
    frappe.PermissionError = _PermissionError
    frappe.ValidationError = _ValidationError
    frappe._roles = set(roles)
    frappe._doctypes = set(doctypes)
    frappe._sources = set(sources)           # Insights Data Source v3
    frappe._v2_sources = {"Site DB", "Query Store"}   # the v2 table, still there

    def only_for(needed, message=None):
        if isinstance(needed, str):
            needed = (needed,)
        if not (set(needed) & frappe._roles):
            raise _PermissionError(f"need one of {needed}")

    def whitelist(*a, **k):
        def deco(fn):
            return fn

        return deco

    def get_all(doctype, filters=None, fields=None, limit=None, **kwargs):
        rows = list(store.get(doctype, {}).values())
        for key, value in (filters or {}).items():
            rows = [r for r in rows if r.get(key) == value]
        return [dict(r) for r in rows][: limit or None]

    def exists(doctype, name):
        if doctype == "DocType":
            return name in frappe._doctypes
        # Both generations of the data-source table exist on a v3 site and both
        # hold a row called "Site DB". Modelled as two separate sets so a guard
        # reading the wrong one is a test failure rather than a coincidence.
        if doctype == "Insights Data Source v3":
            return name in frappe._sources
        if doctype == "Insights Data Source":
            return name in frappe._v2_sources
        return name in store.get(doctype, {})

    frappe.only_for = only_for
    frappe.whitelist = whitelist
    frappe.get_all = get_all
    class _DoesNotExistError(Exception):
        pass

    def get_doc(doctype, name=None):
        # Two signatures, like the real thing: a payload dict to insert, or
        # (doctype, name) to fetch. The fake modelled only the first, so the
        # first call that read a record back blew up rather than being wrong.
        if isinstance(doctype, dict):
            return _FakeDoc(doctype, store)
        data = store.get(doctype, {}).get(name)
        if data is None:
            raise _DoesNotExistError(f"{doctype} {name} not found")
        return _FakeDoc(data, store, doctype)

    frappe.DoesNotExistError = _DoesNotExistError
    frappe.get_doc = get_doc
    frappe.as_json = lambda value: __import__("json").dumps(value)
    frappe.get_roles = lambda: list(frappe._roles)
    frappe.parse_json = __import__("json").loads
    frappe.throw = lambda msg: (_ for _ in ()).throw(_ValidationError(msg))
    frappe.db = types.SimpleNamespace(exists=exists)
    return frappe
