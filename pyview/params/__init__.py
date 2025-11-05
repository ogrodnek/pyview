"""Parameter conversion for PyView handlers.

This module provides automatic type conversion for handle_params and handle_event
methods, converting raw dict[str, list[str] | str] parameters into typed Python values.

Main exports:
- typed_params: Decorator to enable type conversion
- convert_params: Core conversion function (for direct use)
- convert_value: Low-level conversion function (for testing)

Example usage:
    from pyview.params import typed_params

    class MyView(LiveView):
        @typed_params
        async def handle_params(self, count: int = 0, page: int = 1):
            # count and page are already converted!
            socket.context["count"] = count

        @event("increment")
        @typed_params
        async def on_increment(self, event, amount: int = 1, socket):
            # amount is converted from payload
            socket.context["count"] += amount
"""

import inspect
from functools import wraps
from typing import Any, Callable

from .conversion import convert_params, convert_value, convert_scalar, normalize_param_value
from .inspection import (
    get_skip_params_for_handler,
    should_convert_params,
    get_conversion_strategy,
)


__all__ = [
    'typed_params',
    'convert_params',
    'convert_value',
    'convert_scalar',
    'normalize_param_value',
]


def typed_params(func: Callable) -> Callable:
    """
    Decorator to enable automatic parameter type conversion.

    This decorator analyzes the function signature and converts raw parameters
    (dict[str, list[str] | str]) into typed Python values based on type annotations.

    Compatible with @event decorator - can be applied in any order:
        @event("click")
        @typed_params
        async def on_click(self, event, item_id: int, socket): ...

        @typed_params
        @event("click")
        async def on_click(self, event, item_id: int, socket): ...

    Args:
        func: Function to wrap (handle_params, handle_event, or @event method)

    Returns:
        Wrapped function with parameter conversion

    Usage:
        @typed_params
        async def handle_params(self, count: int = 0):
            socket.context["count"] = count

        @typed_params
        async def handle_event(self, event, item_id: int, enabled: bool = True, socket):
            # item_id and enabled are converted from payload
            pass
    """
    # Check if conversion is needed
    if not should_convert_params(func):
        # No type annotations, return as-is (backward compatibility)
        return func

    sig = inspect.signature(func)
    func_name = func.__name__

    # Determine which parameters to skip based on function signature
    # This handles both handle_params and handle_event cases
    skip_params = get_skip_params_for_handler(func, func_name)

    @wraps(func)  # Preserves __name__, __doc__, and other attributes (including _event_names)
    async def wrapper(*args, **kwargs):
        """Wrapper that performs parameter conversion before calling the original function."""

        # Two call patterns:
        # 1. Real usage from ws_handler.py: handle_params(self, url, params, socket) - positional
        # 2. Test/direct usage: handle_params(self, count=["5"], page=["2"]) - kwargs

        # If we have enough positional args, assume real usage pattern
        if len(args) >= 4:
            # Real usage: called from ws_handler.py
            # For handle_params: args = (self, url, params, socket)
            # For handle_event: args = (self, event, payload, socket)

            is_handle_params = 'handle_params' in func_name or 'url' in sig.parameters
            is_handle_event = 'handle_event' in func_name or 'event' in sig.parameters

            if is_handle_params:
                # args = (self, url, params, socket)
                raw_params = args[2]
                special_args = {'url': args[1], 'socket': args[3]}
            elif is_handle_event:
                # args = (self, event, payload, socket)
                raw_params = args[2]
                special_args = {'event': args[1], 'socket': args[3]}
            else:
                # Unknown pattern, pass through
                return await func(*args, **kwargs)

            if not isinstance(raw_params, dict):
                return await func(*args, **kwargs)

            # Convert the parameters
            try:
                converted = convert_params(raw_params, sig, skip_params)
            except ValueError as e:
                raise ValueError(f"Parameter conversion error in {func_name}: {e}")

            # Build final args
            final_args = {'self': args[0]}

            # Add special parameters if they exist in the signature
            for name in ('url', 'event', 'socket'):
                if name in sig.parameters and name in special_args:
                    final_args[name] = special_args[name]

            # Add converted parameters
            final_args.update(converted)

            return await func(**final_args)

        # Test/direct usage pattern: called with some positional + kwargs
        # E.g., handle_event(self, "event_name", item_id=["5"])
        # or handle_params(self, count=["5"], page=["2"])
        if kwargs:
            # Build a dict of the raw params from kwargs (excluding special params)
            raw_params = {k: v for k, v in kwargs.items() if k not in skip_params}

            if not raw_params:
                return await func(*args, **kwargs)

            # Convert the parameters
            try:
                converted = convert_params(raw_params, sig, skip_params)
            except ValueError as e:
                raise ValueError(f"Parameter conversion error in {func_name}: {e}")

            # Extract special args from kwargs
            special_args = {k: v for k, v in kwargs.items() if k in skip_params}

            # Build final args - start with positional args
            final_args = {}

            # Map positional args to their parameter names
            param_names = list(sig.parameters.keys())
            for i, arg in enumerate(args):
                if i < len(param_names):
                    final_args[param_names[i]] = arg

            # Add special args from kwargs
            final_args.update(special_args)

            # Add converted parameters
            final_args.update(converted)

            return await func(**final_args)

        # No conversion needed, pass through
        return await func(*args, **kwargs)

    return wrapper


# Make conversion functions available at package level for direct use
# This allows ws_handler.py to use them without the decorator
