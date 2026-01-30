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

Dependencies can access the session by declaring a `session` parameter:

```python
async def get_current_user(session):
    """Load the current user from session."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return await User.get(user_id)

class ProfileLiveView(LiveView[ProfileContext]):
    async def mount(self, socket, user=Depends(get_current_user)):
        if not user:
            socket.redirect("/login")
            return
        socket.context = {"user": user}
```

This is particularly useful for services that need authentication context.

## Dependency Chains

Dependencies can depend on other dependencies. PyView resolves them in the right order:

```python
async def get_database():
    return await create_connection()

async def get_user_repository(db=Depends(get_database)):
    return UserRepository(db)

async def get_current_user(session, users=Depends(get_user_repository)):
    user_id = session.get("user_id")
    return await users.find(user_id) if user_id else None

class DashboardLiveView(LiveView[DashboardContext]):
    async def mount(self, socket, user=Depends(get_current_user)):
        # user is resolved, which resolved users, which resolved db
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
        # Both repositories share the same database connection
        pass
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
from pyview.events import BaseEventHandler, event

async def get_notification_service(session):
    return NotificationService(session.get("user_id"))

class NotificationLiveView(BaseEventHandler, LiveView[NotificationContext]):
    async def mount(self, socket, session):
        socket.context = {"notifications": []}

    @event("mark_read")
    async def handle_mark_read(
        self,
        socket,
        notification_id: str,
        service=Depends(get_notification_service),
    ):
        await service.mark_read(notification_id)
        socket.context["notifications"] = await service.get_unread()
```

## Testing

Dependencies make testing straightforward. Override them by passing values directly:

```python
import pytest
from myapp.views import ItemsLiveView
from pyview.testing import mount_live_view

@pytest.fixture
def mock_db():
    return MockDatabase(items=[
        {"id": 1, "name": "Test Item"}
    ])

async def test_items_mount(mock_db):
    # Pass the dependency directly - Depends() is bypassed
    socket = await mount_live_view(ItemsLiveView)
    await socket.view.mount(socket, db=mock_db)

    assert socket.context["items"] == [{"id": 1, "name": "Test Item"}]
```

For more control, you can also test the dependency functions directly:

```python
async def test_get_current_user():
    session = {"user_id": "123"}
    user = await get_current_user(session)
    assert user.id == "123"

async def test_get_current_user_no_session():
    user = await get_current_user({})
    assert user is None
```

## Available Injectables

Beyond `Depends()`, certain parameter names are automatically injected:

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
        # socket and session are automatically injected
        pass

    async def handle_params(self, url, socket, page: int = 1):
        # url is injected, page is extracted from query params
        pass
```

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
