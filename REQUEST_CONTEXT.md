# Request Context Pattern for PyView

## The Key Insight

**You don't need `self.db = ...` assignments!**

Since all LiveView methods get `socket`, you can access services directly from `socket.state` when needed:

```python
# ❌ OLD: Storing services as instance variables
class OldView(LiveView):
    async def mount(self, socket, session):
        self.database = socket.state.database  # Unnecessary!
        self.cache = socket.state.cache

    async def handle_event(self, event, payload, socket):
        user = await self.database.get_user(1)  # Via self

# ✅ NEW: Access from socket when needed
class NewView(LiveView):
    async def mount(self, socket, session):
        c = ctx(socket)  # Type-safe wrapper
        user = await c.database.get_user(1)

    async def handle_event(self, event, payload, socket):
        c = ctx(socket)  # Access when needed
        user = await c.database.get_user(2)
```

## Why This is Better

1. **Stateless LiveView** - No instance state to manage
2. **Available everywhere** - All methods get `socket`
3. **Easier testing** - Just mock `socket.state`
4. **Functional style** - Socket is the single source of truth
5. **Like Phoenix LiveView** - Similar to `socket.assigns`

## Type-Safe RequestContext Pattern

Create a type-safe wrapper for `socket.state`:

```python
from starlette.datastructures import State

class RequestContext:
    """Type-safe wrapper for socket providing access to services."""

    def __init__(self, socket):
        self._socket = socket

    @property
    def database(self) -> Database:
        """Get database service with type safety."""
        return self._socket.state.database

    @property
    def cache(self) -> Cache:
        """Get cache service with type safety."""
        return self._socket.state.cache

    @property
    def context(self):
        """Access the typed view context."""
        return self._socket.context


def ctx(socket) -> RequestContext:
    """Helper to get type-safe request context."""
    return RequestContext(socket)
```

## Usage in LiveViews

```python
@dataclass
class UserContext:
    user: dict
    posts: list


class UserView(LiveView[UserContext]):
    async def mount(self, socket, session):
        c = ctx(socket)

        # ✅ Full type safety
        # ✅ IDE autocomplete
        # ✅ Type checker validates
        user = await c.database.get_user(session["user_id"])
        posts = await c.database.get_user_posts(user["id"])

        socket.context = UserContext(user=user, posts=posts)

    async def handle_event(self, event, payload, socket):
        if event == "refresh":
            c = ctx(socket)

            # ✅ Access services when needed
            user = await c.database.get_user(c.context.user["id"])
            c.context.user = user

    async def render(self, context, meta):
        return f"<div>User: {context.user['name']}</div>"
```

## Benefits

| Feature | `self.db = ...` | `ctx(socket).database` |
|---------|----------------|------------------------|
| Type Safety | ❌ Manual hints | ✅ Automatic |
| IDE Support | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| Testing | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Stateless | ❌ No | ✅ Yes |
| Clarity | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

## Comparison with Other Frameworks

### Phoenix LiveView (Elixir)

```elixir
def mount(_params, _session, socket) do
  # Access via socket.assigns
  socket = assign(socket, :user, get_user())
  {:ok, socket}
end

def handle_event("click", _params, socket) do
  user = socket.assigns.user
  {:noreply, socket}
end
```

**PyView equivalent:**
```python
async def mount(self, socket, session):
    c = ctx(socket)
    user = await c.database.get_user(1)
    socket.context.user = user

async def handle_event(self, event, payload, socket):
    user = socket.context.user
```

### FastAPI (Python)

```python
@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    db: Database = Depends(get_db),
    cache: Cache = Depends(get_cache)
):
    user = await db.get_user(user_id)
    return user
```

**PyView equivalent:**
```python
async def mount(self, socket, session):
    c = ctx(socket)
    # Type-safe, like FastAPI's Depends
    user = await c.database.get_user(session["user_id"])
```

### Flask (Python)

```python
from flask import g

@app.before_request
def setup():
    g.db = get_db()

@app.route("/users/<int:user_id>")
def get_user(user_id):
    user = g.db.get_user(user_id)
    return user
```

**PyView equivalent:**
```python
# socket.state is like Flask's g
async def mount(self, socket, session):
    c = ctx(socket)  # Type-safe wrapper around socket.state
    user = await c.database.get_user(session["user_id"])
```

## Advanced: Combined Services + Context

You can create a context that combines services AND your view data:

```python
from typing import Generic, TypeVar

T = TypeVar("T")

class TypedRequestContext(Generic[T]):
    """Combines services and typed view context."""

    def __init__(self, socket):
        self._socket = socket

    # Services
    @property
    def db(self) -> Database:
        return self._socket.state.database

    @property
    def cache(self) -> Cache:
        return self._socket.state.cache

    # Typed view context
    @property
    def data(self) -> T:
        return self._socket.context

    @data.setter
    def data(self, value: T):
        self._socket.context = value


def typed_ctx(socket) -> TypedRequestContext:
    return TypedRequestContext(socket)


# Usage
@dataclass
class DashboardContext:
    user: dict
    stats: dict


class DashboardView(LiveView[DashboardContext]):
    async def mount(self, socket, session):
        c = typed_ctx(socket)

        # ✅ c.db is Database
        # ✅ c.data is DashboardContext
        user = await c.db.get_user(session["user_id"])
        c.data = DashboardContext(user=user, stats={})
```

## svcs Lifecycle

If you're using the optional `svcs` integration:

**How svcs works:**
```python
# 1. Register factories
@configure_svcs(app)
def register(registry):
    registry.register_factory(Database, create_db)

# 2. Services created LAZILY on first access
db = await get_services(socket, Database)  # Created NOW
db2 = await get_services(socket, Database) # Same instance

# 3. Automatic cleanup when connection closes
```

**Key differences:**

| Feature | svcs | socket.state |
|---------|------|--------------|
| Instantiation | Lazy (on first access) | Eager (when assigned) |
| Lifecycle | Automatic cleanup | Manual cleanup |
| Complexity | Factory-based | Direct assignment |
| Use case | Complex apps | Simple apps |

**When to use svcs:**
- Need lazy instantiation
- Complex service factories
- Automatic resource cleanup
- Large apps with many services

**When to use socket.state:**
- Want simplicity
- Control service instantiation
- Services don't need factories
- Maximum testability

**Hybrid approach:**
You can use BOTH! Simple services on `socket.state`, complex ones via `svcs`.

## Testing

Testing is trivial - just mock `socket.state`:

```python
@pytest.mark.asyncio
async def test_user_view():
    # Create mocks
    mock_db = Mock(spec=Database)
    mock_db.get_user = AsyncMock(return_value={"id": 1, "name": "Test"})

    # Inject into socket
    socket = UnconnectedSocket()
    socket.state.database = mock_db

    # Test with type-safe wrapper
    c = ctx(socket)
    user = await c.database.get_user(1)

    # ✅ Still type-safe in tests
    assert user["name"] == "Test"
```

## Summary

**The Pattern:**
1. Access services from `socket` when needed
2. Use `ctx(socket)` for type safety
3. No `self.x = ...` assignments needed
4. Available in all methods that get `socket`

**Benefits:**
- ✅ Type safety
- ✅ Stateless LiveViews
- ✅ Easy testing
- ✅ Clean, functional style
- ✅ Similar to Phoenix LiveView

**Examples:**
- `examples/request_context_patterns.py` - Complete patterns
- `examples/svcs_lifecycle_demo.py` - Understanding svcs
- `examples/type_safe_demo.py` - Type safety in action

Run them:
```bash
poetry run python examples/svcs_lifecycle_demo.py
poetry run python examples/type_safe_demo.py
```
