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

### 6. View Transition API Integration (Medium Value, Good DX Win)

See the dedicated [View Transition API](#view-transition-api) section below for
full details. In short: wrap DOM patches in `document.startViewTransition()`,
give developers a declarative opt-in, and let CSS handle the animations.

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

## View Transition API

The browser-native [View Transition API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API)
lets the browser animate between two visual states of the DOM. It works by:

1. **Capturing** rasterized snapshots of named elements (old state)
2. **Running** a DOM update callback (the actual mutation)
3. **Animating** from old snapshots to new state using CSS pseudo-elements

The default animation is a crossfade, but developers can customize per-element
animations using CSS `::view-transition-old(name)` and `::view-transition-new(name)`
pseudo-elements.

### Browser Support

Same-document transitions are **Baseline Newly Available** as of October 2025:

| Browser | Version |
|---|---|
| Chrome | 111+ (March 2023) |
| Edge | 111+ |
| Safari | 18+ |
| Firefox | 144+ (October 2025) |

Coverage is over 85% of browsers globally. The API degrades gracefully — if
unsupported, DOM updates execute normally without animation.

### How Datastar Does It

Datastar treats view transitions as a **first-class protocol feature**. The server
includes a boolean flag on any SSE event:

```
event: datastar-patch-elements
data: useViewTransition true
data: elements <div id="content">Updated content</div>
```

The client runtime automatically wraps the DOM morph in
`document.startViewTransition()` when this flag is set. Zero JavaScript required
from the developer. Every backend SDK exposes this as a simple option:

```go
// Go SDK
sse.PatchElements(datastar.WithUseViewTransitions(true), ...)
```

### How Phoenix LiveView Does It

LiveView added support in **v1.1.18 (November 2025)** via
[PR #4043](https://github.com/phoenixframework/phoenix_live_view/pull/4043).
It provides a low-level `onDocumentPatch` DOM callback — not a turnkey feature.
Developers must write ~30-50 lines of JavaScript glue code:

```javascript
// app.js — wire up view transitions manually
let liveSocket = new LiveSocket("/live", Socket, {
  dom: {
    onDocumentPatch(start) {
      if (shouldTransition) {
        document.startViewTransition({
          update: () => {
            resetTransitionState();
            start(); // apply the DOM patch
          },
          types: transitionTypes,
        });
      } else {
        start();
      }
    }
  }
});
```

On the server side, transitions are signaled via `push_event` with a new
`dispatch: :before` option (ensures the event fires before the DOM patch):

```elixir
socket
|> push_event("start-view-transition", %{type: "page"}, dispatch: :before)
```

Developers write CSS to customize the animations:

```css
::view-transition-old(root) {
  animation: 300ms ease-out slide-to-left;
}
::view-transition-new(root) {
  animation: 300ms ease-in slide-from-right;
}
```

### Comparison

| Aspect | Datastar | Phoenix LiveView |
|---|---|---|
| **API surface** | Boolean flag on SSE events | `onDocumentPatch` callback + manual JS |
| **Developer effort** | Zero JS | ~30-50 lines of JS boilerplate |
| **Per-event control** | Each SSE event opts in independently | Must `push_event` with `dispatch: :before` per handler |
| **Granularity** | On/off + CSS customization | Full control over types, per-element naming, timing |
| **SDK support** | Built into all backend SDKs | Elixir-only; JS part is manual |

### Why This Is a Natural Fit for PyView

DOM morphing and view transitions are **complementary by design**:

- **Morphdom is synchronous** — exactly what `startViewTransition()` wants. The
  API freezes rendering, runs the callback, then animates between snapshots.
- **Morphing preserves element identity** (matching by ID), so `view-transition-name`
  values on elements remain stable across patches — ideal for shared-element
  transitions (e.g., a card "flying" from a list to a detail view).
- **No architectural changes needed** — this is purely a client-side enhancement
  to the existing DOM patching.

### Implementation Approach for PyView

#### Constraint: PyView uses LiveView JS client v0.20.17 (pre-1.0)

PyView's bundled JS client is `phoenix_live_view` v0.20.17 — the last pre-1.0
release. The `onDocumentPatch` callback was added in v1.1.18 and is **not
available**. Upgrading to 1.x is non-trivial due to breaking changes in form
submission handling and other areas.

However, in 0.20.17 the `dom` config already supports `onPatchStart` and
`onPatchEnd` callbacks (declared at `LiveSocket` construction), though they are
**registered but never called** in the source. This is dead code that was later
activated as `onDocumentPatch` in 1.1.

This means we need an approach that works **without modifying or upgrading the
LiveView JS client**.

#### Option A: Monkey-patch `DOMPatch.prototype.perform` (Simplest, no fork)

The bundled app.js contains a `DOMPatch` class whose `perform()` method is the
single entry point for all morphdom operations. We can wrap it:

```javascript
// In a script loaded after app.js, or in a custom app.js build
//
// Wrap the DOMPatch perform method to add view transition support.
// This avoids modifying the vendored LiveView JS client.

(function() {
  if (!document.startViewTransition) return; // feature detection

  const liveSocket = window.liveSocket;
  if (!liveSocket) return;

  // The DOMPatch class is not exported, but every patch goes through
  // View.performPatch, which calls patch.perform(). We can intercept
  // at the View level instead.

  // Option: wrap liveSocket's internal view update path
  // This is fragile but works for 0.20.17 specifically.

  const origPerformPatch = Object.getPrototypeOf(
    Object.values(liveSocket.roots)[0] || {}
  )?.performPatch;

  if (origPerformPatch) {
    const ViewProto = Object.getPrototypeOf(
      Object.values(liveSocket.roots)[0]
    );
    ViewProto.performPatch = function(patch, pruneCids, isJoinPatch) {
      if (window.__pyviewTransitionsEnabled) {
        let result;
        document.startViewTransition(() => {
          result = origPerformPatch.call(this, patch, pruneCids, isJoinPatch);
        });
        return result;
      }
      return origPerformPatch.call(this, patch, pruneCids, isJoinPatch);
    };
  }
})();
```

**Pros:** Zero changes to vendored code, can be added as a separate script.
**Cons:** Fragile — depends on internal class structure of 0.20.17. Breaks if
the bundled JS is ever rebuilt from a different version.

#### Option B: Patch the bundled app.js directly (More reliable)

Since `pyview/static/assets/app.js` is a pre-built bundle checked into the repo,
we can surgically edit it. The `perform` method in the `DOMPatch` class (around
line 3924) is the insertion point:

```javascript
// Before (line 3924):
perform(isJoinPatch) {
  let { view, liveSocket: liveSocket2, container, html } = this;
  // ... rest of morphdom logic
}

// After:
perform(isJoinPatch) {
  if (document.startViewTransition && window.__pyviewTransitionsEnabled) {
    document.startViewTransition(() => this._performInner(isJoinPatch));
    return;
  }
  this._performInner(isJoinPatch);
}
_performInner(isJoinPatch) {
  let { view, liveSocket: liveSocket2, container, html } = this;
  // ... rest of original morphdom logic (unchanged)
}
```

**Pros:** Reliable, self-contained, easy to understand.
**Cons:** Modifies a vendored file — needs to be re-applied if the bundle is
ever regenerated. Should be documented clearly.

#### Option C: Activate the existing dead `onPatchStart`/`onPatchEnd` callbacks

The v0.20.17 client already declares these in `domCallbacks` but never calls
them. Adding two `triggerDOM` calls in `performPatch` would bring them to life:

```javascript
// In performPatch (around line 4983), add before patch.perform():
this.liveSocket.triggerDOM("onPatchStart", [this.el]);

// After patch.perform():
this.liveSocket.triggerDOM("onPatchEnd", [this.el]);
```

Then in `app.js` configuration:

```javascript
let liveSocket = new LiveSocket("/live", Socket, {
  dom: {
    onPatchStart(container) {
      // Could signal transition start
    },
    onPatchEnd(container) {
      // But view transitions need to WRAP the mutation, not fire before/after
    }
  }
});
```

**Problem:** `onPatchStart`/`onPatchEnd` fire *around* the patch, not *wrapping*
it. The View Transition API needs the DOM mutation to happen **inside** the
`startViewTransition()` callback. Before/after hooks aren't sufficient — this is
exactly why Phoenix added `onDocumentPatch(startCallback)` in 1.1, which wraps
rather than brackets the mutation.

**Verdict:** Option C doesn't work for view transitions specifically, though
activating these callbacks could be useful for other purposes.

#### Recommended approach

**Option B** (patching the bundled app.js) is the most practical:

1. It's a small, surgical change (~10 lines)
2. The bundle is already a vendored artifact, not regenerated from source
3. It's easy to document with a comment explaining the modification
4. Users opt in via `window.__pyviewTransitionsEnabled = true` or a
   `<meta name="pyview-transitions" content="true">` tag
5. Feature detection means zero impact on browsers without support

The server-side opt-in and CSS customization story remains the same regardless
of which client-side approach is chosen:

**Server-side: declarative opt-in**

```python
class ItemDetail(LiveView):
    # Enable view transitions for this entire view
    view_transitions = True
```

Or per-element in templates:

```html
<div id="card-{{ item.id }}"
     style="view-transition-name: card-{{ item.id }}; view-transition-class: card;">
  {{ item.name }}
</div>
```

**CSS: developers customize animations**

```css
/* Default crossfade happens automatically. Customize as needed: */
::view-transition-group(*.card) {
  animation-duration: 300ms;
}

::view-transition-old(root) {
  animation: 200ms ease-out fade-out;
}
::view-transition-new(root) {
  animation: 300ms ease-in fade-in;
}
```

### Edge Cases to Handle

- **Rapid updates**: If a new WebSocket diff arrives while a transition is
  animating, either skip the running animation (`transition.skipTransition()`)
  or start a fresh transition. Both htmx and Datastar let the new update
  proceed immediately.
- **view-transition-name uniqueness**: Every visible element with a
  `view-transition-name` must have a unique value. In server-rendered lists,
  use `view-transition-name: item-${id}`. Duplicate names cause the transition
  to abort entirely.
- **Elements entering/leaving**: When an element only exists in the old or new
  state, use CSS `:only-child` on the pseudo-elements to target enter/exit
  animations specifically.
- **`startViewTransition` is async**: The callback runs synchronously but the
  animation is async. In 0.20.17, `performPatch` returns `phxChildrenAdded`
  (a boolean) — the return value must still be captured correctly. Option B
  handles this naturally since the inner method runs synchronously inside
  the callback.

### Recommendation

Start with Option B: a surgical patch to the bundled `app.js` that wraps
`DOMPatch.perform()` in `startViewTransition()` with feature detection. Pair it
with a `<meta>` tag or `view_transitions = True` config for opt-in. This gives
developers animated transitions for free (the default crossfade) and they can
progressively add `view-transition-name` and custom CSS to specific elements
for richer animations. No server-side protocol changes needed — this is entirely
a client-side enhancement that works on the current v0.20.17 JS client.

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
