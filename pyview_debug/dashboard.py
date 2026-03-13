from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, TypedDict

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket, is_connected
from pyview.events.info_event import InfoEvent

from pyview_debug.registry import ConnectionInfo, ConnectionRegistry, inspect_context


class ConnectionRow(TypedDict):
    topic: str
    view_name: str
    route: str
    connected_at: str
    last_seen: str
    last_action: str
    event_count: int
    avg_event_ms: str
    context_size: str


class DashboardContext(TypedDict):
    connections: list[ConnectionRow]
    routes: list[tuple[str, str]]
    active_count: int
    selected_topic: Optional[str]
    selected_info: Optional[dict[str, Any]]


def _format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M:%S")


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _connection_to_row(info: ConnectionInfo) -> ConnectionRow:
    avg_ms = ""
    if info.event_count > 0:
        avg_ms = f"{(info.total_event_duration / info.event_count) * 1000:.1f}"

    context_size = ""
    sock = info.socket
    if sock is not None:
        try:
            from pyview_debug.registry import deep_getsizeof

            context_size = _format_size(deep_getsizeof(sock.context))
        except Exception:
            context_size = "?"

    return ConnectionRow(
        topic=info.topic,
        view_name=info.view_name,
        route=info.route,
        connected_at=_format_time(info.connected_at),
        last_seen=_format_time(info.last_seen),
        last_action=info.last_action or "-",
        event_count=info.event_count,
        avg_event_ms=avg_ms,
        context_size=context_size,
    )


def _build_selected_info(info: ConnectionInfo) -> Optional[dict[str, Any]]:
    sock = info.socket
    if sock is None:
        return None

    try:
        ctx_inspection = inspect_context(sock.context)
    except Exception:
        ctx_inspection = {"total_size_bytes": 0, "type": "?", "fields": {}}

    return {
        "topic": info.topic,
        "view_name": info.view_name,
        "route": info.route,
        "connected_at": _format_time(info.connected_at),
        "event_count": info.event_count,
        "last_action": info.last_action or "-",
        "context": ctx_inspection,
        "component_count": sock.components.component_count if hasattr(sock.components, "component_count") else 0,
    }


def make_dashboard_view(
    registry: ConnectionRegistry,
    app: Any,
    dashboard_view_class: Optional[type] = None,
) -> type[LiveView]:
    """Factory that creates a dashboard LiveView class with registry and app baked in."""

    class DebugDashboardLiveView(LiveView[DashboardContext]):
        async def mount(self, socket: LiveViewSocket[DashboardContext], session):
            exclude = {DebugDashboardLiveView}

            connections = [_connection_to_row(c) for c in registry.get_all(exclude)]
            routes = [(fmt, cls.__name__) for fmt, cls in app.registered_routes]

            socket.context = DashboardContext(
                connections=connections,
                routes=routes,
                active_count=registry.active_count,
                selected_topic=None,
                selected_info=None,
            )

            if is_connected(socket):
                socket.schedule_info(InfoEvent("refresh"), 2)

        async def handle_info(
            self, event: InfoEvent, socket: ConnectedLiveViewSocket[DashboardContext]
        ):
            exclude = {DebugDashboardLiveView}
            connections = [_connection_to_row(c) for c in registry.get_all(exclude)]
            socket.context["connections"] = connections
            socket.context["active_count"] = registry.active_count

            # Refresh selected detail if one is open
            selected_topic = socket.context.get("selected_topic")
            if selected_topic:
                info = registry.get(selected_topic)
                if info:
                    socket.context["selected_info"] = _build_selected_info(info)
                else:
                    socket.context["selected_topic"] = None
                    socket.context["selected_info"] = None

        async def handle_event(
            self, event: str, payload: Any, socket: ConnectedLiveViewSocket[DashboardContext]
        ):
            if event == "select":
                topic = payload.get("topic", "")
                info = registry.get(topic)
                if info:
                    socket.context["selected_topic"] = topic
                    socket.context["selected_info"] = _build_selected_info(info)
                else:
                    socket.context["selected_topic"] = None
                    socket.context["selected_info"] = None
            elif event == "back":
                socket.context["selected_topic"] = None
                socket.context["selected_info"] = None

    return DebugDashboardLiveView
