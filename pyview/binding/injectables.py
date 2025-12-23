"""Injectable parameter resolution for special runtime objects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar, get_args, get_origin

from .converters import ConverterRegistry
from .params import Params

if TYPE_CHECKING:
    from .context import BindContext

# Sentinel to distinguish "not resolvable" from "resolved to None"
_NOT_FOUND = object()

T = TypeVar("T")


class InjectableRegistry(Generic[T]):
    """Resolves special injectable parameters by name or type.

    Injectables are parameters that come from the runtime context rather than
    from user-provided params/payload. Examples: socket, event, payload, url, params.
    """

    def resolve(
        self,
        name: str,
        annotation: Any,
        ctx: BindContext[T],
    ) -> Any | None:
        """Try to resolve a parameter from injectables.

        Args:
            name: Parameter name
            annotation: Parameter type annotation
            ctx: Binding context with available values

        Returns:
            The injectable value, or None if not resolvable
        """
        # Name-based injection
        if name == "socket":
            return ctx.socket
        if name == "event":
            return ctx.event
        if name == "payload":
            return ctx.payload
        if name == "url":
            return ctx.url
        if name == "params":
            # Only inject if typed as Params, dict, or untyped (Any)
            # Otherwise treat "params" as a regular URL param name
            if self._is_params_annotation(annotation):
                return self._resolve_params(annotation, ctx)
            return _NOT_FOUND

        # Check extra injectables
        if name in ctx.extra:
            return ctx.extra[name]

        return _NOT_FOUND

    def _is_params_annotation(self, annotation: Any) -> bool:
        """Check if annotation indicates params injection vs URL param named 'params'."""
        # Untyped (Any) -> inject for backward compat
        if annotation is Any:
            return True
        # Explicit Params type
        if annotation is Params:
            return True
        # dict or dict[...] -> inject
        return annotation is dict or get_origin(annotation) is dict

    def _resolve_params(self, annotation: Any, ctx: BindContext[T]) -> Any:
        """Resolve params parameter based on annotation type."""
        origin = get_origin(annotation)
        args = get_args(annotation)

        # params: Params -> return wrapper
        if annotation is Params:
            return ctx.params

        # Handle dict annotations
        if annotation is dict or origin is dict:
            # params: dict[str, list[str]] -> return raw
            if args == (str, list[str]):
                return ctx.params.raw()

            # params: dict[str, Any] -> flatten
            if len(args) == 2 and args[0] is str:
                if args[1] is Any:
                    return ctx.params.to_flat_dict()

                # params: dict[str, T] -> convert values
                value_type = args[1]
                return self._convert_dict_values(ctx.params, value_type)

            # Bare dict or dict[str, list[str]] default
            if not args:
                return ctx.params.to_flat_dict()

        # Default: return Params wrapper
        return ctx.params

    def _convert_dict_values(
        self,
        params: Params,
        value_type: type,
    ) -> dict[str, Any]:
        """Convert all param values to specified type."""
        converter = ConverterRegistry()
        result: dict[str, Any] = {}

        for key in params:
            raw = params.getlist(key)
            result[key] = converter.convert(raw, value_type)

        return result
