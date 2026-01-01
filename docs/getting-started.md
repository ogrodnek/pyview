# Getting Started

Let's get you up and running with a real-time web app in about five minutes.

PyView requires Python 3.11 or later. For t-string templates and LiveComponents, you'll need Python 3.14+.

## Quick Start with Cookiecutter

The fastest way to start a new project is with [cookiecutter](https://cookiecutter.readthedocs.io/):

```bash
cookiecutter gh:ogrodnek/pyview-cookiecutter
```

This gives you a complete project with:

- A working **counter example** to play with immediately
- [Poetry](https://python-poetry.org/) for dependency management
- [Just](https://just.systems/) command runner for common tasks
- Docker setup for deployment

> **Alternative:** Prefer [uv](https://docs.astral.sh/uv/) and want a nice component library? Try [pyview-cookiecutter-uv](https://github.com/ogrodnek/pyview-cookiecutter-uv), which uses uv for dependency management and includes [WebAwesome](https://www.webawesome.com/) components.

## Install and Run

```bash
cd myapp
poetry install
just
```

Visit `http://localhost:8000` and click the buttons. The count updates instantly without page reloads—that's LiveView in action.

Try adding `?c=10` to the URL to see how `handle_params` can initialize state from query parameters.

## What Just Happened?

1. **Initial page load**: The server renders HTML and sends it to the browser
2. **WebSocket connection**: The JavaScript client connects back to the server
3. **User clicks a button**: `phx-click="increment"` sends an event over WebSocket
4. **Server handles event**: The event handler updates the context
5. **Diff sent to client**: Only the changed `{{count}}` value is sent back
6. **DOM updates**: The page updates without a full reload

This is the LiveView pattern: server-rendered HTML with real-time updates over WebSocket.

## Project Structure

Here's what the cookiecutter generated:

```
myapp/
├── src/myapp/
│   ├── app.py              # Application entry point
│   └── views/
│       ├── __init__.py
│       └── count/
│           ├── __init__.py
│           ├── count.py    # LiveView class
│           └── count.html  # Template
├── tests/
├── pyproject.toml          # Poetry config
├── justfile                # Command runner
└── Dockerfile              # Production deployment
```

## Creating a New View

Let's add a temperature converter. The `just add-view` command scaffolds a new view:

```bash
just add-view temperature
```

This creates `src/myapp/views/temperature/` with starter files and automatically exports the view. Open `temperature.py` and update it:

```python
from pyview import LiveView, LiveViewSocket
from pyview.events import event, BaseEventHandler
from dataclasses import dataclass
from typing import Optional


@dataclass
class TempContext:
    celsius: float = 0
    fahrenheit: float = 32


class TemperatureLiveView(BaseEventHandler, LiveView[TempContext]):
    async def mount(self, socket: LiveViewSocket[TempContext], session):
        socket.context = TempContext()

    @event("update_celsius")
    async def handle_celsius(self, socket: LiveViewSocket[TempContext], value: Optional[float] = None):
        if value is None:
            return
        socket.context.celsius = value
        socket.context.fahrenheit = round(value * 9/5 + 32, 1)

    @event("update_fahrenheit")
    async def handle_fahrenheit(self, socket: LiveViewSocket[TempContext], value: Optional[float] = None):
        if value is None:
            return
        socket.context.fahrenheit = value
        socket.context.celsius = round((value - 32) * 5/9, 1)
```

Now update `temperature.html`:

```html
<div>
    <h1>Temperature Converter</h1>
    <div>
        <label>Celsius</label>
        <input type="number" value="{{celsius}}" phx-keyup="update_celsius" />
    </div>
    <div>
        <label>Fahrenheit</label>
        <input type="number" value="{{fahrenheit}}" phx-keyup="update_fahrenheit" />
    </div>
</div>
```

Register the route in `app.py`:

```python
from .views import CountLiveView
from .views.temperature import TemperatureLiveView

routes = [
    ("/", CountLiveView),
    ("/temperature", TemperatureLiveView),
]
```

Restart the server and visit `http://localhost:8000/temperature`. Type in either field and watch the other update in real-time.

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
