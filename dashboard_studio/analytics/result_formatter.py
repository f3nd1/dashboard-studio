from __future__ import annotations

from typing import Any


def format_series(rows: list[dict[str, Any]], dimension: str, value_field: str) -> dict[str, Any]:
    return {
        "labels": [row.get(dimension) for row in rows],
        "values": [row.get(value_field) for row in rows],
        "rows": rows,
    }
