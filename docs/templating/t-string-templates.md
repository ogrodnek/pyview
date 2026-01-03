---
title: T-String Templates
---

# T-String Templates

> **Requires Python 3.14+**

Template Strings let you write templates as Python code using the new template string literals from [PEP 750](https://peps.python.org/pep-0750/). This gives you full IDE support, type checking, and the ability to compose templates using regular Python functions.

> **Note:** For Python 3.11-3.13, see [HTML Templates](html-templates.md) instead.

## Basic Usage

Instead of creating `.html` files, extend `TemplateView` and define a `template()` method on your LiveView:

```python
from pyview import LiveView, LiveViewSocket
from pyview.template import TemplateView
from string.templatelib import Template
from pyview.meta import PyViewMeta
from pyview.events import AutoEventDispatch, event
from typing import TypedDict

class CountContext(TypedDict):
    count: int

class CounterLiveView(AutoEventDispatch, TemplateView, LiveView[CountContext]):
    async def mount(self, socket: LiveViewSocket[CountContext], session):
        socket.context = CountContext({"count": 0})

    @event
    async def increment(self, event, payload, socket):
      socket.context["count"] += 1

    @event
    async def decrement(self, event, payload, socket):
      socket.context["count"] -= 1

    def button(self, action, text: str) -> Template:
      return t"""<button phx-click={action}>{text}</button>"""

    def template(self, assigns: CountContext, meta: PyViewMeta) -> Template:
        count = assigns["count"]
        return t"""<div>
            <h1>Count: {count}</h1>
            {self.button(self.increment, "+")}
            {self.button(self.decrement, "-")}
        </div>"""
```

Key points:
- Inherit from both `TemplateView` and `LiveView`
- Implement `template(self, assigns, meta)` returning a `Template`
- Use `t"..."` or `t"""..."""` for template literals
- Use `{variable}` for interpolation (not `{{variable}}` like Ibis)

## Variable Interpolation

Variables from your context are interpolated using `{variable}` syntax:

```python
def template(self, assigns: CountContext, meta: PyViewMeta) -> Template:
    name = assigns["name"]
    email = assigns["email"]

    return t"""<div class="user-card">
        <h2>{name}</h2>
        <p>{email}</p>
    </div>"""
```

### Automatic HTML Escaping

All string interpolations are automatically HTML-escaped for security:

```python
# If name contains "<script>alert('xss')</script>"
# Output will be: "<p>Hello, &lt;script&gt;alert('xss')&lt;/script&gt;</p>"
return t"<p>Hello, {name}</p>"
```

To insert raw HTML, use an object with an `__html__()` method:

```python
from markupsafe import Markup

def template(self, assigns, meta):
    raw_html = Markup("<strong>Bold text</strong>")
    return t"<div>{raw_html}</div>"
```

## Composable Helper Methods

One of the biggest advantages of t-strings is composability. You can create helper methods that return template fragments:

```python
class CounterLiveView(TemplateView, LiveView[CountContext]):

    def button(self, label: str, event: str, style: str = "primary") -> Template:
        """Reusable button component."""
        if style == "primary":
            classes = "bg-blue-600 text-white hover:bg-blue-700"
        else:
            classes = "bg-gray-200 text-gray-800 hover:bg-gray-300"

        return t"""<button phx-click="{event}" class="{classes}">
            {label}
        </button>"""

    def template(self, assigns: CountContext, meta: PyViewMeta) -> Template:
        count = assigns["count"]
        return t"""<div>
            <h1>{count}</h1>
            <div class="buttons">
                {self.button("−", "decrement", "secondary")}
                {self.button("+", "increment", "primary")}
            </div>
        </div>"""
```

Helper methods can be reused across your view and even extracted to mixins for cross-view reuse.

## Using with AutoEventDispatch

T-strings work especially well with `AutoEventDispatch`, which lets you reference event handler methods directly in templates:

```python
from pyview import LiveView, LiveViewSocket
from pyview.events import AutoEventDispatch, event
from pyview.template import TemplateView

class CounterLiveView(AutoEventDispatch, TemplateView, LiveView[CountContext]):
    async def mount(self, socket, session):
        socket.context = CountContext({"count": 0})

    @event
    async def decrement(self, event, payload, socket):
        socket.context["count"] -= 1

    @event
    async def increment(self, event, payload, socket):
        socket.context["count"] += 1

    def button(self, label: str, event_ref, style: str = "primary") -> Template:
        classes = "px-4 py-2 rounded"
        return t"""<button phx-click="{event_ref}" class="{classes}">{label}</button>"""

    def template(self, assigns: CountContext, meta: PyViewMeta) -> Template:
        count = assigns["count"]
        return t"""<div>
            <h1>{count}</h1>
            {self.button("−", self.decrement)}
            {self.button("+", self.increment)}
        </div>"""
```

Notice `phx-click="{self.decrement}"` - the method reference automatically converts to the event name string. This eliminates the duplication of event name strings throughout your code.

See [Event Handling - AutoEventDispatch](../core-concepts/event-handling.md#autoeventdispatch) for more details.

## Lists and Loops

For rendering lists, use list comprehensions that produce template fragments:

```python
def template(self, assigns, meta) -> Template:
    users = assigns["users"]

    # List comprehension producing Template objects
    user_rows = [
        t"""<tr>
            <td>{user["name"]}</td>
            <td>{user["email"]}</td>
        </tr>"""
        for user in users
    ]

    return t"""<table>
        <thead>
            <tr><th>Name</th><th>Email</th></tr>
        </thead>
        <tbody>
            {user_rows}
        </tbody>
    </table>"""
```

You can also use helper methods for more complex list items:

```python
def user_row(self, user: dict) -> Template:
    return t"""<tr>
        <td>{user["name"]}</td>
        <td>{user["email"]}</td>
        <td>
            <button phx-click="edit" phx-value-id="{user["id"]}">Edit</button>
        </td>
    </tr>"""

def template(self, assigns, meta) -> Template:
    users = assigns["users"]
    return t"""<table>
        <tbody>
            {[self.user_row(u) for u in users]}
        </tbody>
    </table>"""
```


## Migration from HTML Templates

To migrate an existing view from HTML templates to t-strings:

1. Add `TemplateView` to your class inheritance:
   ```python
   # Before
   class MyView(LiveView[MyContext]):

   # After
   class MyView(TemplateView, LiveView[MyContext]):
   ```

2. Move your HTML to a `template()` method, converting syntax:
   - `{{variable}}` → `{variable}`
   - `{% if condition %}...{% endif %}` → Python conditionals
   - `{% for item in items %}...{% endfor %}` → List comprehensions
   - `{{ value | filter }}` → Python function calls

3. Delete the `.html` file (PyView will use `template()` instead)

4. Optionally add `AutoEventDispatch` for cleaner event binding

## Best Practices

### Extract Reusable Components

```python
# Create helper methods for repeated patterns
def card(self, title: str, content: Template) -> Template:
    return t"""<div class="card">
        <h3 class="card-title">{title}</h3>
        <div class="card-body">{content}</div>
    </div>"""

def template(self, assigns, meta) -> Template:
    return t"""<div>
        {self.card("Users", self.user_list(assigns["users"]))}
        {self.card("Stats", self.stats_panel(assigns["stats"]))}
    </div>"""
```

