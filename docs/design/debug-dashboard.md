# PyView Debug Dashboard — Design Document

## Overview

A debug dashboard that gives pyview developers real-time visibility into their running application: active LiveViews, routes, context sizes, event activity, and the ability to drill into individual LiveView state.

**Key constraint**: The dashboard itself should be a **separate package** (e.g. `pyview-debug`) that users install alongside pyview and wire in with minimal configuration. This keeps the core framework lean while making the debug tooling easy to adopt.

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

## Architecture

```
┌─────────────────────────────────────────────┐
│              User's PyView App              │
│                                             │
│  app = PyView()                             │
│  app.add_live_view("/posts", PostsView)     │
│  app.add_live_view("/chat", ChatView)       │
│                                             │
│  # One-line debug dashboard setup:          │
│  from pyview_debug import enable_debug      │
│  enable_debug(app)                          │
│     │                                       │
│     ├── Registers DebugDashboardLiveView    │
│     │   at /debug (configurable)            │
│     ├── Installs DebugInstrumentation       │
│     │   (wraps existing instrumentation)    │
│     └── Registers ConnectionRegistry        │
│         hooks on LiveSocketHandler          │
└─────────────────────────────────────────────┘
```

### Components of the External Package (`pyview-debug`)

1. **`DebugDashboardLiveView`** — A LiveView that renders the dashboard UI. Uses `schedule_info` to poll the registry and update the table in real-time.

2. **`ConnectionRegistry`** — Tracks active connections with metadata. Populated via hooks on `LiveSocketHandler`.

3. **`DebugInstrumentation`** — An `InstrumentationProvider` wrapper that intercepts metric calls to capture per-connection data (event counts, durations, etc.), while delegating to the user's existing instrumentation provider.

---

## What PyView Needs to Expose

The current pyview codebase has good instrumentation abstractions but is missing the **introspection primitives** needed for a debug dashboard. The existing instrumentation is metric-oriented (counters, histograms) — great for aggregate monitoring but insufficient for per-connection visibility.

### Gap Analysis

| Need | Current State | Gap |
|------|--------------|-----|
| Enumerate active connections | `self.sessions` is just an `int` counter | No connection registry |
| Per-connection metadata | Not tracked | Need connected_at, route, view class |
| Access socket context | Only available inside lifecycle handlers | Need external read access |
| Event history per connection | Countered in aggregate only | Need per-connection event log |
| Lifecycle hooks (connect/disconnect/event) | Instrumentation is metric-only | Need callbacks with connection context |
| Registered routes | `view_lookup.routes` exists but is private/internal | Need public accessor |

### Proposed Additions to PyView Core

#### 1. Connection Registry (New)

A lightweight registry that tracks active `ConnectedLiveViewSocket` instances. This is the most critical addition.

```python
# pyview/connection_registry.py

@dataclass
class ConnectionInfo:
    topic: str
    view_class: type[LiveView]
    view_name: str
    route: str
    connected_at: datetime
    last_seen: datetime
    last_action: Optional[str]
    event_count: int
    socket: ConnectedLiveViewSocket  # weak reference in practice

class ConnectionRegistry:
    """Tracks active LiveView connections for introspection."""

    def __init__(self):
        self._connections: dict[str, ConnectionInfo] = {}  # keyed by topic

    def register(self, topic: str, socket: ConnectedLiveViewSocket,
                 view_class: type, route: str) -> None: ...

    def unregister(self, topic: str) -> None: ...

    def record_event(self, topic: str, event_name: str) -> None: ...

    def get_all(self) -> list[ConnectionInfo]: ...

    def get(self, topic: str) -> Optional[ConnectionInfo]: ...

    @property
    def active_count(self) -> int: ...
```

**Integration point**: `LiveSocketHandler` calls `register`/`unregister`/`record_event` at the appropriate lifecycle moments. This is low-overhead — just dict insertions.

#### 2. Lifecycle Hooks (New)

A simple callback system so external code can react to lifecycle events with full context. This is more flexible than the metric-based instrumentation.

