from typing import (
    Any,
    TypeVar,
    Generic,
)
from dataclasses import dataclass
from pyview.meta import PyViewMeta

T = TypeVar("T")


@dataclass
class LiveComponentMeta(PyViewMeta):
    myself: Any


class LiveComponentSocket(Generic[T]):
    context: T
    connected: bool
    meta: LiveComponentMeta
