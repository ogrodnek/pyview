"""Core binder for signature-driven parameter binding."""

from __future__ import annotations

import dataclasses
import inspect
import logging
from typing import Any, Callable, Generic, TypeVar, get_type_hints

from pyview.depends import _DependsMarker

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

        Supports Depends() for sync dependencies. Raises TypeError if an
        async dependency is encountered.

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
            hints = get_type_hints(func, include_extras=True)
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

            # Handle Depends separately (sync resolution)
            if isinstance(param.default, _DependsMarker):
                try:
                    bound[name] = self._resolve_depends_sync(param.default, ctx)
                except Exception as e:
                    errors.append(ParamError(name, "Depends", None, str(e)))
                continue

            # all other params
            result = self._resolve_param(name, param, expected, ctx)
            if result is not None:
                value, error = result
                if error:
                    errors.append(error)
                else:
                    bound[name] = value

        return BindResult(bound, errors)

    def _resolve_depends_sync(self, dep: _DependsMarker, ctx: BindContext[T]) -> Any:
        """Resolve a sync-only Depends() dependency.

        Raises TypeError if the dependency is async.
        """
        if inspect.iscoroutinefunction(dep.dependency):
            raise TypeError(
                f"Async dependency '{dep.dependency.__name__}' cannot be used in sync context. "
                "Use an async method like mount() for async dependencies."
            )

        if dep.use_cache and dep.dependency in ctx.cache:
            return ctx.cache[dep.dependency]

        # Recursively bind the dependency function's parameters
        result = self.bind(dep.dependency, ctx)
        if not result.success:
            raise ValueError(f"Dependency binding failed: {result.errors}")

        value = dep.dependency(**result.bound_args)

        if dep.use_cache:
            ctx.cache[dep.dependency] = value

        return value

    def _resolve_param(
        self,
        name: str,
        param: inspect.Parameter,
        expected: Any,
        ctx: BindContext[T],
    ) -> tuple[Any, ParamError | None] | None:
        """Resolve a single non-Depends parameter.

        Returns:
            - (value, None) if resolved successfully
            - (None, ParamError) if resolution failed
            - None if this is a Depends parameter (caller handles)
        """
        if isinstance(param.default, _DependsMarker):
            return None  # Caller handles sync/async

        # Try injectables
        injected = self.injectables.resolve(name, expected, ctx)
        if injected is not _NOT_FOUND:
            return (injected, None)

        # Dataclass parameter
        if dataclasses.is_dataclass(expected) and isinstance(expected, type):
            raw = self._resolve_dataclass_fields(expected, ctx)
            try:
                return (self.converter.convert(raw, expected), None)
            except ConversionError as e:
                return (None, ParamError(name, repr(expected), raw, str(e)))

        # Raw value from params/payload
        raw = self._resolve_raw(name, ctx)

        # Missing values
        if raw is None:
            if param.default is not inspect.Parameter.empty:
                return (param.default, None)
            if self.converter.is_optional(expected):
                return (None, None)
            return (None, ParamError(name, repr(expected), None, "missing required parameter"))

        # Convert
        try:
            return (self.converter.convert(raw, expected), None)
        except ConversionError as e:
            return (None, ParamError(name, repr(expected), raw, str(e)))

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
        sig = inspect.signature(func)

        try:
            hints = get_type_hints(func, include_extras=True)
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

            # Handle Depends separately (async resolution)
            if isinstance(param.default, _DependsMarker):
                try:
                    bound[name] = await self._resolve_depends(param.default, ctx)
                except Exception as e:
                    errors.append(ParamError(name, "Depends", None, str(e)))
                continue

            # all other params
            result = self._resolve_param(name, param, expected, ctx)
            if result is not None:
                value, error = result
                if error:
                    errors.append(error)
                else:
                    bound[name] = value

        return BindResult(bound, errors)

    async def _resolve_depends(self, dep: _DependsMarker, ctx: BindContext[T]) -> Any:
        """Resolve a Depends() dependency.

        Args:
            dep: The Depends marker with dependency callable and cache settings
            ctx: Binding context (includes cache dict)

        Returns:
            The resolved dependency value
        """
        if dep.use_cache and dep.dependency in ctx.cache:
            return ctx.cache[dep.dependency]

        # Recursively bind the dependency function's parameters
        result = await self.abind(dep.dependency, ctx)
        if not result.success:
            raise ValueError(f"Dependency binding failed: {result.errors}")

        # Call the dependency (sync or async)
        if inspect.iscoroutinefunction(dep.dependency):
            value = await dep.dependency(**result.bound_args)
        else:
            value = dep.dependency(**result.bound_args)

        if dep.use_cache:
            ctx.cache[dep.dependency] = value

        return value
