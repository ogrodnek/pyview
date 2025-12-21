from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar

from pyview.live_socket import LiveViewSocket

T = TypeVar("T")
R = TypeVar("R")


class Params:
    def __init__(self, values: dict[str, list[str]] | None = None) -> None:
        self._values = values or {}

    def get(self, key: str, default: str | None = None) -> str | None:
        values = self._values.get(key)
        if not values:
            return default
        return values[0]

    def getlist(self, key: str) -> list[str]:
        return list(self._values.get(key, []))

    def has(self, key: str) -> bool:
        return key in self._values

    def raw(self) -> dict[str, list[str]]:
        return self._values


@dataclass(frozen=True)
class BindContext(Generic[T]):
    params: Params
    socket: LiveViewSocket[T]


@dataclass(frozen=True)
class ParamError:
    key: str
    message: str


@dataclass(frozen=True)
class BindResult(Generic[T]):
    value: T | None
    errors: tuple[ParamError, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.errors


Provider = Callable[[BindContext[Any]], R]
Converter = Callable[[list[str]], R]


class InjectableRegistry(Generic[R]):
    def __init__(self) -> None:
        self._providers: dict[type[Any], Provider[R]] = {}

    def register(self, key: type[Any], provider: Provider[R]) -> None:
        self._providers[key] = provider

    def get(self, key: type[Any]) -> Provider[R] | None:
        return self._providers.get(key)

    def has(self, key: type[Any]) -> bool:
        return key in self._providers


class ConverterRegistry:
    def __init__(self) -> None:
        self._converters: dict[type[Any], Converter[Any]] = {}

    def register(self, key: type[Any], converter: Converter[Any]) -> None:
        self._converters[key] = converter

    def get(self, key: type[Any]) -> Converter[Any] | None:
        return self._converters.get(key)

    def has(self, key: type[Any]) -> bool:
        return key in self._converters