```python
# pyview/hooks.py

@dataclass
class ConnectEvent:
    topic: str
    socket: ConnectedLiveViewSocket
    view_class: type[LiveView]
    route: str
    session: dict

@dataclass
class DisconnectEvent:
    topic: str
    view_class: type[LiveView]
    route: str

@dataclass
class EventProcessed:
    topic: str
    event_name: str
    view_class: type[LiveView]
    duration_seconds: float
    socket: ConnectedLiveViewSocket

class HookRegistry:
    """Registry for lifecycle hook callbacks."""

    def on_connect(self, callback: Callable[[ConnectEvent], None]) -> None: ...
    def on_disconnect(self, callback: Callable[[DisconnectEvent], None]) -> None: ...
    def on_event(self, callback: Callable[[EventProcessed], None]) -> None: ...
```

**Integration point**: `PyView` gets a `.hooks` attribute. `LiveSocketHandler` fires hooks at the right moments. The external debug package registers its callbacks during `enable_debug(app)`.

#### 3. Public Accessors for Existing State

Expose what's already there but currently internal:

```python
# On PyView class:
@property
def registered_routes(self) -> list[tuple[str, type[LiveView]]]:
    """Return list of (path, view_class) for all registered LiveViews."""
    return [(fmt, cls) for fmt, _, _, cls in self.view_lookup.routes]

@property
def connection_registry(self) -> ConnectionRegistry:
    """Access the connection registry for introspection."""
    return self.live_handler.registry

@property
def hooks(self) -> HookRegistry:
    """Access lifecycle hooks."""
    return self._hooks
```

---

## Design Decision: Hooks vs. Registry vs. Both

There's a question of whether we need both the ConnectionRegistry and the Hooks system, or just one.

### Option A: Registry Only
The registry tracks everything. The dashboard polls it. Simple, but no way to react to events in real-time (only polling).

### Option B: Hooks Only
External code registers callbacks and maintains its own state. Maximum flexibility, but every consumer rebuilds the same connection-tracking logic.

