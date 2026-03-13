from __future__ import annotations

import sys
import weakref
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from typing import Any, Optional

from pyview.live_socket import ConnectedLiveViewSocket


@dataclass
class ConnectionInfo:
    topic: str
    view_class: type
    view_name: str
    route: str
    connected_at: datetime
    last_seen: datetime
    last_action: Optional[str]
    event_count: int
    total_event_duration: float
    socket_ref: weakref.ref[ConnectedLiveViewSocket]
    session_metadata: dict[str, Any]

    @property
    def socket(self) -> Optional[ConnectedLiveViewSocket]:
        """Resolve the weak reference. Returns None if the socket has been GC'd."""
        return self.socket_ref()


class ConnectionRegistry:
    """Tracks active LiveView connections for introspection."""

    def __init__(self):
        self._connections: dict[str, ConnectionInfo] = {}

    def register(
        self,
        topic: str,
        socket: ConnectedLiveViewSocket,
        view_class: type,
        route: str,
        session_metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        now = datetime.now()
        self._connections[topic] = ConnectionInfo(
            topic=topic,
            view_class=view_class,
            view_name=view_class.__name__,
            route=route,
            connected_at=now,
            last_seen=now,
            last_action=None,
            event_count=0,
            total_event_duration=0.0,
            socket_ref=weakref.ref(socket),
            session_metadata=session_metadata or {},
        )

    def unregister(self, topic: str) -> None:
        self._connections.pop(topic, None)

    def record_event(self, topic: str, event_name: str, duration: float) -> None:
        info = self._connections.get(topic)
        if info:
            info.last_seen = datetime.now()
            info.last_action = event_name
            info.event_count += 1
            info.total_event_duration += duration

    def get_all(self, exclude_view_classes: Optional[set[type]] = None) -> list[ConnectionInfo]:
        exclude = exclude_view_classes or set()
        return [c for c in self._connections.values() if c.view_class not in exclude]

    def get(self, topic: str) -> Optional[ConnectionInfo]:
        return self._connections.get(topic)

    @property
    def active_count(self) -> int:
        return len(self._connections)


# --- Context introspection utilities ---


def deep_getsizeof(obj: Any, seen: Optional[set[int]] = None) -> int:
    """Recursive sys.getsizeof that tracks visited objects to avoid double-counting."""
    if seen is None:
        seen = set()
    obj_id = id(obj)
    if obj_id in seen:
        return 0
    seen.add(obj_id)

    size = sys.getsizeof(obj)

    if isinstance(obj, dict):
        size += sum(deep_getsizeof(k, seen) + deep_getsizeof(v, seen) for k, v in obj.items())
    elif isinstance(obj, (list, tuple, set, frozenset)):
        size += sum(deep_getsizeof(item, seen) for item in obj)
    elif is_dataclass(obj) and not isinstance(obj, type):
        size += sum(deep_getsizeof(getattr(obj, f.name), seen) for f in fields(obj))

    return size


def inspect_context(context: Any) -> dict[str, Any]:
    """Safely inspect a LiveView context for debug display."""
    return {
        "total_size_bytes": deep_getsizeof(context),
        "type": type(context).__name__,
        "fields": _inspect_fields(context),
    }


_SENSITIVE_PATTERNS = {"password", "token", "secret", "key", "credential"}


def _inspect_fields(obj: Any) -> dict[str, dict[str, Any]]:
    """Return per-field size, type, and truncated repr."""
    items = _extract_fields(obj)
    result: dict[str, dict[str, Any]] = {}
    for name, value in items:
        is_sensitive = any(p in name.lower() for p in _SENSITIVE_PATTERNS)
        result[name] = {
            "size_bytes": deep_getsizeof(value),
            "type": type(value).__name__,
            "repr": "***" if is_sensitive else _truncated_repr(value),
        }
    return result


def _extract_fields(obj: Any) -> list[tuple[str, Any]]:
    """Extract (name, value) pairs from dicts, dataclasses, or objects."""
    if isinstance(obj, dict):
        return list(obj.items())
    if is_dataclass(obj) and not isinstance(obj, type):
        return [(f.name, getattr(obj, f.name)) for f in fields(obj)]
    try:
        return list(vars(obj).items())
    except TypeError:
        return []


def _truncated_repr(value: Any, max_len: int = 120) -> str:
    """Safe repr with truncation for large values."""
    try:
        r = repr(value)
        if len(r) > max_len:
            return r[: max_len - 3] + "..."
        return r
    except Exception:
        return f"<{type(value).__name__}>"
