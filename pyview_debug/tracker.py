from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyview_debug.registry import ConnectionRegistry

if TYPE_CHECKING:
    from pyview.live_socket import ConnectedLiveViewSocket
    from pyview.live_view import LiveView


class DebugTracker:
    """Implements the ConnectionTracker protocol, populates a ConnectionRegistry."""

    def __init__(self, registry: ConnectionRegistry):
        self.registry = registry

    def on_connect(
        self,
        topic: str,
        socket: ConnectedLiveViewSocket,
        view_class: type[LiveView],
        route: str,
        session: dict[str, Any],
    ) -> None:
        self.registry.register(
            topic=topic,
            socket=socket,
            view_class=view_class,
            route=route,
            session_metadata=_extract_session_metadata(session),
        )

    def on_disconnect(self, topic: str) -> None:
        self.registry.unregister(topic)

    def on_event(self, topic: str, event_name: str, duration_seconds: float) -> None:
        self.registry.record_event(topic, event_name, duration_seconds)


class ChainedTracker:
    """Forwards lifecycle events to multiple trackers."""

    def __init__(self, *trackers: Any):
        self.trackers = trackers

    def on_connect(
        self,
        topic: str,
        socket: ConnectedLiveViewSocket,
        view_class: type[LiveView],
        route: str,
        session: dict[str, Any],
    ) -> None:
        for t in self.trackers:
            t.on_connect(topic, socket, view_class, route, session)

    def on_disconnect(self, topic: str) -> None:
        for t in self.trackers:
            t.on_disconnect(topic)

    def on_event(self, topic: str, event_name: str, duration_seconds: float) -> None:
        for t in self.trackers:
            t.on_event(topic, event_name, duration_seconds)


def _extract_session_metadata(session: dict[str, Any]) -> dict[str, Any]:
    """Extract safe metadata from session, excluding sensitive values."""
    safe_keys = {"user_id", "user", "role", "username", "email"}
    return {k: v for k, v in session.items() if k in safe_keys}
