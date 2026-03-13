# PyView Debug Dashboard — Design Document

## Overview

A debug dashboard that gives pyview developers real-time visibility into their running application: active LiveViews, routes, context sizes, event activity, and the ability to drill into individual LiveView state.

**Key constraint**: The dashboard should be a **separate package** (e.g. `pyview-debug`) that users install alongside pyview and wire in with minimal configuration. The pyview core changes should be as **minimal as possible** — just enough of a seam for the external package to do everything else.

## What the Dashboard Shows

### Summary View (Landing Page)
- Total active LiveView connections
- Registered routes with their LiveView class names
- Global event rate / recent event count
- Server uptime

### Active LiveViews Table
| Column | Description |
|--------|-------------|
| Topic | The Phoenix-style topic ID (e.g. `lv:phx-...`) |
| Route | The URL path this LiveView is serving |
| View | LiveView class name (e.g. `PlaybackLiveView`) |
| Connected At | When the WebSocket connection was established |
| Last Seen | Last event or heartbeat timestamp |
| Last Action | Name of the most recent event handled |
| Event Count | Total events processed for this connection |
| Context Size | Approximate size of `socket.context` in bytes |
| View Size | Approximate size of the rendered output |
| User | Session-derived user info (if available) |

### Detail View (Click Into a LiveView)
- Full context state (formatted JSON/repr, expandable tree)
- Component tree with per-component state
- Event history (recent N events with timestamps, payloads, durations)
- Rendered output size over time
- PubSub subscriptions for this socket
- Scheduled jobs

---

## Why the External Package Can't Do It Alone (Today)

Before settling on the architecture, it's worth understanding what approaches are available with **zero pyview changes** and where they fall short.

### Approach 1: Wrap the InstrumentationProvider

The external package could swap in a wrapping `InstrumentationProvider`:

```python
debug_provider = DebugInstrumentationProvider(app.instrumentation, registry)
app.live_handler.instrumentation = debug_provider
app.live_handler.metrics = LiveSocketMetrics(debug_provider)
```

**Problem**: The current metric calls don't carry connection identity:

```python
# ws_handler.py — what's emitted today:
self.metrics.mounts.add(1, {"view": view_name})            # no topic
self.metrics.events_processed.add(1, {"event": ..., "view": ...})  # no topic
self.metrics.active_connections.add(1)                       # no attributes at all
```

You'd see "a PlaybackLiveView mounted" but not *which* connection. You can't build a per-connection registry from aggregate metrics.

### Approach 2: Monkey-patch `LiveSocketHandler.handle`

```python
original_handle = app.live_handler.handle
async def wrapped_handle(websocket):
    registry.note_connection(websocket)
    try:
        await original_handle(websocket)
    finally:
        registry.note_disconnection(websocket)
app.live_handler.handle = wrapped_handle
```

This gives connect/disconnect timing, but `handle()` is a ~400-line method. You can't see inside it — which view class mounted, which events fired, what the context looks like. You'd only know a WebSocket opened and closed.

### Approach 3: Deep monkey-patching

Replace both `handle` and `handle_connected` with versions that intercept the Phoenix protocol messages. This technically *works* but you're forking ws_handler.py internals. It breaks whenever pyview changes that code.

### Conclusion

The external package needs pyview to provide a **thin, stable seam** — a small interface it calls at key lifecycle points, giving the external package enough context to build everything else.

---

## The Minimal PyView Change: `ConnectionTracker` Protocol

The single addition to pyview core is a **protocol** (interface) that `ws_handler.py` calls at lifecycle boundaries. The external package implements it. PyView ships no registry, no hook system, no dashboard — just the call sites.

```python
# pyview/connection_tracker.py

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
        """Called when a LiveView WebSocket connection is established."""
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
        """Called after an event is processed."""
        ...
```

That's it — ~30 lines of protocol definition. No implementation in pyview core.

### Integration into ws_handler.py (~10 lines of call sites)

```python
class LiveSocketHandler:
    def __init__(self, routes, instrumentation, connection_tracker=None):
        ...
        self.connection_tracker = connection_tracker

    async def handle(self, websocket):
        ...
        # After successful join:
        if self.connection_tracker:
            self.connection_tracker.on_connect(topic, socket, lv_class, url.path, session)

        # In disconnect/error cleanup:
        if self.connection_tracker and topic:
            self.connection_tracker.on_disconnect(topic)

    async def handle_connected(self, myJoinId, socket):
        ...
        # After event processing (inside the timing block):
        if self.connection_tracker:
            self.connection_tracker.on_event(topic, event_name, duration)
```

### Wiring in PyView.__init__

