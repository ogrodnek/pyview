---
title: Single-File Apps
---

# Single-File PyView Apps

PyView supports single-file applications using [PEP 723](https://peps.python.org/pep-0723/) inline script metadata. Combined with [uv](https://docs.astral.sh/uv/), you can create and run a complete LiveView app in a single file with no setup.

## Quick Start

Create a file called `counter.py`:

```python
#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "pyview-web",
#   "uvicorn",
# ]
# ///

from typing import TypedDict
from pyview import LiveView, playground
from pyview.template.template_view import TemplateView
from pyview.events import AutoEventDispatch, event
from string.templatelib import Template
import uvicorn


class CountContext(TypedDict):
    count: int


class CounterView(AutoEventDispatch, TemplateView, LiveView[CountContext]):
    async def mount(self, socket, session):
        socket.context = {"count": 0}

    @event
    async def increment(self, event, payload, socket):
        socket.context["count"] += 1

    @event
    async def decrement(self, event, payload, socket):
        socket.context["count"] -= 1

    def button(self, ref, text, color: str = "blue") -> Template:
        return t"""
        <button phx-click={ref}
                class="bg-{color}-500 px-4 py-2 text-white rounded">{text}</button>
        """

    def template(self, assigns: CountContext, meta) -> Template:
        return t"""
        <div class="flex items-center justify-center min-h-screen">
            <div class="flex flex-col items-center gap-4">
                <h1 class="text-2xl">Count: {assigns['count']}</h1>
                <div class="flex gap-2">
                    {self.button(self.decrement, "-", "red")}
                    {self.button(self.increment, "+", "blue")}
                </div>
            </div>
        </div>
        """


if __name__ == "__main__":
    app = (
        playground()
        .with_live_view(CounterView)
        .with_title("Counter")
        .with_css('<script src="https://cdn.tailwindcss.com"></script>')
        .build()
    )

    uvicorn.run(app, host="0.0.0.0", port=8000)
```

Run it:

```bash
uv run counter.py
```

That's it! No virtual environment setup, no `requirements.txt`, no project scaffolding.

## Playground Builder

The `playground()` builder provides a simple API for configuring your app:

```python
from pyview import playground
from pyview.playground import Favicon

app = (
    playground()
    .with_live_view(MyView)                    # Add a LiveView (required)
    .with_live_view(OtherView, path="/other")  # Add more views at different paths
    .with_title("My App")                      # Set page title (also generates favicon)
    .with_css('<link rel="stylesheet" href="...">')  # Add CSS (can call multiple times)
    .with_favicon(Favicon(bg_color="#22c55e")) # Customize favicon colors
    .build()
)
```

### Auto-Generated Favicon

When you set a title, the playground automatically generates an SVG favicon from the title's initials. Customize it with:

```python
from pyview.playground import Favicon

# Custom colors
.with_favicon(Favicon(bg_color="#22c55e", text_color="#ffffff"))

# Disable favicon
.no_favicon()
```

## Auto-Reload for Development

For development with auto-reload, expose the app at module level and use uvicorn's `--reload` flag:

```python
# At module level (outside if __name__ == "__main__")
app = playground().with_live_view(CounterView).with_title("Counter").build()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("counter:app", host="0.0.0.0", port=8000, reload=True)
```

Or run directly with uvicorn:

```bash
uv run uvicorn counter:app --reload
```
