"""Core binder for signature-driven parameter binding."""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import logging
from typing import TYPE_CHECKING, Any, Callable, Generic, TypeVar, get_type_hints

from .context import BindContext
from .converters import ConversionError, ConverterRegistry
from .injectables import _NOT_FOUND, InjectableRegistry
from .result import BindResult, ParamError

if TYPE_CHECKING:
    from pyview.depends import Depends

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

    async def abind(self, func: Callable[..., Any], ctx: BindContext[T]) -> BindResult:
        """Async bind with Depends() support.

        Same as bind(), but also resolves Depends() parameters by calling
        their dependency functions (which may be async).

        Args:
            func: The function to bind parameters for
            ctx: Binding context with params, payload, socket, etc.

        Returns:
            BindResult with bound_args dict and any errors
        """
        # Import here to avoid circular import
        from pyview.depends import Depends

        sig = inspect.signature(func)

        try:
            hints = get_type_hints(func)
        except (NameError, AttributeError, RecursionError) as e:
            logger.debug("Could not resolve type hints for %s: %s", func.__name__, e)
            hints = {}

        bound: dict[str, Any] = {}
        errors: list[ParamError] = []

        for name, param in sig.parameters.items():
            if name == "self":
                continue

            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            expected = hints.get(name, Any)

            # Check for Depends first
            if isinstance(param.default, Depends):
                try:
                    bound[name] = await self._resolve_depends(param.default, ctx)
                except Exception as e:
                    errors.append(ParamError(name, "Depends", None, str(e)))
                continue

            # Try injectables
            injected = self.injectables.resolve(name, expected, ctx)
            if injected is not _NOT_FOUND:
                bound[name] = injected
                continue

            # Check for dataclass parameter
            if dataclasses.is_dataclass(expected) and isinstance(expected, type):
                raw = self._resolve_dataclass_fields(expected, ctx)
                try:
                    bound[name] = self.converter.convert(raw, expected)
                except ConversionError as e:
                    errors.append(ParamError(name, repr(expected), raw, str(e)))
                continue

            # Pull raw value from params or payload
            raw = self._resolve_raw(name, ctx)

            # Handle missing values
            if raw is None:
                if param.default is not inspect.Parameter.empty:
                    bound[name] = param.default
                    continue
                if self.converter.is_optional(expected):
                    bound[name] = None
                    continue
                errors.append(ParamError(name, repr(expected), None, "missing required parameter"))
                continue

            # Convert to expected type
            try:
                bound[name] = self.converter.convert(raw, expected)
            except ConversionError as e:
                errors.append(ParamError(name, repr(expected), raw, str(e)))

        return BindResult(bound, errors)

    async def _resolve_depends(self, dep: "Depends", ctx: BindContext[T]) -> Any:
        """Resolve a Depends() dependency.

        Args:
            dep: The Depends marker with dependency callable and cache settings
            ctx: Binding context (includes cache dict)

        Returns:
            The resolved dependency value
        """
        # Check cache first
        if dep.use_cache and dep.dependency in ctx.cache:
            return ctx.cache[dep.dependency]

        # Recursively bind the dependency function's parameters
        result = await self.abind(dep.dependency, ctx)
        if not result.success:
            raise ValueError(f"Dependency binding failed: {result.errors}")

        # Call the dependency (sync or async)
        if asyncio.iscoroutinefunction(dep.dependency):
            value = await dep.dependency(**result.bound_args)
        else:
            value = dep.dependency(**result.bound_args)

        # Cache the result
        if dep.use_cache:
            ctx.cache[dep.dependency] = value

        return value
