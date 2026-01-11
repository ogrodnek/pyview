"""Path utilities for navigating nested data structures.

Supports dot-notation paths like:
- "name" - simple field
- "address.city" - nested model field
- "tags.0" - list index
- "addresses.0.city" - nested list item field
"""

from typing import Any


def parse_path(path: str) -> list[str | int]:
    """Parse dot-notation path into segments.

    Args:
        path: Dot-separated path string

    Returns:
        List of string keys and integer indices

    Examples:
        >>> parse_path("name")
        ["name"]
        >>> parse_path("address.city")
        ["address", "city"]
        >>> parse_path("tags.0")
        ["tags", 0]
        >>> parse_path("addresses.0.city")
        ["addresses", 0, "city"]
    """
    if not path:
        return []

    segments: list[str | int] = []
    for part in path.split("."):
        if part.isdigit():
            segments.append(int(part))
        else:
            segments.append(part)
    return segments


def get_nested(data: dict[str, Any], path: str, default: Any = None) -> Any:
    """Get value at nested path.

    Args:
        data: Dictionary to traverse
        path: Dot-notation path
        default: Value to return if path not found

    Returns:
        Value at path or default

    Examples:
        >>> get_nested({"user": {"name": "John"}}, "user.name")
        "John"
        >>> get_nested({"tags": ["a", "b"]}, "tags.0")
        "a"
    """
    segments = parse_path(path)
    current: Any = data

    for segment in segments:
        if current is None:
            return default

        if isinstance(segment, int):
            if isinstance(current, list) and 0 <= segment < len(current):
                current = current[segment]
            else:
                return default
        elif isinstance(current, dict):
            current = current.get(segment, default)
            if current is default:
                return default
        else:
            return default

    return current


def set_nested(data: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """Set value at nested path, creating intermediate structures as needed.

    This function mutates the input dict and also returns it for convenience.

    Args:
        data: Dictionary to modify
        path: Dot-notation path
        value: Value to set

    Returns:
        The modified dictionary

    Examples:
        >>> set_nested({}, "name", "John")
        {"name": "John"}
        >>> set_nested({}, "address.city", "NYC")
        {"address": {"city": "NYC"}}
        >>> set_nested({"tags": []}, "tags.0", "python")
        {"tags": ["python"]}
    """
    segments = parse_path(path)
    if not segments:
        return data

    current: Any = data

    for i, segment in enumerate(segments[:-1]):
        next_segment = segments[i + 1]

        if isinstance(segment, int):
            # Current position is a list index
            while len(current) <= segment:
                current.append(None)

            if current[segment] is None:
                # Create appropriate structure for next segment
                current[segment] = [] if isinstance(next_segment, int) else {}

            current = current[segment]
        else:
            # Current position is a dict key
            if segment not in current or current[segment] is None:
                # Create appropriate structure for next segment
                current[segment] = [] if isinstance(next_segment, int) else {}

            current = current[segment]

    # Set the final value
    final_segment = segments[-1]
    if isinstance(final_segment, int):
        while len(current) <= final_segment:
            current.append(None)
        current[final_segment] = value
    else:
        current[final_segment] = value

    return data


def join_path(*segments: str | int) -> str:
    """Join path segments into dot-notation string.

    Args:
        *segments: Path segments (strings or integers)

    Returns:
        Dot-separated path string

    Examples:
        >>> join_path("address", "city")
        "address.city"
        >>> join_path("tags", 0)
        "tags.0"
    """
    return ".".join(str(s) for s in segments)
