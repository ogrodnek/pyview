"""Payload parsing utilities for form data.

Handles various payload formats from HTML forms:
- Flat: {"name": ["John"], "_target": ["name"]}
- Nested dot: {"address.city": ["NYC"], "_target": ["address", "city"]}
- Nested dict: {"user": {"name": ["John"]}}
"""

from typing import Any

from .paths import join_path


def parse_form_payload(payload: dict[str, Any]) -> tuple[str, Any]:
    """Extract target field path and value from form payload.

    Args:
        payload: Form payload dict from phx-change event

    Returns:
        Tuple of (field_path, value)

    Examples:
        # Flat payload
        >>> parse_form_payload({"name": ["John"], "_target": ["name"]})
        ("name", "John")

        # Nested via _target
        >>> parse_form_payload({"address.city": ["NYC"], "_target": ["address", "city"]})
        ("address.city", "NYC")

        # List index
        >>> parse_form_payload({"tags.0": ["python"], "_target": ["tags", "0"]})
        ("tags.0", "python")
    """
    target = payload.get("_target", [])

    if not target:
        # No target specified - return first non-underscore key
        for key, value in payload.items():
            if not key.startswith("_"):
                return key, _extract_value(value)
        return "", None

    # Build path from target segments
    path = join_path(*target)

    # Try to find value using various key formats
    value = _find_value_in_payload(payload, target, path)

    return path, value


def _find_value_in_payload(
    payload: dict[str, Any], target: list[str], path: str
) -> Any:
    """Find the value in payload using various key formats.

    HTML forms can send data in different formats depending on the
    form structure and framework conventions.
    """
    # Try dot-notation key first (most common for nested)
    if path in payload:
        return _extract_value(payload[path])

    # Try just the first segment (flat form)
    if target and target[0] in payload:
        return _extract_value(payload[target[0]])

    # Try nested dict traversal
    value = _traverse_nested(payload, target)
    if value is not None:
        return _extract_value(value)

    return None


def _traverse_nested(data: dict[str, Any], keys: list[str]) -> Any:
    """Traverse nested dict structure following keys."""
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list):
            try:
                idx = int(key)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            except (ValueError, TypeError):
                return None
        else:
            return None
    return current


def _extract_value(value: Any) -> Any:
    """Extract scalar value from form value.

    HTML forms send values as arrays, so ["John"] becomes "John".
    Handles edge cases like empty arrays and non-array values.
    """
    if isinstance(value, list):
        if len(value) == 0:
            return ""
        elif len(value) == 1:
            return value[0]
        else:
            # Multiple values (e.g., multi-select) - return as list
            return value
    return value


def flatten_payload(payload: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten a nested payload dict into dot-notation keys.

    Args:
        payload: Potentially nested dict
        prefix: Current path prefix

    Returns:
        Flat dict with dot-notation keys

    Examples:
        >>> flatten_payload({"user": {"name": "John", "address": {"city": "NYC"}}})
        {"user.name": "John", "user.address.city": "NYC"}
    """
    result: dict[str, Any] = {}

    for key, value in payload.items():
        if key.startswith("_"):
            # Preserve meta keys at top level
            result[key] = value
            continue

        full_key = f"{prefix}.{key}" if prefix else key

        if isinstance(value, dict):
            # Recurse into nested dict
            result.update(flatten_payload(value, full_key))
        else:
            result[full_key] = value

    return result