```python
class PyView(Starlette):
    def __init__(self, *args, instrumentation=None, connection_tracker=None, **kwargs):
        ...
        self.connection_tracker = connection_tracker
        self.live_handler = LiveSocketHandler(
            self.view_lookup, self.instrumentation, self.connection_tracker
        )
```

### Public route accessor (one property)

```python
# On PyView class:
@property
def registered_routes(self) -> list[tuple[str, type[LiveView]]]:
    """Return list of (path_format, view_class) for all registered LiveViews."""
    return [(fmt, cls) for fmt, _, _, cls in self.view_lookup.routes]
```

### Total pyview core footprint

| What | Lines |
|------|-------|
| `ConnectionTracker` protocol definition | ~30 |
| Call sites in `ws_handler.py` | ~10 |
| `connection_tracker` param on `PyView.__init__` | ~3 |
| `registered_routes` property | ~4 |
| **Total** | **~47 lines** |

Zero overhead when `connection_tracker is None` — just a falsy check at each call site.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     User's PyView App                            │
│                                                                  │
│  from pyview_debug import enable_debug                           │
│                                                                  │
│  app = PyView()                                                  │
│  app.add_live_view("/posts", PostsView)                          │
│  app.add_live_view("/chat", ChatView)                            │
│  enable_debug(app)                                               │
│                                                                  │
└──────┬───────────────────────────────────────────────────────────┘
       │
       │ enable_debug() does:
       │
       ├─► Sets app.connection_tracker = DebugTracker(registry)
       │     (implements ConnectionTracker protocol)
       │
       ├─► Registers DebugDashboardLiveView at /debug
       │
       └─► DebugTracker populates ConnectionRegistry
             on_connect  → registry.register(...)
             on_disconnect → registry.unregister(...)
             on_event    → registry.record_event(...)

┌──────────────────────────────────────────────────────────────────┐
│                pyview-debug (external package)                    │
│                                                                  │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │  DebugTracker    │  │ ConnectionRegistry│  │ Dashboard      │  │
│  │  (implements     │  │ (dict of          │  │ LiveView       │  │
│  │  ConnectionTracker│ │  ConnectionInfo)  │  │ (renders UI)   │  │
│  │  protocol)       │  │                  │  │                │  │
│  └────────┬─────────┘  └────────▲─────────┘  └───────┬────────┘  │
│           │ populates           │ reads from          │           │
│           └─────────────────────┘                     │           │
│                                         polls via schedule_info  │
│                                         + PubSub for live updates│
└──────────────────────────────────────────────────────────────────┘
```

### Everything in the external package

| Component | Responsibility | Lives in |
|-----------|---------------|----------|
| `ConnectionTracker` protocol | Defines the interface | **pyview core** |
| Call sites (4-5 places in ws_handler) | Fires lifecycle callbacks | **pyview core** |
| `registered_routes` property | Exposes route list | **pyview core** |
| `DebugTracker` | Implements the protocol, populates registry | pyview-debug |
| `ConnectionRegistry` | Tracks active connections with metadata | pyview-debug |
| `ConnectionInfo` dataclass | Per-connection state (topic, view, route, timing, etc.) | pyview-debug |
| `DebugDashboardLiveView` | The dashboard UI | pyview-debug |
| `enable_debug()` | One-line setup entrypoint | pyview-debug |
| Context introspection | Safe serialization, size estimation | pyview-debug |
| Security / auth gating | Optional auth wrapper for dashboard | pyview-debug |

---

## The External Package: `pyview-debug`

### Installation & Setup

```python
# pip install pyview-debug

from pyview import PyView
from pyview_debug import enable_debug

app = PyView()
app.add_live_view("/posts", PostsView)

# One line — adds /debug route and installs the tracker
enable_debug(app, path="/debug")
```

### What `enable_debug()` Does

```python
def enable_debug(app: PyView, path: str = "/debug", auth=None):
    registry = ConnectionRegistry()

    # Install the tracker on the app (pyview will call it at lifecycle points)
    tracker = DebugTracker(registry)

    # If user already has a tracker, chain them
    if app.connection_tracker:
        tracker = ChainedTracker(app.connection_tracker, tracker)

    app.connection_tracker = tracker

    # Also need to update the live_handler reference
    app.live_handler.connection_tracker = tracker

    # Register the dashboard LiveView
    dashboard_factory = make_dashboard_view(registry, app)
    app.add_live_view(path, dashboard_factory)
