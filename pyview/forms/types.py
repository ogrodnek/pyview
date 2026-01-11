"""Type inference utilities for mapping Python types to HTML input types."""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Union, get_args, get_origin

from pydantic.fields import FieldInfo


# Map Python types to HTML input types
TYPE_TO_INPUT: dict[type, str] = {
    int: "number",
    float: "number",
    Decimal: "number",
    bool: "checkbox",
    date: "date",
    datetime: "datetime-local",
    time: "time",
}

# Field name patterns that suggest specific input types
NAME_PATTERNS: dict[str, str] = {
    "email": "email",
    "password": "password",
    "phone": "tel",
    "telephone": "tel",
    "url": "url",
    "website": "url",
    "search": "search",
    "color": "color",
}


def infer_input_type(
    field_name: str,
    annotation: Any | None = None,
    field_info: FieldInfo | None = None,
) -> str:
    """Infer HTML input type from field metadata.

    Priority:
    1. Explicit type in field_info.json_schema_extra["input_type"]
    2. Field name patterns (email, password, etc.)
    3. Python type annotation
    4. Default to "text"

    Args:
        field_name: Name of the field
        annotation: Python type annotation
        field_info: Pydantic FieldInfo if available

    Returns:
        HTML input type string

    Examples:
        >>> infer_input_type("email", str)
        "email"
        >>> infer_input_type("count", int)
        "number"
        >>> infer_input_type("is_active", bool)
        "checkbox"
    """
    # Check explicit type in field_info
    if field_info is not None:
        extra = field_info.json_schema_extra
        if isinstance(extra, dict) and "input_type" in extra:
            return str(extra["input_type"])

    # Check field name patterns
    name_lower = field_name.lower()
    for pattern, input_type in NAME_PATTERNS.items():
        if pattern in name_lower:
            return input_type

    # Check type annotation
    if annotation is not None:
        resolved_type = _unwrap_type(annotation)
        if resolved_type in TYPE_TO_INPUT:
            return TYPE_TO_INPUT[resolved_type]

    return "text"


def _unwrap_type(annotation: Any) -> Any:
    """Unwrap Optional, Union, etc. to get the inner type."""
    origin = get_origin(annotation)

    # Handle Optional[X] and Union[X, None]
    if origin is Union:
        args = get_args(annotation)
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _unwrap_type(non_none[0])
        return type(None)

    # Handle list[X] - return the list itself, not inner type
    # (lists are typically rendered as multiple inputs or special widgets)
    if origin is list:
        return list

    return annotation


def get_field_constraints(field_info: FieldInfo | None) -> dict[str, Any]:
    """Extract HTML input constraints from Pydantic FieldInfo.

    Extracts constraints like min, max, minlength, maxlength, pattern
    that can be applied to HTML inputs.

    Args:
        field_info: Pydantic FieldInfo

    Returns:
        Dict of HTML attribute names to values

    Examples:
        >>> from pydantic import Field
        >>> info = Field(min_length=3, max_length=20)
        >>> get_field_constraints(info)
        {"minlength": 3, "maxlength": 20}
    """
    if field_info is None:
        return {}

    constraints: dict[str, Any] = {}
    metadata = field_info.metadata or []

    for meta in metadata:
        meta_type = type(meta).__name__

        # String constraints
        if meta_type == "MinLen":
            constraints["minlength"] = meta.min_length
        elif meta_type == "MaxLen":
            constraints["maxlength"] = meta.max_length

        # Numeric constraints
        elif meta_type == "Ge":
            constraints["min"] = meta.ge
        elif meta_type == "Gt":
            constraints["min"] = meta.gt + 1  # Approximate gt with min
        elif meta_type == "Le":
            constraints["max"] = meta.le
        elif meta_type == "Lt":
            constraints["max"] = meta.lt - 1  # Approximate lt with max

        # Pattern
        elif meta_type == "Pattern":
            constraints["pattern"] = meta.pattern

    return constraints
