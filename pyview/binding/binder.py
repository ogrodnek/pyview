"""Core binder for signature-driven parameter binding."""

from __future__ import annotations

import dataclasses
import inspect
import logging
from typing import Any, Callable, Generic, TypeVar, get_type_hints

from .context import BindContext
from .converters import ConversionError, ConverterRegistry
from .injectables import _NOT_FOUND, InjectableRegistry
from .result import BindResult, ParamError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Binder(Generic[T]):
    """Binds function parameters from BindContext based on type annotations.

    The binder inspects a function's signature and type hints, then:
    1. Resolves injectable parameters (socket, event, payload, url, params)
    2. Pulls values from params or payload for other parameters
    3. Converts values to the expected types
    4. Returns a BindResult with bound_args and any errors
    """

    def __init__(
        self,
        converter: ConverterRegistry | None = None,
        injectables: InjectableRegistry[T] | None = None,
    ):
        self.converter = converter or ConverterRegistry()
        self.injectables = injectables or InjectableRegistry()

    def bind(self, func: Callable[..., Any], ctx: BindContext[T]) -> BindResult:
        """Bind context values to function signature.

        Args:
            func: The function to bind parameters for
            ctx: Binding context with params, payload, socket, etc.

        Returns:
            BindResult with bound_args dict and any errors
        """
        sig = inspect.signature(func)

        # Get type hints, falling back to empty for missing annotations
        # NameError: forward reference can't be resolved
        # AttributeError: accessing annotations on some objects
        # RecursionError: circular type references
        try:
            hints = get_type_hints(func)
        except (NameError, AttributeError, RecursionError) as e:
            logger.debug("Could not resolve type hints for %s: %s", func.__name__, e)
            hints = {}

        bound: dict[str, Any] = {}
        errors: list[ParamError] = []

        for name, param in sig.parameters.items():
            # Skip 'self' for methods
            if name == "self":
                continue

            # Skip *args and **kwargs (VAR_POSITIONAL and VAR_KEYWORD)
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            expected = hints.get(name, Any)

            # 1) Try injectables first
            injected = self.injectables.resolve(name, expected, ctx)
            if injected is not _NOT_FOUND:
                bound[name] = injected
                continue

            # 2) Check for dataclass parameter - gather fields from params
            if dataclasses.is_dataclass(expected) and isinstance(expected, type):
                raw = self._resolve_dataclass_fields(expected, ctx)
                try:
                    bound[name] = self.converter.convert(raw, expected)
                except ConversionError as e:
                    errors.append(ParamError(name, repr(expected), raw, str(e)))
                continue

            # 3) Pull raw value from params or payload
            raw = self._resolve_raw(name, ctx)

            # 4) Handle missing values
            if raw is None:
                if param.default is not inspect.Parameter.empty:
                    bound[name] = param.default
                    continue
                if self.converter.is_optional(expected):
                    bound[name] = None
                    continue
                errors.append(ParamError(name, repr(expected), None, "missing required parameter"))
                continue

            # 5) Convert to expected type
            try:
                bound[name] = self.converter.convert(raw, expected)
            except ConversionError as e:
                errors.append(ParamError(name, repr(expected), raw, str(e)))

        return BindResult(bound, errors)

    def _resolve_dataclass_fields(self, expected: type, ctx: BindContext[T]) -> dict[str, Any]:
        """Gather dataclass fields from params."""
        fields = dataclasses.fields(expected)
        result: dict[str, Any] = {}

        for field in fields:
            if ctx.params.has(field.name):
                result[field.name] = ctx.params.getlist(field.name)
            elif ctx.payload and field.name in ctx.payload:
                result[field.name] = ctx.payload[field.name]

        return result

    def _resolve_raw(self, name: str, ctx: BindContext[T]) -> Any | None:
        """Resolve raw value from params or payload."""
        # Check params first
        if ctx.params.has(name):
            return ctx.params.getlist(name)

        # Check payload
        if ctx.payload and name in ctx.payload:
            return ctx.payload[name]

        return None
