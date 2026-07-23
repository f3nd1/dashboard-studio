from __future__ import annotations

from typing import Any

ALLOWED_AGGREGATIONS = {"count", "sum", "average", "minimum", "maximum", "percentage"}
ALLOWED_OPERATORS = {"=", "!=", ">", ">=", "<", "<=", "in", "not in", "is set", "is not set"}


class DefinitionValidationError(ValueError):
    """Raised when a dashboard definition is unsafe or incomplete."""


def _as_string_set(value: Any, label: str) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, (list, tuple, set)):
        raise DefinitionValidationError(f"{label} must be a list of field names")
    result = {str(item).strip() for item in value if str(item).strip()}
    return result


def validate_metric_config(config: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise DefinitionValidationError("Metric configuration must be an object")
    if not isinstance(dataset, dict):
        raise DefinitionValidationError("Dataset definition must be an object")

    source_doctype = str(dataset.get("source_doctype") or "").strip()
    if not source_doctype:
        raise DefinitionValidationError("Dataset source_doctype is required")

    allowed_fields = _as_string_set(dataset.get("allowed_fields"), "allowed_fields")
    restricted_fields = _as_string_set(dataset.get("restricted_fields"), "restricted_fields")

    aggregation = str(config.get("aggregation") or "").strip().lower()
    if aggregation not in ALLOWED_AGGREGATIONS:
        raise DefinitionValidationError(f"Unsupported aggregation: {aggregation or '<blank>'}")

    dimension = str(config.get("dimension") or "").strip()
    measure = str(config.get("measure") or "").strip()

    referenced_fields = {field for field in (dimension, measure) if field}
    for condition in config.get("conditions") or []:
        if not isinstance(condition, dict):
            raise DefinitionValidationError("Each condition must be an object")
        field = str(condition.get("field") or "").strip()
        operator = str(condition.get("operator") or "").strip().lower()
        if not field:
            raise DefinitionValidationError("Condition field is required")
        if operator not in ALLOWED_OPERATORS:
            raise DefinitionValidationError(f"Unsupported operator: {operator or '<blank>'}")
        referenced_fields.add(field)

    forbidden = referenced_fields & restricted_fields
    if forbidden:
        raise DefinitionValidationError(f"Restricted fields requested: {', '.join(sorted(forbidden))}")

    if allowed_fields:
        unknown = referenced_fields - allowed_fields
        if unknown:
            raise DefinitionValidationError(f"Fields are not allowlisted: {', '.join(sorted(unknown))}")

    if aggregation != "count" and not measure:
        raise DefinitionValidationError(f"Measure is required for {aggregation}")

    return {
        "source_doctype": source_doctype,
        "dimension": dimension or None,
        "measure": measure or "name",
        "aggregation": aggregation,
        "conditions": list(config.get("conditions") or []),
    }