```

### DebugTracker (Implements the Protocol)

```python
class DebugTracker:
    """Implements ConnectionTracker, populates a ConnectionRegistry."""

    def __init__(self, registry: ConnectionRegistry):
        self.registry = registry

    def on_connect(self, topic, socket, view_class, route, session):
        self.registry.register(
            topic=topic,
            socket=socket,
            view_class=view_class,
            route=route,
            session_metadata=_extract_session_metadata(session),
        )
        # Broadcast update to any listening dashboard LiveViews
        # (via PubSub — the dashboard subscribes to a debug topic)

    def on_disconnect(self, topic):
        self.registry.unregister(topic)

    def on_event(self, topic, event_name, duration_seconds):
        self.registry.record_event(topic, event_name, duration_seconds)
```

### ConnectionRegistry (All External)

```python
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
    socket_ref: weakref.ref[ConnectedLiveViewSocket]  # weak reference — won't prevent GC
    session_metadata: dict                              # safe subset of session data

    @property
    def socket(self) -> Optional[ConnectedLiveViewSocket]:
        """Resolve the weak reference. Returns None if the socket has been GC'd."""
        return self.socket_ref()

class ConnectionRegistry:
    def __init__(self):
        self._connections: dict[str, ConnectionInfo] = {}

    def register(self, topic, socket, view_class, route, session_metadata):
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
            session_metadata=session_metadata,
        )

    def unregister(self, topic):
        self._connections.pop(topic, None)

    def record_event(self, topic, event_name, duration):
        info = self._connections.get(topic)
        if info:
            info.last_seen = datetime.now()
            info.last_action = event_name
            info.event_count += 1
            info.total_event_duration += duration

    def get_all(self) -> list[ConnectionInfo]:
        return list(self._connections.values())

    def get(self, topic) -> Optional[ConnectionInfo]:
        return self._connections.get(topic)

    @property
    def active_count(self) -> int:
        return len(self._connections)
```

### Dashboard LiveView

```python
class DebugDashboardLiveView(LiveView):
    async def mount(self, socket):
        if is_connected(socket):
            await socket.subscribe("pyview_debug:updates")
            socket.schedule_info(InfoEvent("refresh"), seconds=2)

        socket.context = {
            "connections": self.registry.get_all(),
            "routes": self.app.registered_routes,
            "selected": None,
        }

    async def handle_info(self, event, socket):
        # Refresh connection data on timer tick or PubSub broadcast
        socket.context["connections"] = self.registry.get_all()

    async def handle_event(self, event, payload, socket):
        if event == "select_connection":
            topic = payload["topic"]
            info = self.registry.get(topic)
            live_socket = info.socket if info else None  # resolves weakref
            if info and live_socket:
                socket.context["selected"] = {
                    "info": info,
                    "context_inspection": inspect_context(live_socket.context),
                    "component_count": live_socket.components.component_count,
                }
```

### Context Introspection (All External)

We want **memory size**, not serialized size. JSON `len()` measures wire format which doesn't reflect actual memory footprint (e.g. a Python `int` is 28 bytes in memory but `"0"` in JSON). Use recursive `sys.getsizeof` with visited-object tracking to avoid double-counting shared references.

The inspector also reports **per-field sizes**, so developers can immediately see which field is bloating their context.

```python
import sys
from dataclasses import fields, is_dataclass

def inspect_context(context: Any) -> dict:
    """Safely inspect a LiveView context for debug display."""
    field_details = _inspect_fields(context)
    return {
        "total_size_bytes": deep_getsizeof(context),
        "type": type(context).__name__,
        "fields": field_details,
    }

def _inspect_fields(obj: Any) -> dict[str, dict]:
    """Return per-field size, type, and truncated repr."""
    SENSITIVE_PATTERNS = {"password", "token", "secret", "key", "credential"}
    items = _extract_fields(obj)
    result = {}
    for name, value in items:
        is_sensitive = any(p in name.lower() for p in SENSITIVE_PATTERNS)
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
    if is_dataclass(obj):
        return [(f.name, getattr(obj, f.name)) for f in fields(obj)]
    # Fallback: vars()
    try:
        return list(vars(obj).items())
    except TypeError:
        return []

def deep_getsizeof(obj: Any, seen: set[int] | None = None) -> int:
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

def _truncated_repr(value: Any, max_len: int = 120) -> str:
    """Safe repr with truncation for large values."""
    try:
        r = repr(value)
        if len(r) > max_len:
            return r[:max_len - 3] + "..."
        return r
    except Exception:
        return f"<{type(value).__name__}>"
```

---

## Accessing the App from a LiveView

One practical challenge: the dashboard LiveView needs access to the `ConnectionRegistry` and the app's `registered_routes`. Currently `ConnectedLiveViewSocket` doesn't have a back-reference to the `PyView` app.

### Options

**Option A: Factory pattern** — `enable_debug` creates a LiveView subclass with the registry baked in:

```python
def make_dashboard_view(registry, app):
    class _DashboardView(DebugDashboardLiveView):
        def __init__(self):
            super().__init__()
            self.registry = registry
            self.app = app
    return _DashboardView
