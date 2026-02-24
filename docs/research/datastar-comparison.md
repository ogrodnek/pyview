# Datastar vs PyView: Research & Comparison

## Overview

[Datastar](https://data-star.dev/) is a lightweight (~11 KiB) hypermedia framework
that combines backend reactivity (like HTMX) and frontend reactivity (like Alpine.js)
into a single package driven by HTML `data-*` attributes. It was created out of
frustration with the plugin systems in HTMX and Alpine.js.

PyView is a Python implementation of the Phoenix LiveView model — server-rendered
HTML with stateful server-side views communicating over WebSockets.

Both frameworks share the philosophy that **the server should drive the UI** and that
developers shouldn't need to write JavaScript SPAs. But they differ significantly in
architecture, communication model, and state management.

---

## Architectural Comparison

| Aspect | PyView | Datastar |
|---|---|---|
| **Transport** | WebSockets (persistent, bidirectional) | SSE (Server-Sent Events, unidirectional) |
| **Server state** | Stateful — per-connection `socket.context` | Stateless — client sends all state with every request |
| **Client state** | Minimal (Phoenix.js handles DOM patching) | Signals — fine-grained reactive variables on the client |
| **DOM updates** | Tree-based diff of rendered template | DOM morphing (idiomorph) by default |
| **Backend languages** | Python only | Any language (Go, Python, PHP, Ruby, Rust, Java, .NET, etc.) |
| **Client size** | Phoenix LiveView JS client (~30+ KiB) | ~11 KiB total |
| **Build step** | Bundled JS client | None — single `<script>` tag |
| **Plugin system** | Hooks, Depends, decorators, context processors | First-class: attribute plugins, action plugins, watcher plugins |
| **Component model** | LiveView + LiveComponent (stateful, server-side) | None — flat signal namespace, server renders HTML |

---

## Communication Model

### PyView: WebSockets

PyView maintains a persistent WebSocket connection per client. The flow:

1. Initial HTTP request renders full HTML page
2. Browser connects via WebSocket (`/live/websocket`)
3. Server calls `mount()` — sets up stateful `socket.context`
4. User events (`phx-click`, `phx-submit`, etc.) send JSON over WebSocket
5. Server processes event, updates context, re-renders template
6. Server sends only the **diff** (changed template values) back over WebSocket
7. Phoenix.js client applies diff to DOM

**Implications:**
- Server maintains state per connection (memory cost)
- Bidirectional — server can push updates anytime
- Automatic reconnection with state recovery
- Connection-scoped pub/sub and scheduled events

### Datastar: Server-Sent Events (SSE)

Datastar uses SSE — a browser-native, HTTP-based, unidirectional streaming protocol:

1. Server renders initial HTML page with `data-*` attributes
2. User interactions trigger HTTP requests (GET/POST/etc.) to the server
3. Client automatically sends all **signals** (client state) as JSON with each request
4. Server responds with an SSE stream containing events:
   - `datastar-patch-elements` — HTML fragments to morph into the DOM
   - `datastar-patch-signals` — JSON updates to client-side signals
   - `datastar-execute-script` — arbitrary JS to run on client
5. A single response can contain multiple events updating different parts of the page

**Implications:**
- Server is stateless — no per-connection memory
- Simpler scaling (no sticky sessions or WebSocket infrastructure needed)
- SSE gets automatic reconnection and compression from the browser
- No bidirectional channel — each interaction is a new HTTP request
- Real-time push requires keeping an SSE connection open

---

## State Management

### PyView

State lives on the **server** in `socket.context`:

```python
class Counter(LiveView):
    async def mount(self, socket):
        socket.context = {"count": 0}

    async def handle_event(self, event, payload, socket):
        if event == "increment":
            socket.context["count"] += 1
```

- State is a Python dict/dataclass, fully server-side
- Survives across events within the same connection
- Lost on disconnect (unless persisted to session/database)
- Templates reference context values, diffs are computed from template tree

### Datastar

State lives on the **client** as reactive **signals**:

```html
<div data-signals="{count: 0}">
    <button data-on-click="@post('/increment')">+</button>
    <span data-text="$count"></span>
</div>
```

- Signals are fine-grained reactive variables
- `$count` references auto-subscribe to changes
- Two-way binding via `data-bind`
- Client sends all signals to server with each request
- Server can patch signals back via SSE events
- Local signals (prefixed `_`) stay client-only

**Key difference:** In PyView, the server owns state and the client is a thin
rendering layer. In Datastar, the client owns state (signals) and the server
processes requests statelessly. This is a fundamental architectural divide.

---

## Plugin/Extension Architecture

### PyView

PyView has several extension points, but no unified plugin system:

- **JS Hooks**: Client-side lifecycle hooks (`mounted`, `updated`, `destroyed`)
- **Depends**: Dependency injection via `Depends(callable)` in handler signatures
- **Event decorators**: `@event("name")` for organized event dispatching
- **Context processors**: Auto-inject template variables
- **Instrumentation**: Pluggable metrics/observability providers

### Datastar

Datastar was built with an "everything is a plugin" philosophy from day one:

- **Attribute plugins**: Map to `data-*` attributes (e.g., `data-bind`, `data-show`)
- **Action plugins**: Callable functions prefixed with `@` (e.g., `@get()`, `@post()`)
- **Watcher plugins**: Observe and respond to system changes

The plugin system has:
- Proper dependency DAG (directed acyclic graph)
- Type-safe TypeScript internals
- Custom bundling — include only the plugins you need
- Alias support to avoid conflicts with other libraries

**Takeaway:** Datastar's plugin system is more formalized and central to the
framework's identity. PyView's extension points are more ad-hoc, which is
typical of LiveView-style frameworks where the core is the server-side
view lifecycle.

---

## Multi-Language Support

### PyView
- Python only (3.11+, 3.14+ for t-string templates and LiveComponents)
- Tightly coupled to the Python async ecosystem (Starlette, asyncio)

### Datastar
- Backend-agnostic — official SDKs for Go, Python, PHP, TypeScript, Ruby,
  Rust, Java, Kotlin, .NET, Clojure
- Community SDKs for Elixir, Scala, Zig, Crystal, Gleam, Perl, Common Lisp,
  Racket, and more
- The protocol is simple enough that writing a new SDK is straightforward

This is possible because Datastar's server protocol is trivially simple: read
signals from request, write SSE events to response. No complex wire protocol,
no connection state management, no diff calculation on the server.

---

## Rendering

### PyView
- Server computes a template tree and calculates diffs against previous render
- Only changed dynamic values are sent over the wire
- Templates can be Ibis (Jinja2-like HTML files) or Python t-strings (3.14+)
- Supports streams for efficient large list handling
- Comprehension tracking for loop optimizations

### Datastar
- Server sends HTML fragments via SSE
- Client does DOM morphing (like idiomorph) to apply changes
- ID-based matching — elements need stable, unique IDs
- No server-side diff calculation — the client's morpher handles it
- Multiple regions can be updated in a single response (default behavior)
- ViewTransition API integration for animations

**Trade-off:** PyView's approach sends less data over the wire (just changed values),
but requires more server computation and memory to maintain the previous render tree.
Datastar sends more data (full HTML fragments) but has zero server-side overhead for
diffing or state.

---

## Ideas Worth Considering for PyView

Based on this research, here are concrete ideas from Datastar that could benefit PyView:

### 1. SSE as an Alternative Transport (High Value)

Datastar's use of SSE is compelling. PyView could potentially support **SSE as an
alternative or complementary transport** alongside WebSockets:

- **Use case:** Read-heavy dashboards, notification feeds, live data displays where
  the server pushes updates but client interactivity is limited
- **Benefit:** Simpler infrastructure (no WebSocket support needed), works through
  more proxies/CDNs, automatic reconnection
- **Implementation:** Add an SSE endpoint that streams template diffs as SSE events.
  Client-side JS would submit events via regular HTTP POST and receive updates via
  SSE stream
- **Caveat:** Would require rethinking the stateful socket model for SSE-based views,
  or maintaining a hybrid where state is serialized to the client

### 2. Fine-Grained Client-Side Signals (Medium Value)

PyView currently has minimal client-side state. Datastar's signals concept could
inspire a lightweight client-side reactivity layer:

- **Use case:** UI state that doesn't need to round-trip to the server (dropdown
  open/closed, tab selection, temporary form state)
