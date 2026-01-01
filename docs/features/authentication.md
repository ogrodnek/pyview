# Sessions and Authentication

PyView integrates with Starlette's session and authentication systems. This guide covers accessing session data, protecting routes, and implementing custom authentication.

## Sessions

Sessions let you persist data across requests for a user. The session dict is passed to your `mount()` method.

### Enabling Sessions

Add Starlette's `SessionMiddleware` to your application:

```python
from starlette.middleware.sessions import SessionMiddleware
from pyview import PyView

app = PyView()
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")
```

> **Important:** Use a strong, random secret key in production. Generate one with `openssl rand -base64 32`.

### Accessing Session Data

The session is available as the second parameter to `mount()`:

```python
from pyview import LiveView, LiveViewSocket
from typing import TypedDict


class DashboardContext(TypedDict):
    user_id: str | None
    username: str | None


class DashboardLiveView(LiveView[DashboardContext]):
    async def mount(self, socket: LiveViewSocket[DashboardContext], session):
        # Read from session
        user_id = session.get("user_id")
        username = session.get("username")

        socket.context = {
            "user_id": user_id,
            "username": username,
        }

        if user_id:
            # Load user-specific data
            socket.context["notifications"] = await load_notifications(user_id)
```

### Session Persistence

Sessions are read-only within LiveViews. To modify session data (login, logout, preferences), use a regular Starlette route:

```python
from starlette.routing import Route
from starlette.responses import RedirectResponse

async def login(request):
    form = await request.form()
    user = await authenticate(form["username"], form["password"])

    if user:
        request.session["user_id"] = user.id
        request.session["username"] = user.username
        return RedirectResponse("/dashboard", status_code=303)

    return RedirectResponse("/login?error=invalid", status_code=303)

async def logout(request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)

app.routes.append(Route("/auth/login", login, methods=["POST"]))
app.routes.append(Route("/auth/logout", logout, methods=["POST"]))
```

Your LiveView reads the session; regular routes modify it.

## Authentication with `@requires`

The `@requires` decorator protects LiveViews, requiring users to have specific authentication scopes.

### Basic Usage

```python
from pyview import LiveView
from pyview.auth import requires


@requires("authenticated")
class SettingsLiveView(LiveView[SettingsContext]):
    async def mount(self, socket, session):
        # Only authenticated users reach this code
        socket.context = {"user_id": session["user_id"]}
```

If the user isn't authenticated, they'll receive a 403 Forbidden response.

### Redirect Unauthenticated Users

Redirect to a login page instead of showing an error:

```python
@requires("authenticated", redirect="/login")
class DashboardLiveView(LiveView[DashboardContext]):
    async def mount(self, socket, session):
        socket.context = {"user": await load_user(session["user_id"])}
```

### Multiple Scopes

Require multiple scopes (user must have all of them):

```python
@requires(["authenticated", "admin"])
class AdminLiveView(LiveView[AdminContext]):
    async def mount(self, socket, session):
        socket.context = {"users": await load_all_users()}
```

### Custom Status Code

```python
@requires("authenticated", status_code=401)
class ProtectedLiveView(LiveView[Context]):
    pass
```

## Setting Up Authentication

The `@requires` decorator works with Starlette's authentication system. You need an `AuthenticationMiddleware` that sets the user's scopes.

### Basic Session-Based Auth

```python
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    SimpleUser,
)
from starlette.middleware.authentication import AuthenticationMiddleware

class SessionAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn):
        user_id = conn.session.get("user_id")

        if user_id is None:
            # Not logged in - no scopes
            return AuthCredentials([]), None

        # Load user and their permissions
        user = await load_user(user_id)

        scopes = ["authenticated"]
        if user.is_admin:
            scopes.append("admin")

        return AuthCredentials(scopes), SimpleUser(user.username)

app = PyView()
app.add_middleware(SessionMiddleware, secret_key="...")
app.add_middleware(AuthenticationMiddleware, backend=SessionAuthBackend())
```

### OAuth Example

