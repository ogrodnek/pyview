"""Type conversion for parameter binding."""

import dataclasses
import types
from typing import Any, Union, get_args, get_origin, get_type_hints


class ConversionError(Exception):
    """Raised when type conversion fails."""

    pass


class ConverterRegistry:
    """Handles type conversion from raw string values to typed parameters.

    Supports:
    - Primitives: int, float, str, bool
    - Optional[T] and T | None: Returns None for missing/empty values
    - Union[T1, T2, ...] and T1 | T2: Tries each variant in order
    - Containers: list[T], set[T], tuple[T, ...]
    """

    def convert(self, raw: Any, expected: Any) -> Any:
        """Convert raw value to expected type.

        Args:
            raw: Raw value (usually str or list[str] from params)
            expected: Target type annotation

        Returns:
            Converted value

        Raises:
            ConversionError: If conversion fails
        """
        origin = get_origin(expected)
        args = get_args(expected)

        # Handle None/missing
        if raw is None:
            if self.is_optional(expected):
                return None
            raise ConversionError("Value is required")

        # Handle Optional / Union (both typing.Union and types.UnionType for X | Y syntax)
        if origin is Union or origin is types.UnionType:
            return self._convert_union(raw, args)

        # Handle list/set/tuple
        if origin in (list, set, tuple):
            return self._convert_container(raw, origin, args)

        # Handle scalar primitives
        if expected in (int, float, str, bool):
            return self._convert_scalar(raw, expected)

        # Handle dataclasses - construct from dict
        if dataclasses.is_dataclass(expected) and isinstance(expected, type):
            return self._convert_dataclass(raw, expected)

        # Fallback: return as-is
        return raw

    def _convert_dataclass(self, raw: Any, expected: type) -> Any:
        """Convert dict to dataclass instance."""
        if not isinstance(raw, dict):
            raise ConversionError(
                f"Expected dict for dataclass {expected.__name__}, got {type(raw).__name__}"
            )

        # Get type hints, falling back to empty for missing annotations
        # NameError: forward reference can't be resolved
        # AttributeError: accessing annotations on some objects
        # RecursionError: circular type references
        try:
            hints = get_type_hints(expected)
        except (NameError, AttributeError, RecursionError):
            hints = {}

        fields = dataclasses.fields(expected)
        kwargs: dict[str, Any] = {}

        missing_fields: list[str] = []

        for field in fields:
            field_type = hints.get(field.name, Any)
            if field.name in raw:
                kwargs[field.name] = self.convert(raw[field.name], field_type)
            elif field.default is not dataclasses.MISSING:
                kwargs[field.name] = field.default
            elif field.default_factory is not dataclasses.MISSING:
                kwargs[field.name] = field.default_factory()
            elif self.is_optional(field_type):
                kwargs[field.name] = None
            else:
                missing_fields.append(field.name)

        if missing_fields:
            raise ConversionError(
                f"Missing required fields for {expected.__name__}: {', '.join(missing_fields)}"
            )

        return expected(**kwargs)

    def _convert_union(self, raw: Any, args: tuple[type, ...]) -> Any:
        """Try each union variant in order."""
        errors: list[str] = []
        for variant in args:
            if variant is type(None):
                # Handle empty string as None for Optional
                if raw == "" or raw == [""]:
                    return None
                continue
            try:
                return self.convert(raw, variant)
            except (ConversionError, ValueError, TypeError) as e:
                errors.append(str(e))
        raise ConversionError(f"No union variant matched: {errors}")

    def _convert_container(self, raw: Any, origin: type, args: tuple[type, ...]) -> Any:
        """Convert to list/set/tuple.

        Handles:
        - list[T], set[T]: homogeneous containers
        - tuple[T, ...]: homogeneous variable-length tuple
        - tuple[T1, T2, T3]: heterogeneous fixed-length tuple
        """
        items = raw if isinstance(raw, list) else [raw]

        if origin is tuple and args:
            # Check for homogeneous tuple: tuple[T, ...] has Ellipsis as second arg
            if len(args) == 2 and args[1] is ...:
                inner = args[0]
                converted = [self.convert(v, inner) for v in items]
            else:
                # Heterogeneous tuple: tuple[T1, T2, T3]
                if len(items) != len(args):
                    raise ConversionError(
                        f"Expected {len(args)} values for tuple, got {len(items)}"
                    )
                converted = [
                    self.convert(item, arg_type) for item, arg_type in zip(items, args, strict=True)
                ]
            return tuple(converted)

        # list[T] or set[T]: homogeneous
        inner = args[0] if args else str
        converted = [self.convert(v, inner) for v in items]

        if origin is list:
            return converted
        if origin is set:
            return set(converted)
        return tuple(converted)

    def _convert_scalar(self, raw: Any, expected: type) -> Any:
        """Convert to scalar type, picking first if input is a list."""
        # Normalize: if list, take first element
        if isinstance(raw, list):
            if not raw:
                raise ConversionError("Empty list for scalar type")
            raw = raw[0]

        if expected is bool:
            return self._convert_bool(raw)

        try:
            return expected(raw)
        except (ValueError, TypeError) as e:
            raise ConversionError(f"Cannot convert {raw!r} to {expected.__name__}: {e}") from e

    def _convert_bool(self, raw: Any) -> bool:
        """Convert to boolean with common string values."""
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        s = str(raw).lower().strip()
        if s in ("true", "1", "yes", "on"):
            return True
        if s in ("false", "0", "no", "off", ""):
            return False
        raise ConversionError(f"Cannot convert {raw!r} to bool")

    def is_optional(self, expected: Any) -> bool:
        """Check if type is Optional[T] (Union[T, None] or T | None)."""
        origin = get_origin(expected)
        if origin is Union or origin is types.UnionType:
            return type(None) in get_args(expected)
        return False