- **Benefit:** Reduces unnecessary WebSocket traffic, improves perceived responsiveness
- **Implementation:** Could introduce a `data-local` or similar attribute system for
  client-only reactive state, processed by PyView's JS client. Similar to how
  Datastar's `_`-prefixed signals stay client-side
- **Caveat:** Adds client-side complexity; need to decide how much client intelligence
  to add before it becomes a different kind of framework

### 3. Formalized Plugin Architecture (Medium Value)

Datastar's "everything is a plugin" approach with typed interfaces and dependency
management is cleaner than PyView's current ad-hoc extension points:

- **Use case:** Third-party extensions, custom attributes, reusable behaviors
- **Implementation:** Define a `Plugin` protocol/ABC with lifecycle hooks, a plugin
  registry, and a dependency resolution system. Unify Hooks, Depends, event
  decorators, and context processors under a single plugin concept
- **Benefit:** Makes the extension surface more discoverable and composable

### 4. Multi-Region Updates as Default (Low-Medium Value)

Datastar can update multiple DOM regions in a single response by default. PyView
can do this via streams and components, but it's not as straightforward:

- **Use case:** Updating a notification badge and content area simultaneously
- **Implementation:** Allow `handle_event` to return updates for multiple DOM
  targets, not just the current view's template
- **Benefit:** Simplifies common patterns like "update content + update sidebar count"

