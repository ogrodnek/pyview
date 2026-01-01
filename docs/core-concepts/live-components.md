---
title: LiveComponents
---

# LiveComponents

LiveComponents are stateful, reusable UI components that manage their own state and handle their own events. They're useful when you need multiple independent instances of the same UI pattern, each with isolated state.

> **Note:** LiveComponents require [T-String Templates](../templating/t-string-templates.md) (Python 3.14+). They are not supported with Ibis HTML templates.

## When to Use LiveComponents

**Use LiveComponents when:**
- You need multiple instances of the same UI with independent state (e.g., several counters, toggles, or cards)
- A piece of UI has its own event handlers that shouldn't clutter the parent LiveView
- You want to encapsulate reusable stateful behavior

**Keep it in the parent LiveView when:**
- There's only one instance
- The state is simple and closely tied to the parent
- You don't need isolation between instances

## Defining a Component

Create a component by extending `LiveComponent` with a context type:

```python
from typing import TypedDict
from pyview.components import LiveComponent, ComponentSocket, ComponentMeta

class CounterContext(TypedDict):
    count: int

class Counter(LiveComponent[CounterContext]):
    async def mount(self, socket: ComponentSocket[CounterContext], assigns: dict):
        """Initialize component state from parent assigns."""
        socket.context = CounterContext(count=assigns.get("initial", 0))

    async def handle_event(self, event: str, payload: dict, socket: ComponentSocket[CounterContext]):
        """Handle events targeted at this component."""
        if event == "increment":
            socket.context["count"] += 1
        elif event == "decrement":
            socket.context["count"] -= 1

    def template(self, assigns: CounterContext, meta: ComponentMeta):
        """Render the component. Use meta.myself for event targeting."""
        count = assigns["count"]
        myself = meta.myself

        return t"""
            <div class="counter">
                <button phx-click="decrement" phx-target="{myself}">-</button>
                <span>{count}</span>
                <button phx-click="increment" phx-target="{myself}">+</button>
            </div>
        """
```

## Rendering Components

Use `live_component()` in your parent template to render a component:

```python
from pyview.template.live_view_template import live_component

class MyLiveView(LiveView[MyContext]):
    def template(self, assigns, meta):
        return t"""
            <div>
                <h1>My Counters</h1>
                {live_component(Counter, id="counter-1", initial=0)}
                {live_component(Counter, id="counter-2", initial=100)}
            </div>
        """
```

**Important:** Every component instance needs a unique `id`. PyView uses `(component_class, id)` to identify instances across re-renders.

## Component Lifecycle

| Method | When Called | Purpose |
|--------|-------------|---------|
| `mount(socket, assigns)` | First time component is rendered | Initialize state from parent assigns |
| `update(socket, assigns)` | Subsequent renders with new assigns | Handle changed props from parent |
| `handle_event(event, payload, socket)` | User interaction with `phx-target` | Process events targeted at this component |
| `template(assigns, meta)` | Every render | Return component HTML |

### mount()

Called once when the component first appears. Initialize your state here:

```python
async def mount(self, socket: ComponentSocket[CounterContext], assigns: dict):
    socket.context = CounterContext(
        count=assigns.get("initial", 0),
        label=assigns.get("label", "Counter")
    )
```

### update()

Called on subsequent renders when the parent passes new assigns. The default implementation does nothing—override it to handle prop changes:

```python
async def update(self, socket: ComponentSocket[CounterContext], assigns: dict):
    # Update label if parent changed it, but preserve count
    if "label" in assigns:
        socket.context["label"] = assigns["label"]
```

### handle_event()

Called when a user interacts with an element that has `phx-target` pointing to this component:

```python
async def handle_event(self, event: str, payload: dict, socket: ComponentSocket[CounterContext]):
    if event == "increment":
        socket.context["count"] += 1
    elif event == "reset":
        socket.context["count"] = 0
```

### template()

Called every render. Returns the component's HTML. The `meta` parameter provides `myself` for event targeting:

```python
def template(self, assigns: CounterContext, meta: ComponentMeta):
    return t"<button phx-click='increment' phx-target='{meta.myself}'>{assigns['count']}</button>"
```

## Event Targeting with meta.myself

Each component instance gets a unique Component ID (CID). Use `meta.myself` in `phx-target` to route events to the component instead of the parent LiveView:

```python
def template(self, assigns, meta):
    myself = meta.myself  # e.g., 1, 2, 3...

    return t"""
        <div>
            <!-- This event goes to the component's handle_event -->
            <button phx-click="increment" phx-target="{myself}">+</button>

            <!-- Without phx-target, this would go to the parent LiveView -->
            <button phx-click="save">Save</button>
        </div>
    """
```

## Parent-Child Communication

Components can send events to their parent LiveView using `send_parent()`:

```python
class Counter(LiveComponent[CounterContext]):
    async def handle_event(self, event, payload, socket):
        if event == "increment":
            socket.context["count"] += 1
        elif event == "notify_parent":
            # Send event to parent LiveView
            await socket.send_parent("counter_updated", {
                "count": socket.context["count"]
            })
```

The parent receives this in its normal `handle_event`:

```python
class ParentLiveView(LiveView[ParentContext]):
    async def handle_event(self, event, payload, socket):
        if event == "counter_updated":
            count = payload["count"]
            socket.context["messages"].append(f"Counter is now {count}")
```

## Slots

