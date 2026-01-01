---
title: Routing
---

# Routing

PyView uses Starlette's routing under the hood—no need to learn a new system if you're already familiar with it. You get flexible URL patterns with automatic type conversion for path parameters.

## Basic Route Registration

Register LiveViews with `add_live_view()`:

```python
from pyview import PyView
from views.counter import CounterLiveView
from views.users import UserListLiveView, UserDetailLiveView

app = PyView()

app.add_live_view("/", CounterLiveView)
app.add_live_view("/users", UserListLiveView)
app.add_live_view("/users/{id}", UserDetailLiveView)
```

## Path Parameters

Use curly braces to capture URL segments. Starlette's converters handle type conversion automatically:

```python
# Matches /users/123, /users/456, etc.
app.add_live_view("/users/{id:int}", UserDetailLiveView)

# Matches /posts/hello-world, /posts/my-first-post, etc.
app.add_live_view("/posts/{slug:str}", PostLiveView)

# Matches /files/documents/report.pdf (captures full path)
app.add_live_view("/files/{path:path}", FileLiveView)
```

## Accessing Path Parameters

Path parameters are automatically merged with query parameters and passed to `handle_params()`. Use typed parameters for clean access:

```python
class UserDetailLiveView(LiveView[UserContext]):
    async def mount(self, socket: LiveViewSocket[UserContext], session):
        socket.context = {"user": None}

    async def handle_params(self, socket: LiveViewSocket[UserContext], id: int):
        # 'id' is already converted to int from the URL /users/123
        user = await load_user(id)
        socket.context["user"] = user
```

Path parameters take precedence over query parameters if there's a name conflict.

### Multiple Path Parameters

```python
# Route: /orgs/{org}/projects/{project_id}
app.add_live_view("/orgs/{org}/projects/{project_id}", ProjectLiveView)

class ProjectLiveView(LiveView[ProjectContext]):
    async def handle_params(self, socket, org: str, project_id: int):
        project = await load_project(org, project_id)
        socket.context["project"] = project
```

## Route Priority

When multiple routes could match a URL, static routes take precedence over parameterized routes:

```python
app.add_live_view("/users/new", NewUserLiveView)      # Static - matched first
app.add_live_view("/users/{id}", UserDetailLiveView)  # Parameterized
```

A request to `/users/new` goes to `NewUserLiveView`, while `/users/123` goes to `UserDetailLiveView`.

## Trailing Slashes

PyView handles trailing slashes gracefully. Both `/users` and `/users/` will match a route registered as `/users`.

## Combining with Query Parameters

Path and query parameters work together seamlessly:

```python
# URL: /users/123?tab=settings&mode=edit
# Route: /users/{id:int}

class UserDetailLiveView(LiveView[UserContext]):
    async def handle_params(self, socket, id: int, tab: str = "profile", mode: str = "view"):
        # id = 123 (from path)
        # tab = "settings" (from query)
        # mode = "edit" (from query)
        socket.context.update({
            "user": await load_user(id),
            "active_tab": tab,
            "edit_mode": mode == "edit"
        })
```

## Static Files

Mount static files separately using Starlette's `StaticFiles`:

```python
from starlette.staticfiles import StaticFiles

app = PyView()

# Serve files from ./static at /static URL
app.mount("/static", StaticFiles(directory="static"), name="static")

# Or from package resources
app.mount(
    "/static",
    StaticFiles(packages=[("myapp", "static")]),
    name="static"
)
```

## Route Organization

For larger applications, organize routes in a list:

```python
from pyview import PyView
from views import (
    HomeLiveView,
    UserListLiveView,
    UserDetailLiveView,
    SettingsLiveView,
)

routes = [
    ("/", HomeLiveView),
    ("/users", UserListLiveView),
    ("/users/{id:int}", UserDetailLiveView),
    ("/settings", SettingsLiveView),
]

app = PyView()

for path, view in routes:
    app.add_live_view(path, view)
```

## Non-LiveView Routes

You can add regular Starlette routes alongside LiveViews for APIs, webhooks, or static pages:

```python
from starlette.routing import Route
from starlette.responses import JSONResponse

async def health_check(request):
    return JSONResponse({"status": "ok"})

app = PyView()
app.routes.append(Route("/health", health_check))
app.add_live_view("/", HomeLiveView)
```

## Custom Root Template

Customize the HTML shell that wraps your LiveViews:

```python
from pyview import PyView, defaultRootTemplate
from markupsafe import Markup

css = Markup("""
<link rel="stylesheet" href="/static/styles.css">
<script src="https://cdn.tailwindcss.com"></script>
""")

app = PyView()
app.rootTemplate = defaultRootTemplate(css=css)
```

See [Socket and Context - Navigation](socket-and-context.md#navigation) for navigating between routes programmatically.
