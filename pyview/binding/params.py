"""Multi-value parameter container for query/path/form params."""

from typing import Any, Iterator, Optional


def _as_list(value: Any) -> list[str]:
    """Convert a value to list[str].

    Handles mixed sources:
    - Query params from parse_qs() are already list[str]
    - Path params from Starlette are single values (str or int)
    """
    if isinstance(value, list):
        return value
    elif value is not None:
        return [str(value)]
    else:
        return []


class Params:
    """Multi-value parameter container for query/path/form params.

    This provides a convenient interface for accessing parameters that may have
    multiple values (e.g., from query strings like ?tag=a&tag=b).

    Handles mixed value types:
    - Query params from parse_qs(): list[str]
    - Path params from Starlette: str or int
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get first value for key, or default if missing."""
        values = _as_list(self._data.get(key))
        return values[0] if values else default

    def getlist(self, key: str) -> list[str]:
        """Get all values for key as a list."""
        return _as_list(self._data.get(key))

    def getone(self, key: str) -> str:
        """Get exactly one value for key.

        Raises:
            KeyError: If key is missing or has multiple values.
        """
        values = _as_list(self._data.get(key))
        if len(values) != 1:
            raise KeyError(f"Expected exactly one value for '{key}', got {len(values)}")
        return values[0]

    def has(self, key: str) -> bool:
        """Check if key exists."""
        return key in self._data

    def keys(self) -> list[str]:
        """Return all keys."""
        return list(self._data.keys())

    def items(self) -> Iterator[tuple[str, str]]:
        """Iterate over (key, value) pairs (first value only for each key)."""
        for k, v in self._data.items():
            values = _as_list(v)
            if values:
                yield k, values[0]

    def multi_items(self) -> Iterator[tuple[str, str]]:
        """Iterate over all (key, value) pairs including multi-values."""
        for k, v in self._data.items():
            for val in _as_list(v):
                yield k, val

    def raw(self) -> dict[str, Any]:
        """Return the underlying dict (may contain mixed value types)."""
        return self._data

    def to_flat_dict(self) -> dict[str, Any]:
        """Convert to flat dict.

        Single values become scalars, multiple values remain as lists.
        """
        result: dict[str, Any] = {}
        for k, v in self._data.items():
            values = _as_list(v)
            result[k] = values[0] if len(values) == 1 else values
        return result

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __getitem__(self, key: str) -> Any:
        """Get raw value for key (returns original type from underlying dict)."""
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"Params({self._data!r})"
