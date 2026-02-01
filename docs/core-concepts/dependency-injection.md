---
title: Dependency Injection
sidebar:
  order: 6
---

# Dependency Injection

PyView provides a simple dependency injection system via `Depends()`. This lets you inject services, database connections, and other dependencies into your handlers—keeping your LiveView code clean and testable.

## Basic Usage

Use `Depends()` to declare a dependency as a default parameter:

```python
from pyview import Depends, LiveView, LiveViewSocket
from typing import TypedDict

# A simple dependency function
async def get_database():
    db = await create_connection()
    return db

class ItemsContext(TypedDict):
    items: list

class ItemsLiveView(LiveView[ItemsContext]):
    async def mount(self, socket: LiveViewSocket[ItemsContext], db=Depends(get_database)):
        items = await db.fetch_all("SELECT * FROM items")
        socket.context = {"items": items}
```

The `get_database()` function is called automatically when `mount()` runs, and its result is passed as the `db` parameter.

## How It Works

1. PyView inspects your method signature for `Depends()` defaults
2. It calls each dependency function, resolving them in order
3. Results are passed to your method as regular arguments

Dependencies can be sync or async functions:

```python
# Sync dependency
def get_config():
    return {"theme": "dark", "items_per_page": 20}

# Async dependency
async def get_user_service():
    return UserService()

class SettingsLiveView(LiveView[SettingsContext]):
    async def mount(
        self,
        socket,
        config=Depends(get_config),           # sync is fine
        users=Depends(get_user_service),      # async is fine
    ):
        socket.context = {"config": config}
```

## Session Access in Dependencies

Use the `Session` type to inject the session dict into your dependencies. This is useful for loading user context into your view:

```python
from pyview import Depends, LiveView, Session

async def get_current_user(session: Session):
    """Load the current user from session."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return await User.get(user_id)

class ProfileLiveView(LiveView[ProfileContext]):
    async def mount(self, socket, user=Depends(get_current_user)):
        socket.context = {"user": user, "name": user.name if user else "Guest"}
```

> **Note:** For restricting access to routes, see [Authentication](/core-concepts/authentication).

## Dependency Chains

Dependencies can depend on other dependencies. PyView resolves them in the right order:

```python
from pyview import Depends, LiveView, Session

async def get_database():
    return await create_connection()

async def get_user_repository(db=Depends(get_database)):
    return UserRepository(db)

async def get_current_user(session: Session, users=Depends(get_user_repository)):
    user_id = session.get("user_id")
    return await users.find(user_id) if user_id else None

class DashboardLiveView(LiveView[DashboardContext]):
    async def mount(self, socket, user=Depends(get_current_user)):
        socket.context = {"user": user}
```

## Caching

By default, dependencies are cached per-request. If multiple parameters use the same dependency, the function only runs once:

```python
async def get_database():
    print("Creating connection")  # Only prints once per request
    return await create_connection()

async def get_users(db=Depends(get_database)):
    return UserRepository(db)

async def get_posts(db=Depends(get_database)):
    return PostRepository(db)

class FeedLiveView(LiveView[FeedContext]):
    async def mount(
        self,
        socket,
        users=Depends(get_users),  # get_database called once
        posts=Depends(get_posts),  # reuses cached connection
    ):
        ...
```

To disable caching for a specific dependency (get a fresh value each time):

```python
def get_timestamp():
    return datetime.now()

class MyView(LiveView):
    async def mount(
        self,
        socket,
        time=Depends(get_timestamp, use_cache=False),  # Always fresh
    ):
        socket.context = {"loaded_at": time}
```

## Using with Event Handlers

`Depends()` works in event handlers too:

```python
from pyview import Depends, LiveView
from pyview.events import BaseEventHandler, event

async def get_notification_service():
    return NotificationService()

class NotificationLiveView(BaseEventHandler, LiveView[NotificationContext]):
    async def mount(self, socket, session):
        socket.context = {"notifications": [], "user_id": session.get("user_id")}

    @event("mark_read")
    async def handle_mark_read(
        self,
        socket,
        notification_id: str,
        service=Depends(get_notification_service),
    ):
        await service.mark_read(notification_id, socket.context["user_id"])
        socket.context["notifications"] = await service.get_unread()
```

## Testing

Dependencies make testing straightforward. Pass mock values directly—`Depends()` is bypassed:

```python
from unittest.mock import MagicMock

async def test_items_mount():
    view = ItemsLiveView()
    socket = MagicMock()
    socket.context = {}
    mock_db = MockDatabase(items=[{"id": 1, "name": "Test Item"}])

    await view.mount(socket, session={}, db=mock_db)

    assert socket.context["items"] == [{"id": 1, "name": "Test Item"}]
```

You can also test dependency functions directly:

```python
async def test_get_current_user():
    session = {"user_id": "123"}
    user = await get_current_user(session)
    assert user.id == "123"

async def test_get_current_user_no_session():
    user = await get_current_user({})
    assert user is None
```

## Supported Methods

`Depends()` works in these LiveView methods:

| Method | Async Deps | Session Available |
|--------|------------|-------------------|
| `__init__` | No (sync only) | Yes |
| `mount` | Yes | Yes |
| `handle_params` | Yes | No |
| `handle_event` | Yes | No |
| `@event` handlers | Yes | No |

## Available Injectables

### Type-based injection

Use type annotations to inject these values—parameter names don't matter:

| Type | Description |
|------|-------------|
| `Session` | Session dict (read-only in LiveViews) |

```python
from pyview import Session

async def get_user(sess: Session):  # Name doesn't matter, type does
    return sess.get("user_id")
```

### Name-based injection

These are injected based on parameter name:

| Parameter | Type | Description |
|-----------|------|-------------|
| `socket` | `LiveViewSocket` | The current socket instance |
| `session` | `dict` | Session data (read-only in LiveViews) |
| `url` | `ParseResult` | Parsed URL (in `handle_params`) |
| `event` | `str` | Event name (in `handle_event`) |
| `payload` | `dict` | Raw event payload (in `handle_event`) |
| `params` | `Params` or `dict` | URL/form parameters |

```python
class MyLiveView(LiveView):
    async def mount(self, socket, session):
        ...

    async def handle_params(self, url, socket, page: int = 1):
        ...
```

> **Tip:** For dependency functions, prefer `Session` type over the `session` name—it's more explicit and works regardless of what you name the parameter.

## When to Use Depends

Good uses for `Depends()`:

- **Database connections** — Inject connection pools or clients
- **Service classes** — Inject repositories, API clients, etc.
- **User/auth context** — Load current user from session
- **Configuration** — Inject settings or feature flags

For simpler cases, regular Python patterns work fine:

```python
# Simple enough - just instantiate directly
class MyLiveView(LiveView):
    async def mount(self, socket, session):
        config = load_config()  # No need for Depends here
        socket.context = {"theme": config.theme}
```

Use `Depends()` when you want cleaner signatures, automatic dependency resolution, or easier testing.

## Migration from 0.8.x

In version 0.9.0, route registration changed from factory functions to classes:

```python
# Before (0.8.x)
routes.add("/items", lambda: ItemsView())

# After (0.9.0)
routes.add("/items", ItemsView)
```

This change enables `Depends()` support in `__init__`, allowing dependencies to be injected when the view is instantiated.
