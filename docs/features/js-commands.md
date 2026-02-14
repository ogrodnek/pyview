---
title: JS Commands
---

# JS Commands

JS Commands let you update the DOM without a server round-trip. Show a modal, toggle a class, focus an input — all instantly on the client, with optional chaining to server events.

## Basic Usage

Import the `js` builder and use it directly in your t-string templates:

```python
from pyview import LiveView, LiveViewSocket, js

class MyLiveView(TemplateView, LiveView):
    def template(self, assigns, meta):
        return t"""
        <button phx-click='{js.show("#modal")}'>Open</button>
        <button phx-click='{js.hide("#modal")}'>Close</button>
        """
```

Each `js` method returns a command chain that serializes to JSON for the Phoenix.js client.

<details>
<summary>Ibis template syntax</summary>

In Ibis templates, commands that accept a positional selector (`show`, `hide`, `toggle`, `dispatch`) can be called directly. Commands with keyword-only arguments need the pipe syntax, since Ibis doesn't support keyword arguments:

```html
<button phx-click='{{ js.show("#modal") }}'>Open</button>
<button phx-click='{{ js | js.focus("#email") }}'>Focus</button>
```

Use pipe syntax for chaining: `{{ js.show("#modal") | js.push("opened") }}`.

</details>

## Command Chaining

Chain commands to run multiple operations on a single interaction:

```python
# Hide an element and notify the server
js.hide("#item", transition=("transition-all duration-200 ease-in", "opacity-100", "opacity-0")).push("delete", value={"id": 42})

# Push a server event and animate
js.push("increment").transition("bounce", to="#counter")
```

Each method returns a new `JsCommands` instance — chains are immutable, so you can safely build them up without side effects.

## Available Commands

### Visibility

| Command | Description |
|---------|-------------|
| `js.show(to)` | Show element(s) |
| `js.hide(to)` | Hide element(s) |
| `js.toggle(to)` | Toggle visibility |

All three accept optional `transition` and `time` parameters. `toggle` takes separate `in_transition` and `out_transition`.

`show` and `toggle` also accept a `display` parameter. Phoenix.js defaults to `display: block` when showing elements, so pass `display="flex"` (or `"grid"`, etc.) if your element needs a different display mode:

```python
js.show("#modal-container", display="flex")
```

### Classes

| Command | Description |
|---------|-------------|
| `js.add_class(names, to=)` | Add CSS class(es) |
| `js.remove_class(names, to=)` | Remove CSS class(es) |
| `js.toggle_class(names, to=)` | Toggle CSS class(es) |

`names` can be a string or a list of strings:

```python
js.add_class("active", to="#tab")
js.remove_class(["highlight", "pulse"], to="#alert")
```

### Attributes

| Command | Description |
|---------|-------------|
| `js.set_attribute(attr, to=)` | Set an attribute |
| `js.remove_attribute(attr, to=)` | Remove an attribute |
| `js.toggle_attribute(attr, to=)` | Toggle an attribute |

Attributes are specified as tuples:

```python
js.set_attribute(("disabled", "true"), to="#submit")
js.toggle_attribute(("aria-expanded", "true", "false"), to="#menu")
```

### Events

| Command | Description |
|---------|-------------|
| `js.push(event)` | Push an event to the server |
| `js.dispatch(event, to=)` | Dispatch a custom DOM event |

```python
js.push("save", value={"name": "PyView"}, target="#form")
js.dispatch("copy-to-clipboard", to="#text")
```

### Focus

| Command | Description |
|---------|-------------|
| `js.focus(to=)` | Focus an element |
| `js.focus_first(to=)` | Focus first focusable child |
| `js.push_focus(to=)` | Push focus onto the stack |
| `js.pop_focus()` | Restore previously pushed focus |

### Navigation

| Command | Description |
|---------|-------------|
| `js.navigate(href)` | LiveView navigation |
| `js.patch(href)` | Patch URL params |

### Other

| Command | Description |
|---------|-------------|
| `js.transition(transition, to=)` | Apply a CSS transition |
| `js.exec(attr, to=)` | Execute commands from an element's attribute |

## Transitions

Transitions animate visibility changes. Pass a 3-tuple of `(transition_classes, start_classes, end_classes)`:

```python
js.show("#modal", transition=(
    "transition-all duration-300 ease-out",
    "opacity-0 scale-95",
    "opacity-100 scale-100"
), time=300)
```

Phoenix.js orchestrates this as:
1. Apply transition + start classes
2. Next frame: swap start for end classes (CSS transition kicks in)
3. After `time` ms: remove everything

For simple cases, a single string works — it's applied as the transition class with no start/end:

```python
js.transition("bounce", to="#counter")
```

If you're using Tailwind, the 3-tuple form with utility classes gives the smoothest results.

## Complete Example

An optimistic delete pattern — hide immediately on the client, then notify the server:

```python
from string.templatelib import Template
from pyview import LiveView, LiveViewSocket, js
from pyview.events import AutoEventDispatch, event
from pyview.template.template_view import TemplateView


class ItemListLiveView(AutoEventDispatch, TemplateView, LiveView):
    async def mount(self, socket, _session):
        socket.context = {"items": [
            {"id": 1, "name": "Draft report"},
            {"id": 2, "name": "Review PR"},
            {"id": 3, "name": "Update docs"},
        ]}

    @event
    async def delete(self, id: int, socket):
        socket.context["items"] = [
            i for i in socket.context["items"] if i["id"] != id
        ]

    def template(self, assigns, meta) -> Template:
        items = assigns["items"]

        rows = [
            t"""
            <div id="item-{item['id']}" class="flex justify-between p-3 border-b">
                <span>{item['name']}</span>
                <button phx-click='{
                    js.hide(f"#item-{item['id']}", transition=(
                        "transition-all duration-200 ease-in",
                        "opacity-100",
                        "opacity-0"
                    )).push("delete", value={"id": item["id"]})
                }'>Delete</button>
            </div>
            """
            for item in items
        ]

        return t"""
        <div>
            <h2>Tasks</h2>
            {rows}
        </div>
        """
```

The user sees the item disappear instantly. The server processes the deletion and confirms on the next render.

## See Also

- [JavaScript Interop](./js-interop.md) — hooks, LiveSocket configuration, debugging
- [Event Handling](/core-concepts/event-handling) — server-side event patterns
