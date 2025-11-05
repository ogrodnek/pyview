"""Function signature inspection utilities.

This module provides helpers for analyzing function signatures to determine
how parameters should be converted.
"""

import inspect
from typing import Any, get_type_hints
from dataclasses import is_dataclass


def get_skip_params_for_handler(func: Any, handler_type: str) -> set[str]:
    """
    Determine which parameters should be skipped for a given handler type.

    Different handler methods have different "special" parameters that
    should not be converted from raw params:
    - handle_params: 'self', 'url', 'socket'
    - handle_event: 'self', 'event', 'socket'

    Args:
        func: The function to analyze
        handler_type: Type of handler ('handle_params', 'handle_event', etc.)

    Returns:
        Set of parameter names to skip
    """
    sig = inspect.signature(func)
    param_names = list(sig.parameters.keys())

    # Always skip 'self'
    skip = {'self'}

    # Check for common special parameters
    if 'url' in param_names:
        skip.add('url')
    if 'socket' in param_names:
        skip.add('socket')
    if 'event' in param_names:
        skip.add('event')

    # For handle_params, if 'params' exists and has no type annotation or is dict,
    # it's the traditional raw params - skip it
    if 'params' in param_names:
        param = sig.parameters['params']
        if param.annotation == inspect.Parameter.empty:
            skip.add('params')
        elif param.annotation == dict or str(param.annotation).startswith('dict['):
            skip.add('params')

    # For handle_event, similar logic for 'payload'
    if 'payload' in param_names:
        param = sig.parameters['payload']
        if param.annotation == inspect.Parameter.empty:
            skip.add('payload')
        elif param.annotation == dict or str(param.annotation).startswith('dict['):
            skip.add('payload')

    return skip


def should_convert_params(func: Any) -> bool:
    """
    Determine if a function should have parameter conversion applied.

    Returns False if the function uses the traditional signature style
    (e.g., handle_params(self, url, params, socket) with no type annotations).

    Returns True if the function has typed parameters that should be converted.

    Args:
        func: Function to analyze

    Returns:
        True if parameter conversion should be applied
    """
    sig = inspect.signature(func)
    hints = get_type_hints(func, include_extras=True) if hasattr(func, '__annotations__') else {}

    # Get all parameters except common special ones
    convertible_params = [
        name for name in sig.parameters.keys()
        if name not in ('self', 'url', 'socket', 'event')
    ]

    # Check for traditional style: 'params' or 'payload' without type hints
    if 'params' in convertible_params:
        param = sig.parameters['params']
        if param.annotation == inspect.Parameter.empty:
            # Traditional style with no annotation
            return False

    if 'payload' in convertible_params:
        param = sig.parameters['payload']
        if param.annotation == inspect.Parameter.empty:
            # Traditional style with no annotation
            return False

    # If there are any typed parameters (excluding special ones), enable conversion
    for name in convertible_params:
        param = sig.parameters[name]
        if param.annotation != inspect.Parameter.empty:
            return True

    # No typed parameters found
    return False


def is_typed_dict_or_dataclass(annotation: Any) -> bool:
    """
    Check if an annotation is a TypedDict or dataclass.

    Args:
        annotation: Type annotation to check

    Returns:
        True if annotation is TypedDict or dataclass
    """
    # Check for dataclass
    if is_dataclass(annotation):
        return True

    # Check for TypedDict
    # TypedDict instances have __annotations__ and __required_keys__ / __optional_keys__
    if hasattr(annotation, '__annotations__'):
        if hasattr(annotation, '__required_keys__') or hasattr(annotation, '__optional_keys__'):
            return True
        # Check the __origin__ for typing_extensions.TypedDict
        if hasattr(annotation, '__origin__'):
            origin_str = str(annotation.__origin__)
            if 'TypedDict' in origin_str:
                return True

    return False


def get_conversion_strategy(func: Any) -> tuple[str, Any | None]:
    """
    Analyze function signature and determine conversion strategy.

    Strategies:
    - 'none': No conversion needed (traditional signature)
    - 'individual': Convert individual parameters (e.g., count: int, page: int)
    - 'typed_object': Convert to a single typed object (TypedDict, dataclass, etc.)

    Args:
        func: Function to analyze

    Returns:
        Tuple of (strategy_name, typed_object_type_or_none)

    Examples:
        >>> def f1(self, url, params, socket): pass
        >>> get_conversion_strategy(f1)
        ('none', None)

        >>> def f2(self, count: int, page: int): pass
        >>> get_conversion_strategy(f2)
        ('individual', None)

        >>> def f3(self, url, params: MyParams, socket): pass
        >>> get_conversion_strategy(f3)
        ('typed_object', MyParams)
    """
    if not should_convert_params(func):
        return ('none', None)

    sig = inspect.signature(func)

    # Check if 'params' or 'payload' has a typed annotation (TypedDict/dataclass)
    if 'params' in sig.parameters:
        param = sig.parameters['params']
        if param.annotation != inspect.Parameter.empty:
            if is_typed_dict_or_dataclass(param.annotation):
                return ('typed_object', param.annotation)

    if 'payload' in sig.parameters:
        param = sig.parameters['payload']
        if param.annotation != inspect.Parameter.empty:
            if is_typed_dict_or_dataclass(param.annotation):
                return ('typed_object', param.annotation)

    # Otherwise, assume individual parameter conversion
    return ('individual', None)