### Option C: Registry + Hooks (Recommended)
The registry is built into pyview as a thin, always-on data structure (very low overhead since it's just a dict keyed by topic). Hooks are an opt-in extension point for when you need real-time reactions. The debug dashboard uses the registry for the table data and hooks for live-updating the dashboard view via PubSub.

**Recommendation: Option C.** The registry is ~50 lines of code with negligible overhead. The hooks layer is another ~50 lines. Both are useful independently, and together they cover all the dashboard's needs cleanly.

---

## How the External Package Works

### Installation & Setup

```python
# pip install pyview-debug

from pyview import PyView
from pyview_debug import enable_debug

app = PyView()
app.add_live_view("/posts", PostsView)

# Add debug dashboard at /debug (or custom path)
enable_debug(app, path="/debug")
```

### What `enable_debug()` Does

```python
def enable_debug(app: PyView, path: str = "/debug"):
    # 1. Register the dashboard LiveView
    app.add_live_view(path, DebugDashboardLiveView)

    # 2. Register hooks that broadcast updates to the dashboard
    app.hooks.on_connect(lambda e: _broadcast_update(app, "connect", e))
    app.hooks.on_disconnect(lambda e: _broadcast_update(app, "disconnect", e))
    app.hooks.on_event(lambda e: _broadcast_update(app, "event", e))
```

### Dashboard LiveView Implementation

```python
class DebugDashboardLiveView(LiveView):
    async def mount(self, socket):
        if is_connected(socket):
            # Subscribe to debug update broadcasts
            await socket.subscribe("pyview_debug:updates")
            # Also poll periodically for context size updates
            socket.schedule_info(InfoEvent("refresh"), seconds=2)

        connections = socket.app.connection_registry.get_all()
        socket.context = {
            "connections": connections,
            "routes": socket.app.registered_routes,
            "selected": None,
        }

    async def handle_info(self, event, socket):
        if event == "refresh" or event.topic == "pyview_debug:updates":
            socket.context["connections"] = socket.app.connection_registry.get_all()

    async def handle_event(self, event, payload, socket):
        if event == "select_connection":
            topic = payload["topic"]
            info = socket.app.connection_registry.get(topic)
            socket.context["selected"] = info
```

### Context Introspection

For the "drill into state" feature, we need a way to safely serialize/inspect a LiveView's context. This should be in the external package, not pyview core:

```python
def inspect_context(context: Any) -> dict:
    """Safely inspect a LiveView context for debug display."""
    return {
        "size_bytes": _estimate_size(context),
        "type": type(context).__name__,
        "fields": _safe_repr_fields(context),
    }

def _estimate_size(obj: Any) -> int:
    """Estimate memory size of an object (best-effort)."""
    # Use sys.getsizeof with recursive traversal for dicts/dataclasses
    ...

def _safe_repr_fields(obj: Any) -> dict:
    """Create a safe repr of an object's fields for display."""
    # Handle dataclasses, dicts, pydantic models, etc.
    # Truncate large values, redact sensitive-looking keys
    ...
```

---

## Context Size Estimation

One of the key dashboard features is showing context size. This is inherently approximate but useful. Approaches:

1. **`sys.getsizeof` with recursion** — Works for dicts and simple objects. Misses shared references but good enough for a dashboard.
2. **`pickle.dumps` length** — More accurate for total serialized size, but slower and may fail on unpicklable objects.
3. **JSON serialization length** — If the context is JSON-serializable (common for LiveView contexts), `len(json.dumps(context))` is fast and meaningful.

**Recommendation**: Try JSON first (since LiveView contexts are typically JSON-friendly for rendering), fall back to recursive `getsizeof`.

---

## View Size Tracking

The rendered output size is already implicitly available — `ws_handler.py` already calls `json.dumps(resp)` and records `message_size`. We could additionally capture the rendered dict size per-connection in the registry by hooking into the render path.

The simplest approach: after `_render(socket)` returns, estimate the size of the rendered dict and store it on the `ConnectionInfo`.

---

## Security Considerations

The debug dashboard should **never** be enabled in production by default:

```python
def enable_debug(app: PyView, path: str = "/debug", auth: Optional[Callable] = None):
    """
    Enable the debug dashboard.

    Args:
        auth: Optional authentication function. If provided, only authenticated
              requests can access the dashboard. Recommended for non-local deployments.
    """
    if auth:
        # Wrap the dashboard view with auth
        ...
```

The dashboard should also be careful about what it exposes:
- Context values may contain sensitive data (passwords, tokens, PII)
- Offer a "redact sensitive" mode that masks values for keys matching patterns like `password`, `token`, `secret`, `key`
- Don't expose the full session — just metadata

---

## Implementation Plan

### Phase 1: PyView Core Additions (Small, Focused PRs)

1. **Connection Registry** — Add `ConnectionRegistry` and integrate it into `LiveSocketHandler`. Register on connect, unregister on disconnect, record events.

2. **Lifecycle Hooks** — Add `HookRegistry` to `PyView`. Wire up `on_connect`, `on_disconnect`, `on_event` in `LiveSocketHandler`.

3. **Public Accessors** — Add `registered_routes` property to `PyView`. Expose `connection_registry` accessor.

### Phase 2: External Package (`pyview-debug`)

4. **Package scaffold** — Set up `pyview-debug` as a separate package with pyview as a dependency.

5. **`enable_debug()` entrypoint** — The one-liner that wires everything together.

6. **Dashboard LiveView** — Summary view with active connections table. Uses `schedule_info` for polling + PubSub for real-time updates.

7. **Detail View** — Click-to-expand context inspector, event history, component tree.

### Phase 3: Polish

8. **Context Inspector** — Safe serialization, sensitive data redaction, expandable tree UI.

9. **Filtering & Search** — Filter by route, view class, event name.

10. **Time-Series Sparklines** — Mini charts for event rate, context size over time per connection.

---

## Open Questions

1. **How much data should the registry retain after disconnect?**
   - Option: Keep last N disconnected sessions for a configurable TTL (useful for debugging issues that just happened)
   - Option: Only track active connections (simpler, less memory)

2. **Should the dashboard use its own WebSocket or piggyback on the LiveView protocol?**
   - Recommendation: It's a LiveView itself, so it uses the standard LiveView WebSocket. This dogfoods the framework.

3. **Should we consider a non-LiveView HTTP/JSON API endpoint for the debug data?**
   - Could be useful for integration with external tools (Grafana, etc.)
   - But the primary UI should be the LiveView dashboard

4. **Access to `app` from within a LiveView — how?**
   - Currently `ConnectedLiveViewSocket` doesn't have a reference back to the `PyView` app
   - Options: (a) Pass `app` reference through to socket, (b) Use a module-level singleton registry, (c) Use Starlette's `request.app` pattern
   - Recommendation: The `ConnectionRegistry` could be a module-level singleton (like `pub_sub_hub` already is) or passed via the socket's instrumentation provider

5. **Should the dashboard LiveView exclude itself from the registry?**
   - Probably yes — you don't want the debug dashboard showing up as an active LiveView in its own table (infinite mirrors)
   - Could filter by checking `view_class != DebugDashboardLiveView`