For OAuth providers (Google, GitHub, etc.), see the [pyview-example-auth](https://github.com/pyview/pyview-example-auth) repository which demonstrates integration with [authlib](https://docs.authlib.org/).

## Custom Auth Providers

For advanced cases, implement the `AuthProvider` protocol:

```python
from starlette.websockets import WebSocket
from pyview.auth import AuthProvider, AuthProviderFactory
from pyview import LiveView


class APIKeyAuthProvider(AuthProvider):
    def __init__(self, required_key: str):
        self.required_key = required_key

    async def has_required_auth(self, websocket: WebSocket) -> bool:
        """Called when WebSocket connects to verify auth."""
        # Check header, query param, or session
        api_key = websocket.query_params.get("api_key")
        return api_key == self.required_key

    def wrap(self, func):
        """Wrap the HTTP endpoint for initial page load."""
        async def wrapped(request):
            api_key = request.query_params.get("api_key")
            if api_key != self.required_key:
                return Response("Unauthorized", status_code=401)
            return await func(request)
        return wrapped


# Apply to a LiveView
class APIProtectedView(LiveView[Context]):
    pass

AuthProviderFactory.set(APIProtectedView, APIKeyAuthProvider("secret-key"))
app.add_live_view("/api/dashboard", APIProtectedView)
```

## Secret Key Configuration

PyView uses a secret key for session serialization. Set it via environment variable:

```bash
export PYVIEW_SECRET="your-secret-key-here"
```

If not set, PyView generates a random key on startup—fine for development, but sessions won't persist across restarts.

Generate a production key:

```bash
openssl rand -base64 32
```

## Complete Example

Here's a full example with login, logout, and protected routes:

```python
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.authentication import AuthCredentials, AuthenticationBackend, SimpleUser
from starlette.routing import Route
from starlette.responses import RedirectResponse, HTMLResponse
from pyview import PyView, LiveView, LiveViewSocket
from pyview.auth import requires
from typing import TypedDict


# Auth backend
class SessionAuth(AuthenticationBackend):
    async def authenticate(self, conn):
        user_id = conn.session.get("user_id")
        if not user_id:
            return AuthCredentials([]), None
        return AuthCredentials(["authenticated"]), SimpleUser(conn.session.get("username", ""))


# Protected LiveView
class DashboardContext(TypedDict):
    username: str


@requires("authenticated", redirect="/login")
class DashboardLiveView(LiveView[DashboardContext]):
    async def mount(self, socket: LiveViewSocket[DashboardContext], session):
        socket.context = {"username": session.get("username", "User")}


# Login page (regular route)
async def login_page(request):
    error = request.query_params.get("error", "")
    return HTMLResponse(f"""
        <form method="post" action="/auth/login">
            <input name="username" placeholder="Username" required>
            <input name="password" type="password" placeholder="Password" required>
            <button type="submit">Login</button>
            {"<p style='color:red'>Invalid credentials</p>" if error else ""}
        </form>
    """)


async def login(request):
    form = await request.form()
    # In production, verify against database
    if form["username"] == "demo" and form["password"] == "demo":
        request.session["user_id"] = "1"
        request.session["username"] = form["username"]
        return RedirectResponse("/dashboard", status_code=303)
    return RedirectResponse("/login?error=1", status_code=303)


async def logout(request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# App setup
app = PyView()
app.add_middleware(SessionMiddleware, secret_key="change-me-in-production")
app.add_middleware(AuthenticationMiddleware, backend=SessionAuth())

app.routes.append(Route("/login", login_page, methods=["GET"]))
app.routes.append(Route("/auth/login", login, methods=["POST"]))
app.routes.append(Route("/auth/logout", logout, methods=["POST"]))

app.add_live_view("/dashboard", DashboardLiveView)
```

## Related

- [LiveView Lifecycle](../core-concepts/liveview-lifecycle.md) — The `mount()` method where you access sessions
- [Routing](../core-concepts/routing.md) — Adding regular routes alongside LiveViews