```

This works today with no pyview changes. The `registry` and `app` references are captured in the closure.

**Option B: Module-level singleton** — Like `pub_sub_hub` already is in pyview. The registry lives at module scope, `enable_debug` sets it.

**Option C: Add app reference to socket** — Small pyview change, but general-purpose and useful beyond debugging.

**Recommendation**: **Option A** for now (zero additional pyview changes), with Option C as a nice-to-have later.

---

## Self-Exclusion

The dashboard should filter itself out of the connections table to avoid the "infinite mirrors" effect:

```python
def get_all(self, exclude_view_classes=None) -> list[ConnectionInfo]:
    exclude = exclude_view_classes or set()
    return [c for c in self._connections.values() if c.view_class not in exclude]
```

The dashboard calls `registry.get_all(exclude_view_classes={DebugDashboardLiveView})`.

---

## Chaining Trackers

If a user already has a `ConnectionTracker` (e.g. for their own monitoring), `enable_debug` should chain rather than replace:

```python
class ChainedTracker:
    """Forwards lifecycle events to multiple trackers."""

    def __init__(self, *trackers):
        self.trackers = trackers

    def on_connect(self, topic, socket, view_class, route, session):
        for t in self.trackers:
            t.on_connect(topic, socket, view_class, route, session)

    def on_disconnect(self, topic):
        for t in self.trackers:
            t.on_disconnect(topic)

    def on_event(self, topic, event_name, duration_seconds):
        for t in self.trackers:
            t.on_event(topic, event_name, duration_seconds)
```

---

## Security Considerations

The debug dashboard should **never** be enabled in production without auth:

```python
def enable_debug(app: PyView, path: str = "/debug", auth=None):
    """
    Args:
        auth: Optional authentication function. If provided, only authenticated
              requests can access the dashboard.
    """
```

The dashboard should also be careful about context inspection:
- Context values may contain sensitive data (passwords, tokens, PII)
- Default to "redact sensitive" mode — mask values for keys matching patterns like `password`, `token`, `secret`, `key`
- Don't expose full session data — just safe metadata (user ID, role, etc.)

---

## Implementation Plan

### Phase 1: PyView Core (One Small PR)

A single PR adding ~47 lines:

1. `ConnectionTracker` protocol definition (`pyview/connection_tracker.py`)
2. `connection_tracker` parameter on `PyView.__init__` and `LiveSocketHandler.__init__`
3. 4-5 call sites in `ws_handler.py` (`on_connect` after join, `on_disconnect` on close, `on_event` after event processing)
4. `registered_routes` property on `PyView`
5. Export `ConnectionTracker` from `pyview.__init__`

### Phase 2: External Package (`pyview-debug`)

Separate repo/package:

1. **Package scaffold** — `pyview-debug` with pyview as a dependency
2. **`DebugTracker`** — Implements `ConnectionTracker`, populates registry
3. **`ConnectionRegistry`** — Tracks active connections with metadata
4. **`enable_debug()`** — One-line setup entrypoint
5. **`DebugDashboardLiveView`** — Summary view with active connections table, uses `schedule_info` for polling
6. **Detail view** — Click-to-expand context inspector, event history
7. **`ChainedTracker`** — For composing with user's existing tracker

### Phase 3: Polish

8. Context inspector — safe serialization, sensitive data redaction, expandable tree UI
9. Filtering & search — filter by route, view class, event name
10. Time-series sparklines — mini charts for event rate, context size over time

---

## Open Questions

1. **~~Should the tracker receive the socket on `on_event` too?~~** *Resolved.*
   - No — the registry holds a `weakref` to the socket from `on_connect`. The socket can be dereferenced at any time while the connection is alive. No need to pass it again on every event.

2. **How much data should the registry retain after disconnect?**
   - Option: Keep last N disconnected sessions for a configurable TTL (useful for "what just happened?")
   - Option: Only track active connections (simpler)
   - Could start simple and add retention later

3. **Should we also add `on_render` to the tracker?**
   - Would enable tracking rendered output size per connection
   - But adds another call site in the hot path
   - Could be added later if needed

4. **Should `enable_debug` also add an HTTP/JSON endpoint?**
   - Useful for integration with external tools (Grafana, etc.)
   - But the primary UI should be the LiveView dashboard
   - Could be a Phase 3 addition

5. **Should the dashboard LiveView exclude itself from tracking entirely?**
   - Currently proposed: filter at display time
   - Alternative: have the tracker skip connections where `view_class` is in an exclude list
   - Display-time filtering is simpler and more flexible
