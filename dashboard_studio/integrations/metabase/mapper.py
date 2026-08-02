from __future__ import annotations


def table_to_doctype(table_name: str) -> str:
    """```tabStudent Applicant``` -> "Student Applicant"; anything else, itself.

    Case-SENSITIVE on the prefix. Frappe creates its tables with a lowercase
    `tab`, so a name starting with `Tab` is something else — Metabase's
    humanized display name, or a DocType whose own name begins "Tab…", which
    a case-insensitive strip would quietly behead.
    """
    value = table_name.strip().strip("`")
    return value[3:] if value.startswith("tab") else value
