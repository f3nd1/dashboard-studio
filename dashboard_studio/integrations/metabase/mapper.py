from __future__ import annotations


def table_to_doctype(table_name: str) -> str:
    value = table_name.strip().strip("`")
    return value[3:] if value.lower().startswith("tab") else value
