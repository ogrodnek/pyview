from __future__ import annotations

import inspect
from types import UnionType
from typing import Any, Callable, Optional, Union, get_args, get_origin, get_type_hints


class Params(dict[str, list[str]]):
    """Marker type for raw params mapping."""


class ConverterRegistry:
    def __init__(self) -> None:
        self._converters: dict[type, Callable[[Any], Any]] = {
            int: self._convert_int,
            float: self._convert_float,
            str: self._convert_str,
            bool: self._convert_bool,
        }

    def convert(self, value: Any, target_type: Any) -> Any:
        if target_type is inspect._empty or target_type is Any:
            return value

        if value is None:
            return None

        origin = get_origin(target_type)
        args = get_args(target_type)

        if origin is list:
            return [self.convert(item, args[0]) for item in self._ensure_iterable(value)]

        if origin is set:
            return {self.convert(item, args[0]) for item in self._ensure_iterable(value)}

        if origin is tuple:
            if len(args) == 2 and args[1] is Ellipsis:
                return tuple(self.convert(item, args[0]) for item in self._ensure_iterable(value))
            return tuple(
                self.convert(item, item_type)
                for item, item_type in zip(self._ensure_iterable(value), args)
            )

        if self._is_union_type(target_type):
            for union_type in args:
                if union_type is type(None):
                    if value is None:
                        return None
                    continue
                try:
                    return self.convert(value, union_type)
                except (TypeError, ValueError):
                    continue
            raise ValueError(f"Unable to convert {value!r} to {target_type}")

        converter = self._converters.get(target_type)
        if converter:
            return converter(value)

        return value

    @staticmethod
    def _ensure_iterable(value: Any) -> list[Any]:
        if isinstance(value, (list, tuple, set)):
            return list(value)
        return [value]

    @staticmethod
    def _unwrap_singleton(value: Any) -> Any:
        if isinstance(value, list) and len(value) == 1:
            return value[0]
        return value

    def _convert_int(self, value: Any) -> int:
        return int(self._unwrap_singleton(value))

    def _convert_float(self, value: Any) -> float:
        return float(self._unwrap_singleton(value))

    def _convert_str(self, value: Any) -> str:
        return str(self._unwrap_singleton(value))

    def _convert_bool(self, value: Any) -> bool:
        value = self._unwrap_singleton(value)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y", "on"}:
                return True
            if normalized in {"false", "0", "no", "n", "off"}:
                return False
        return bool(value)

    @staticmethod
    def _is_union_type(target_type: Any) -> bool:
        origin = get_origin(target_type)
        return origin in {Union, UnionType}


class InjectableRegistry:
    def __init__(
        self,
        *,
        socket: Any = None,
        event: Any = None,
        payload: Any = None,
        url: Any = None,
        params: Any = None,
    ) -> None:
        self._values = {
            "socket": socket,
            "event": event,
            "payload": payload,
            "url": url,
            "params": params,
        }

    def has(self, name: str) -> bool:
        return name in self._values

    def get(self, name: str) -> Any:
        return self._values[name]


class Binder:
    def __init__(self, converter_registry: Optional[ConverterRegistry] = None) -> None:
        self.converter_registry = converter_registry or ConverterRegistry()

    def bind(self, func: Callable[..., Any], injectables: InjectableRegistry) -> tuple[list[Any], dict[str, Any]]:
        signature = inspect.signature(func)
        type_hints = get_type_hints(func)
        args: list[Any] = []
        kwargs: dict[str, Any] = {}

        for name, param in signature.parameters.items():
            if name == "self":
                continue

            annotation = type_hints.get(name, param.annotation)

            if injectables.has(name):
                value = injectables.get(name)
                if name == "params":
                    value = self._convert_params(value, annotation)
                self._assign_argument(param, name, value, args, kwargs)
                continue

            value, found = self._lookup_value(name, annotation, injectables)
            if not found:
                if param.default is not inspect._empty:
                    value = param.default
                elif self._is_optional(annotation):
                    value = None
                else:
                    raise TypeError(f"Missing required argument: {name}")

            self._assign_argument(param, name, value, args, kwargs)

        return args, kwargs

    def _lookup_value(
        self, name: str, annotation: Any, injectables: InjectableRegistry
    ) -> tuple[Any, bool]:
        payload = injectables.get("payload") if injectables.has("payload") else None
        if isinstance(payload, dict) and name in payload:
            return self._convert_value(payload[name], annotation), True

        params = injectables.get("params") if injectables.has("params") else None
        if isinstance(params, dict) and name in params:
            return self._convert_value(params[name], annotation), True

        return None, False

    def _convert_value(self, value: Any, annotation: Any) -> Any:
        if annotation is inspect._empty or annotation is Any:
            return value
        return self.converter_registry.convert(value, annotation)

    def _convert_params(self, params: Any, annotation: Any) -> Any:
        if annotation is inspect._empty or annotation is None:
            return params

        if annotation is Params:
            return params

        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin is dict and args and args[0] is str:
            value_type = args[1]
            if self._is_list_of_str(value_type):
                return params
            if value_type is Any:
                return self._flatten_params(params)
            return {
                key: self._convert_param_value(value, value_type)
                for key, value in (params or {}).items()
            }

        return params

    def _convert_param_value(self, value: Any, value_type: Any) -> Any:
        if self._treat_list_as_scalar(value, value_type):
            value = value[0]
        return self.converter_registry.convert(value, value_type)

    @staticmethod
    def _treat_list_as_scalar(value: Any, value_type: Any) -> bool:
        if not isinstance(value, list) or len(value) != 1:
            return False
        origin = get_origin(value_type)
        return origin not in {list, set, tuple}

    @staticmethod
    def _flatten_params(params: Any) -> dict[str, Any]:
        flattened: dict[str, Any] = {}
        for key, value in (params or {}).items():
            if isinstance(value, list):
                flattened[key] = value[0] if len(value) == 1 else value
            else:
                flattened[key] = value
        return flattened

    @staticmethod
    def _assign_argument(
        param: inspect.Parameter,
        name: str,
        value: Any,
        args: list[Any],
        kwargs: dict[str, Any],
    ) -> None:
        if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            args.append(value)
        elif param.kind is inspect.Parameter.KEYWORD_ONLY:
            kwargs[name] = value

    @staticmethod
    def _is_list_of_str(value_type: Any) -> bool:
        return get_origin(value_type) is list and get_args(value_type) == (str,)

    @staticmethod
    def _is_optional(annotation: Any) -> bool:
        return get_origin(annotation) in {Union, UnionType} and type(None) in get_args(annotation)


DEFAULT_BINDER = Binder()


async def call_handler(
    handler: Callable[..., Any],
    injectables: InjectableRegistry,
    binder: Binder = DEFAULT_BINDER,
) -> Any:
    args, kwargs = binder.bind(handler, injectables)
    result = handler(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result
