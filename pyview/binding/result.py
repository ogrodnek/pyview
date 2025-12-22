"""Result types for parameter binding."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ParamError:
    """Describes a parameter binding error."""

    name: str
    expected: str
    value: Any
    reason: str

    def __str__(self) -> str:
        return (
            f"Parameter '{self.name}': {self.reason} (expected {self.expected}, got {self.value!r})"
        )


@dataclass
class BindResult:
    """Result of binding parameters to a function signature."""

    bound_args: dict[str, Any]
    errors: list[ParamError]

    @property
    def success(self) -> bool:
        """True if binding completed without errors."""
        return len(self.errors) == 0