### 5. Loading Indicators (Low Value, Easy Win)

Datastar's `data-indicator` automatically creates boolean signals tied to request
lifecycle (loading/done). PyView could add something similar:

- **Use case:** Show spinners during server processing
- **Implementation:** Emit `phx-loading` / `phx-loading-done` CSS classes or
  attributes on elements during event processing. Phoenix LiveView already does
  some of this — verify PyView's current support and fill gaps
- **Benefit:** Better UX with minimal developer effort

### 6. ViewTransition API Integration (Low Value, Easy Win)

Datastar supports the browser's ViewTransition API for animated DOM transitions:

- **Implementation:** When applying diffs, wrap DOM mutations in
  `document.startViewTransition()` calls, gated by a `phx-view-transition`
  attribute
- **Benefit:** Smooth visual transitions between states with zero JS from developers

### 7. Custom Bundles / Tree-Shaking (Low Priority)

Datastar's custom bundler lets you include only needed plugins. PyView's JS client
is fixed. Long-term, if PyView's client grows, consider making it modular.

---

## Ideas That Don't Fit PyView's Model

Some Datastar features are incompatible with PyView's architecture:

- **Stateless server model**: PyView's core value proposition IS stateful
  server-side views. Adopting a stateless model would make it a different framework
- **Client-side expression evaluation**: Datastar evaluates JS expressions in
  `data-*` attributes. PyView deliberately keeps logic server-side in Python
- **Backend-agnostic protocol**: PyView is inherently Python. Making it
  language-agnostic would require extracting the wire protocol, which is the
  Phoenix LiveView protocol (complex, stateful, not designed for simplicity)

---

## Summary

| Dimension | PyView Strength | Datastar Strength |
|---|---|---|
| **Developer model** | Pure Python, no JS needed | No build step, declarative HTML |
| **State management** | Server-side, type-safe Python | Fine-grained reactive signals |
| **Real-time** | Native via WebSocket, server push | SSE-based, simpler infrastructure |
| **Scaling** | Needs WebSocket infrastructure | Stateless, any HTTP server |
| **Efficiency** | Minimal wire traffic (diffs only) | Minimal server memory (no state) |
| **Extensibility** | Ad-hoc but functional | First-class plugin system |
| **Language support** | Python only | 10+ languages |
| **Component model** | Rich (LiveComponent) | None (flat signals) |
| **Maturity** | Alpha, small community | Growing rapidly, active community |

Both frameworks solve the "build interactive web apps without writing a JavaScript
SPA" problem, but they occupy different points in the design space. PyView gives you
a richer server-side programming model with stateful components, while Datastar gives
you a lighter-weight, more portable approach at the cost of less server-side structure.

The most actionable ideas for PyView are: exploring SSE as a complementary transport,
adding lightweight client-side signals for UI-only state, and formalizing the plugin
architecture.
