"""Binding context for parameter resolution."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar
from urllib.parse import ParseResult

if TYPE_CHECKING:
    from pyview.live_socket import LiveViewSocket

    from .params import Params

T = TypeVar("T")


@dataclass
class BindContext(Generic[T]):
    """Context provided to the binder for resolving parameter values.

    Attributes:
        params: Multi-value parameter container (query/path/form merged)
        payload: Event payload dict (for handle_event)
        url: Parsed URL (for handle_params)
        socket: LiveView socket instance
        event: Event name (for handle_event)
        extra: Additional injectable values
    """

    params: "Params"
    payload: Optional[dict[str, Any]]
    url: Optional[ParseResult]
    socket: Optional["LiveViewSocket[T]"]
    event: Optional[str]
    extra: dict[str, Any] = field(default_factory=dict)
