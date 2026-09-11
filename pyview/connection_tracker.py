from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pyview.live_socket import ConnectedLiveViewSocket
    from pyview.live_view import LiveView


@runtime_checkable
class ConnectionTracker(Protocol):
    """Protocol for tracking LiveView connection lifecycle.

    Implement this protocol to receive callbacks at key lifecycle points.
    All methods should be fast and non-blocking — they're called inline
    in the WebSocket handler hot path.
    """

    def on_connect(
        self,
        topic: str,
        socket: ConnectedLiveViewSocket,
        view_class: type[LiveView],
        route: str,
        session: dict[str, Any],
    ) -> None:
        """Called when a LiveView mounts and completes its first render."""
        ...

    def on_disconnect(self, topic: str) -> None:
        """Called when a LiveView WebSocket connection is closed."""
        ...

    def on_event(
        self,
        topic: str,
        event_name: str,
        duration_seconds: float,
    ) -> None:
        """Called after an event is processed and rendered."""
        ...
