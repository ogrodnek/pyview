"""Core type conversion logic for parameters.

This module contains pure functions for converting raw parameter dictionaries
(dict[str, list[str] | str]) into typed Python values based on type annotations.

These functions are designed to be:
- Pure and side-effect free (easy to test)
- Independent of any framework concepts
- Usable directly without decorators
"""

from typing import Any, Union, get_origin, get_args, Type
import inspect


def normalize_param_value(value: Union[str, list[str]]) -> list[str]:
    """
    Normalize parameter values to list[str] format.

    Query params come as list[str] (from parse_qs), but path params come as str.
    This function normalizes both to list[str] for consistent handling.

    Args:
        value: Either a string (path param) or list of strings (query param)

    Returns:
        A list of strings

    Examples:
        >>> normalize_param_value("123")
        ["123"]
        >>> normalize_param_value(["123", "456"])
        ["123", "456"]
    """
    if isinstance(value, str):
        return [value]
    return value


def convert_scalar(value: str, target_type: Type) -> Any:
    """
    Convert a single string value to the target scalar type.

    Supports: str, int, float, bool

    Args:
        value: String value to convert
        target_type: Target Python type

    Returns:
        Converted value

    Raises:
        ValueError: If conversion fails

    Examples:
        >>> convert_scalar("123", int)
        123
        >>> convert_scalar("true", bool)
        True
        >>> convert_scalar("3.14", float)
        3.14
    """
    if target_type == str:
        return value

    if target_type == int:
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"Cannot convert '{value}' to int")

    if target_type == float:
        try:
            return float(value)
        except ValueError:
            raise ValueError(f"Cannot convert '{value}' to float")

    if target_type == bool:
        # Handle common boolean string representations
        lower_value = value.lower()
        if lower_value in ("true", "t", "1", "yes", "on"):
            return True
        elif lower_value in ("false", "f", "0", "no", "off", ""):
            return False
        else:
            # Non-empty strings are truthy in Python
            return bool(value)

    # For any other type, try calling its constructor
    try:
        return target_type(value)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Cannot convert '{value}' to {target_type.__name__}: {e}")


def convert_value(raw_value: Union[str, list[str]], target_type: Type) -> Any:
    """
    Convert a raw parameter value to the target type.

    Handles:
    - Scalar types: int, float, bool, str
    - Optional[T]: Returns None if value is missing/empty, otherwise converts to T
    - list[T]: Converts each element to T
    - Union types: Attempts conversion, with special handling for Optional

    Args:
        raw_value: Raw parameter value (str or list[str])
        target_type: Target type from type annotation

    Returns:
        Converted value

    Raises:
        ValueError: If conversion fails

    Examples:
        >>> convert_value("123", int)
        123
        >>> convert_value(["1", "2", "3"], list[int])
        [1, 2, 3]
        >>> convert_value([], Optional[int])
        None
        >>> convert_value(["123"], Optional[int])
        123
    """
    # Normalize to list format
    values = normalize_param_value(raw_value)

    # Get the origin and args for generic types
    origin = get_origin(target_type)
    args = get_args(target_type)

    # Handle Optional[T] (which is Union[T, None])
    if origin is Union:
        # Check if this is Optional (Union with None)
        if type(None) in args:
            # Optional type
            if not values or values == [""]:
                return None
            # Get the non-None type
            non_none_types = [t for t in args if t is not type(None)]
            if len(non_none_types) == 1:
                target_type = non_none_types[0]
                origin = get_origin(target_type)
                args = get_args(target_type)
            else:
                # Multiple non-None types in Union - not supported yet
                raise ValueError(f"Union types with multiple non-None types not supported: {target_type}")

    # Handle list[T]
    if origin is list:
        if not args:
            # Plain list without type parameter, return as strings
            return values

        inner_type = args[0]
        try:
            return [convert_scalar(v, inner_type) for v in values]
        except ValueError as e:
            raise ValueError(f"Cannot convert list values to {inner_type.__name__}: {e}")

    # Handle scalar types - take the first value
    if not values:
        raise ValueError(f"No value provided for required parameter")

    return convert_scalar(values[0], target_type)


def convert_params(
    raw_params: dict[str, Union[str, list[str]]],
    signature: inspect.Signature,
    skip_params: set[str] | None = None,
) -> dict[str, Any]:
    """
    Convert raw parameters to typed values based on function signature.

    This is the main entry point for parameter conversion. It:
    1. Inspects the function signature to get parameter names and types
    2. Converts raw parameter values to the appropriate types
    3. Applies default values for missing optional parameters
    4. Validates that required parameters are present

    Args:
        raw_params: Raw parameters dict (from parse_qs or path params)
        signature: Function signature (from inspect.signature())
        skip_params: Parameter names to skip (e.g., 'self', 'socket')

    Returns:
        Dictionary of parameter names to converted values

    Raises:
        ValueError: If required parameter is missing or conversion fails

    Examples:
        >>> def my_func(count: int = 0, page: int = 1): pass
        >>> sig = inspect.signature(my_func)
        >>> convert_params({"count": ["5"]}, sig)
        {"count": 5, "page": 1}
    """
    if skip_params is None:
        skip_params = set()

    converted = {}

    for param_name, param in signature.parameters.items():
        # Skip special parameters like 'self', 'socket', etc.
        if param_name in skip_params:
            continue

        # Get the type annotation
        if param.annotation == inspect.Parameter.empty:
            # No type annotation - try to pass through if value exists
            if param_name in raw_params:
                raw_value = raw_params[param_name]
                # Pass through as-is (for backward compatibility)
                converted[param_name] = raw_value
            elif param.default != inspect.Parameter.empty:
                converted[param_name] = param.default
            # If no annotation and no value, skip it
            continue

        target_type = param.annotation

        # Check if parameter is present in raw_params
        if param_name in raw_params:
            try:
                converted[param_name] = convert_value(raw_params[param_name], target_type)
            except ValueError as e:
                raise ValueError(f"Error converting parameter '{param_name}': {e}")
        elif param.default != inspect.Parameter.empty:
            # Use default value
            converted[param_name] = param.default
        else:
            # Check if it's Optional - if so, default to None
            origin = get_origin(target_type)
            args = get_args(target_type)
            if origin is Union and type(None) in args:
                # Optional type without default - use None
                converted[param_name] = None
            else:
                # Required parameter missing
                raise ValueError(f"Missing required parameter: '{param_name}'")

    return converted
