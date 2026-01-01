# Getting Started

This guide walks you through installing PyView and creating your first LiveView application.

PyView requires Python 3.11 or later. For t-string templates and LiveComponents, you'll need Python 3.14+.

## Quick Start with Cookiecutter

The fastest way to start a new project:

```bash
cookiecutter gh:ogrodnek/pyview-cookiecutter
```

## Project Structure

A typical PyView project looks like this:

```
my_app/
├── app.py                 # Application entry point
├── views/
│   ├── counter/__init__.py
│   ├── counter.py         # LiveView class
│   ├── counter.html       # Template (or use t-strings in .py)
│   └── counter.css        # Optional, auto-included
└── static/                # Static files
```

## Your First LiveView

Let's build a simple counter. Create `views/counter.py`:

```python
from pyview import LiveView, LiveViewSocket
from typing import TypedDict


class CountContext(TypedDict):
    count: int


class CounterLiveView(LiveView[CountContext]):
    async def mount(self, socket: LiveViewSocket[CountContext], session):
        socket.context = {"count": 0}

    async def handle_event(self, event, payload, socket: LiveViewSocket[CountContext]):
        if event == "increment":
            socket.context["count"] += 1
        elif event == "decrement":
            socket.context["count"] -= 1
```

Create the template `views/counter.html`:

```html
<div>
    <h1>Count: {{count}}</h1>
    <button phx-click="decrement">-</button>
    <button phx-click="increment">+</button>
</div>
```

## Setting Up the Application

Create `app.py`:

```python
from pyview import PyView
from views.counter import CounterLiveView

app = PyView()
app.add_live_view("/", CounterLiveView)
```

## Running the Dev Server

```bash
uvicorn app:app --reload
```

Visit `http://localhost:8000` and click the buttons. The count updates instantly without page reloads—that's LiveView in action.

## What Just Happened?

1. **Initial page load**: The server renders HTML and sends it to the browser
2. **WebSocket connection**: The JavaScript client connects back to the server
3. **User clicks a button**: `phx-click="increment"` sends an event over WebSocket
4. **Server handles event**: `handle_event()` updates the context
5. **Diff sent to client**: Only the changed `{{count}}` value is sent back
6. **DOM updates**: The page updates without a full reload

This is the LiveView pattern: server-rendered HTML with real-time updates over WebSocket.

## Single-File Apps

For quick experiments, you can put everything in one file using the playground builder:

```python
#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.14"
# dependencies = ["pyview-web", "uvicorn"]
# ///

from pyview import LiveView, playground
from pyview.template import TemplateView
from typing import TypedDict
import uvicorn


class CountContext(TypedDict):
    count: int


class Counter(TemplateView, LiveView[CountContext]):
    async def mount(self, socket, session):
        socket.context = {"count": 0}

    async def handle_event(self, event, payload, socket):
        if event == "increment":
            socket.context["count"] += 1

    def template(self, assigns, meta):
        return t"""<div>
            <h1>Count: {assigns['count']}</h1>
            <button phx-click="increment">+</button>
        </div>"""


app = playground().with_live_view(Counter).with_title("Counter").build()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

Run it with `uv run counter.py`—no virtual environment setup needed.

See [Single-File Apps](single-file-apps.md) for more on this approach.

## Environment Variables

For production, set a secret key for session security:

```bash
export PYVIEW_SECRET="your-secret-key-here"
```

Generate one with:

```bash
openssl rand -base64 32
```

## Next Steps

- [LiveView Lifecycle](core-concepts/liveview-lifecycle.md) — Understand mount, handle_event, and handle_params
- [Socket and Context](core-concepts/socket-and-context.md) — Managing state and real-time features
- [Event Handling](core-concepts/event-handling.md) — Buttons, forms, and user interactions
- [Templating](templating/overview.md) — Choose between HTML templates and t-strings
- [Routing](core-concepts/routing.md) — URL patterns and path parameters