Slots allow parent templates to pass content into components, similar to React's children or Phoenix LiveView's slots. This enables flexible, composable components.

### Basic Usage

Use the `slots()` helper to pass content when rendering a component:

```python
from pyview.components import slots
from pyview.template.live_view_template import live_component

# Default slot only
live_component(Card, id="card-1", slots=slots(
    t"<p>This is the card body content</p>"
))

# Named slots
live_component(Card, id="card-2", slots=slots(
    t"<p>Body content</p>",
    header=t"<h2>Card Title</h2>",
    actions=t"<button>Save</button>"
))
```

### Accessing Slots in Components

Access slots via `meta.slots` in your component's template:

```python
class Card(LiveComponent):
    async def mount(self, socket, assigns):
        socket.context = {}

    def template(self, assigns, meta):
        # Use .get() for optional slots with fallbacks
        header = meta.slots.get("header", t"")
        body = meta.slots.get("default", t"<p>No content</p>")
        actions = meta.slots.get("actions", t"")

        return t"""
            <div class="card">
                <header>{header}</header>
                <main>{body}</main>
                <footer>{actions}</footer>
            </div>
        """
```

### Nested Components in Slots

Slots can contain live components, enabling nested interactivity:

```python
live_component(Card, id="card-with-counter", slots=slots(
    t"""
        <p>This card contains a counter:</p>
        {live_component(Counter, id="nested-counter", initial=10)}
    """,
    header=t"<h2>Interactive Card</h2>"
))
```

The nested Counter component is fully interactive with its own state and event handling.

### Slot Patterns

| Pattern | Example |
|---------|---------|
| Default slot only | `slots(t"<p>Content</p>")` |
| Named slots only | `slots(header=t"...", footer=t"...")` |
| Default + named | `slots(t"Body", header=t"Title")` |
| Optional with fallback | `meta.slots.get("header", t"Default")` |
| Check if provided | `if "header" in meta.slots:` |

## Multiple Component Instances

Each component instance has isolated state. Create multiple instances with unique IDs:

```python
def template(self, assigns, meta):
    # Using a list comprehension
    counters = [
        live_component(Counter, id=f"counter-{i}", initial=i * 10, label=f"Counter {i+1}")
        for i in range(assigns["counter_count"])
    ]

    return t"""
        <div class="counter-grid">
            {counters}
        </div>
    """
```

Clicking increment on one counter doesn't affect the others—each maintains its own state.

## Complete Example

Here's a full example with a parent LiveView managing multiple counter components:

```python
from typing import TypedDict
from pyview import LiveView, LiveViewSocket
from pyview.components import LiveComponent, ComponentSocket, ComponentMeta
from pyview.template.live_view_template import live_component
from pyview.template.template_view import TemplateView

# Component context
class CounterContext(TypedDict):
    count: int
    label: str

# Component definition
class Counter(LiveComponent[CounterContext]):
    async def mount(self, socket: ComponentSocket[CounterContext], assigns: dict):
        socket.context = CounterContext(
            count=assigns.get("initial", 0),
            label=assigns.get("label", "Counter")
        )

    async def handle_event(self, event, payload, socket):
        if event == "increment":
            socket.context["count"] += 1
        elif event == "decrement":
            socket.context["count"] -= 1
        elif event == "notify":
            await socket.send_parent("counter_changed", {
                "label": socket.context["label"],
                "count": socket.context["count"]
            })

    def template(self, assigns: CounterContext, meta: ComponentMeta):
        count = assigns["count"]
        label = assigns["label"]
        myself = meta.myself

        return t"""
            <div class="counter-card">
                <h3>{label}</h3>
                <div class="controls">
                    <button phx-click="decrement" phx-target="{myself}">-</button>
                    <span>{count}</span>
                    <button phx-click="increment" phx-target="{myself}">+</button>
                </div>
                <button phx-click="notify" phx-target="{myself}">Notify Parent</button>
            </div>
        """

# Parent LiveView context
class DemoContext(TypedDict):
    messages: list[str]

# Parent LiveView
class CounterDemo(TemplateView, LiveView[DemoContext]):
    async def mount(self, socket: LiveViewSocket[DemoContext], session):
        socket.context = DemoContext(messages=[])

    async def handle_event(self, event, payload, socket):
        if event == "counter_changed":
            label = payload["label"]
            count = payload["count"]
            socket.context["messages"].append(f"{label} is now {count}")
            # Keep only last 5 messages
            socket.context["messages"] = socket.context["messages"][-5:]

    def template(self, assigns: DemoContext, meta):
        messages = assigns["messages"]

        message_items = [
            t'<li>{msg}</li>' for msg in messages
        ] if messages else [t'<li>No messages yet</li>']

        return t"""
            <div>
                <h1>Counter Components Demo</h1>

                <div class="counters">
                    {live_component(Counter, id="a", label="Alpha", initial=0)}
                    {live_component(Counter, id="b", label="Beta", initial=50)}
                    {live_component(Counter, id="c", label="Gamma", initial=100)}
                </div>

                <div class="messages">
                    <h2>Messages from Components</h2>
                    <ul>{message_items}</ul>
                </div>
            </div>
        """
```

## Related Documentation

- [Event Handling](event-handling.md) - More on event handling patterns
- [LiveView Lifecycle](liveview-lifecycle.md) - Understanding the render lifecycle
- [T-String Templates](../templating/t-string-templates.md) - Template syntax reference
