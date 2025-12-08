# Authentication

Need to protect your LiveViews? PyView gives you the building blocks:

- **Session access** — Read session data in your LiveViews
- **View protection** — The `@requires` decorator checks scopes before mount
- **Custom auth** — Implement your own logic with `AuthProvider`

PyView builds on [Starlette's authentication system](https://www.starlette.io/authentication/), so you get signed cookies and scope-based authorization out of the box.

## Quick Start

### 1. Add Session Middleware

First, enable [sessions](https://www.starlette.io/middleware/#sessionmiddleware) in your app:

```python
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from pyview import PyView

app = PyView(
    middleware=[
        Middleware(SessionMiddleware, secret_key="your-secret-key")
    ]
)
```

### 2. Protect a View

Use `@requires` to restrict access:

```python
from pyview import LiveView, LiveViewSocket
from pyview.auth import requires

@requires("authenticated")
class DashboardView(LiveView[dict]):
    async def mount(self, socket: LiveViewSocket[dict], session):
        user_id = session.get("user_id")
        socket.context = {
            "user_id": user_id,
            "welcome": f"Hello, user {user_id}!"
        }
```

If the user doesn't have the `authenticated` scope, they'll get a 403. To redirect instead:

```python
@requires("authenticated", redirect="/login")
class DashboardView(LiveView[dict]):
    ...
```

### 3. Access Session Data

The `session` parameter in `mount` gives you read access to session data:

```python
async def mount(self, socket: LiveViewSocket[dict], session):
    user_id = session.get("user_id")
    is_admin = session.get("is_admin", False)

    if not user_id:
        await socket.push_navigate("/login")
        return

    socket.context = {"user_id": user_id, "is_admin": is_admin}
```

---

## The @requires Decorator

### Single Scope

```python
@requires("authenticated")
class ProfileView(LiveView[dict]):
    ...
```

### Multiple Scopes

All scopes must be present:

```python
@requires(["authenticated", "premium"])
class PremiumView(LiveView[dict]):
    ...
```

### Custom Status Code

```python
@requires("admin", status_code=404)  # Hide the existence of admin pages
class AdminView(LiveView[dict]):
    ...
```

### How Scopes Work

Scopes come from Starlette's [`AuthenticationMiddleware`](https://www.starlette.io/authentication/). You provide a backend that reads the session and returns the appropriate scopes:

```python
from starlette.authentication import (
    AuthCredentials, AuthenticationBackend, SimpleUser
)
from starlette.middleware.authentication import AuthenticationMiddleware

class SessionAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn):
        user_id = conn.session.get("user_id")
        if not user_id:
            return None  # No scopes - @requires("authenticated") will fail

        # Build scopes based on session data
        scopes = ["authenticated"]
        if conn.session.get("is_admin"):
            scopes.append("admin")

        return AuthCredentials(scopes), SimpleUser(user_id)

# Add to your app
app.add_middleware(AuthenticationMiddleware, backend=SessionAuthBackend())
```

Now `@requires("authenticated")` checks for that scope, and `@requires("admin")` only passes for admin users.
