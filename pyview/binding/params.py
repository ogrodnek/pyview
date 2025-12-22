"""Multi-value parameter container for query/path/form params."""

from typing import Any, Iterator, Optional


class Params:
    """Multi-value parameter container wrapping dict[str, list[str]].

    This provides a convenient interface for accessing parameters that may have
    multiple values (e.g., from query strings like ?tag=a&tag=b).
    """

    def __init__(self, data: dict[str, list[str]]) -> None:
        self._data = data

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get first value for key, or default if missing."""
        values = self._data.get(key)
        return values[0] if values else default

    def getlist(self, key: str) -> list[str]:
        """Get all values for key as a list."""
        return self._data.get(key, [])

    def getone(self, key: str) -> str:
        """Get exactly one value for key.

        Raises:
            KeyError: If key is missing or has multiple values.
        """
        values = self._data.get(key, [])
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
            if v:
                yield k, v[0]

    def multi_items(self) -> Iterator[tuple[str, str]]:
        """Iterate over all (key, value) pairs including multi-values."""
        for k, values in self._data.items():
            for v in values:
                yield k, v

    def raw(self) -> dict[str, list[str]]:
        """Return the underlying dict[str, list[str]]."""
        return self._data

    def to_flat_dict(self) -> dict[str, Any]:
        """Convert to flat dict.

        Single values become scalars, multiple values remain as lists.
        """
        result: dict[str, Any] = {}
        for k, v in self._data.items():
            result[k] = v[0] if len(v) == 1 else v
        return result

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"Params({self._data!r})"
