"""
Type-Safe Request Context Pattern for PyView

This shows how to create a type-safe context that combines:
1. Services (database, cache, etc.) - from socket.state
2. Request data (user, session data) - user-defined context
3. Access services directly from socket when needed (no self.db = ...)

This pattern is inspired by:
- Phoenix LiveView's socket.assigns
- FastAPI's dependency injection
- ASP.NET Core's HttpContext
"""
from __future__ import annotations
from typing import Generic, TypeVar, TYPE_CHECKING
from dataclasses import dataclass
from starlette.datastructures import State

if TYPE_CHECKING:
    from pyview.live_socket import LiveViewSocket


# =============================================================================
# Example Services
# =============================================================================

class Database:
    async def get_user(self, user_id: int) -> dict:
        return {"id": user_id, "name": f"User {user_id}"}


class Cache:
    async def get(self, key: str) -> str | None:
        return None


class AuthService:
    async def authenticate(self, token: str) -> dict | None:
        return {"id": 1, "email": "user@example.com"}


# =============================================================================
# PATTERN 1: Type-Safe Context Wrapper (Recommended)
# =============================================================================

class RequestContext:
    """
    Type-safe wrapper for socket that provides:
    - Type-safe service access (socket.state)
    - Type-safe view context (socket.context)
    - No need for self.db = ... assignments!

    This combines the best of both worlds.
    """

    def __init__(self, socket: "LiveViewSocket"):
        self._socket = socket

    # Services (from socket.state) with type safety
    @property
    def database(self) -> Database:
        """Access database service."""
        return self._socket.state.database

    @property
    def cache(self) -> Cache:
        """Access cache service."""
        return self._socket.state.cache

    @property
    def auth(self) -> AuthService:
        """Access auth service."""
        return self._socket.state.auth

    # View-specific context (typed!)
    @property
    def context(self):
        """Access the typed view context."""
        return self._socket.context

    # Session data helpers
    def session_get(self, key: str, default=None):
        """Type-safe session access."""
        # Could store session on first access
        if not hasattr(self, '_session'):
            self._session = {}
        return self._session.get(key, default)


def ctx(socket: "LiveViewSocket") -> RequestContext:
    """Helper to get type-safe request context."""
    return RequestContext(socket)


# =============================================================================
# Usage Example - No self.db = ... needed!
# =============================================================================

from pyview import LiveView, LiveViewSocket


@dataclass
class UserProfileContext:
    """Your view's data context."""
    user: dict | None = None
    posts: list = None


class UserProfileView(LiveView[UserProfileContext]):
    """
    Example view showing the new pattern.

    Note: We DON'T store services as instance variables!
    We access them from socket when needed.
    """

    async def mount(self, socket: LiveViewSocket[UserProfileContext], session):
        # Get type-safe context
        c = ctx(socket)

        # ✅ Access services directly - no self.db = ...
        # ✅ Full type safety
        # ✅ Services accessed when needed
        user = await c.database.get_user(session.get("user_id", 1))

        # Set view context
        socket.context = UserProfileContext(user=user, posts=[])

    async def handle_event(self, event: str, payload, socket):
        if event == "refresh":
            c = ctx(socket)

            # ✅ Access services directly in event handlers too!
            # No need for self.database - just use ctx(socket)
            user = await c.database.get_user(c.context.user["id"])
            cached_data = await c.cache.get(f"user:{user['id']}")

            # Update context
            c.context.user = user

    async def render(self, context: UserProfileContext, meta):
        return f"<div>User: {context.user['name']}</div>"


# =============================================================================
# PATTERN 2: Lazy-Loading Context (Like svcs)
# =============================================================================

class LazyContext:
    """
    Context that lazily creates services only when accessed.

    This mimics svcs behavior:
    - Services created on first access
    - Cached for subsequent accesses
    - Can be cleaned up
    """

    def __init__(self, socket: "LiveViewSocket"):
        self._socket = socket
        self._cache = {}

    @property
    def database(self) -> Database:
        """Lazy-load database service."""
        if "database" not in self._cache:
            # Could call a factory here
            self._cache["database"] = self._socket.state.database
        return self._cache["database"]

    @property
    def cache(self) -> Cache:
        """Lazy-load cache service."""
        if "cache" not in self._cache:
            self._cache["cache"] = self._socket.state.cache
        return self._cache["cache"]

    async def cleanup(self):
        """Clean up any resources."""
        for service in self._cache.values():
            if hasattr(service, "close"):
                await service.close()
        self._cache.clear()


# =============================================================================
# PATTERN 3: Combined Services + Context (Most Powerful)
# =============================================================================

T = TypeVar("T")


class TypedRequestContext(Generic[T]):
    """
    Combines services AND typed view context in one place.

    This gives you a single, type-safe object with:
    - Services (database, cache, etc.)
    - View context (your data)
    - Session helpers
    """

    def __init__(self, socket: "LiveViewSocket[T]"):
        self._socket = socket

    # Services
    @property
    def db(self) -> Database:
        return self._socket.state.database

    @property
    def cache(self) -> Cache:
        return self._socket.state.cache

    @property
    def auth(self) -> AuthService:
        return self._socket.state.auth

    # Typed view context
    @property
    def data(self) -> T:
        """Access the typed view context."""
        return self._socket.context

    @data.setter
    def data(self, value: T):
        """Set the view context."""
        self._socket.context = value

    # Convenience helpers
    async def get_current_user(self) -> dict | None:
        """Common operation - get current user."""
        if hasattr(self, "_current_user"):
            return self._current_user

        # Could read from session, database, etc.
        self._current_user = await self.db.get_user(1)
        return self._current_user


def typed_ctx(socket: "LiveViewSocket[T]") -> TypedRequestContext[T]:
    """Get typed request context."""
    return TypedRequestContext(socket)


# Usage with typed context
@dataclass
class DashboardContext:
    user: dict
    stats: dict


class DashboardView(LiveView[DashboardContext]):
    async def mount(self, socket: LiveViewSocket[DashboardContext], session):
        # Get typed context - T is inferred!
        c = typed_ctx(socket)

        # ✅ c.db is Database
        # ✅ c.data is DashboardContext
        user = await c.db.get_user(session["user_id"])
        stats = {"views": 100, "clicks": 50}

        c.data = DashboardContext(user=user, stats=stats)

    async def render(self, context: DashboardContext, meta):
        return f"""
        <div>
            <h1>{context.user['name']}</h1>
            <p>Views: {context.stats['views']}</p>
        </div>
        """


# =============================================================================
# PATTERN 4: Context as a Mixin (Like FastAPI's Request)
# =============================================================================

class ServicesMixin:
    """
    Mixin that provides service access.

    This could be added to LiveView base class.
    """

    def services(self, socket: "LiveViewSocket") -> RequestContext:
        """Get type-safe services."""
        return RequestContext(socket)


class MyView(ServicesMixin, LiveView):
    """Views get service access automatically."""

    async def mount(self, socket, session):
        # Access via mixin
        svc = self.services(socket)
        user = await svc.database.get_user(1)


# =============================================================================
# Comparison with Other Frameworks
# =============================================================================

"""
## Phoenix LiveView (Elixir)

    def mount(_params, _session, socket) do
      # Access via socket.assigns
      socket = assign(socket, :user, get_user())
      socket = assign(socket, :posts, [])
      {:ok, socket}
    end

    def handle_event("click", _params, socket) do
      # Access assigned values
      user = socket.assigns.user
      {:noreply, socket}
    end

- Uses socket.assigns for all state
- No separate "services" concept (Elixir handles DI differently)
- Pattern matching provides some type safety


## FastAPI (Python)

    @app.get("/users/{user_id}")
    async def get_user(
        user_id: int,
        db: Database = Depends(get_db),
        cache: Cache = Depends(get_cache)
    ):
        # Dependencies injected as function parameters
        user = await db.get_user(user_id)
        return user

- Dependencies injected as parameters
- Full type safety through type hints
- Can't easily inject into class methods


## ASP.NET Core (C#)

    public class UserController : Controller
    {
        private readonly IDatabase _db;

        // Constructor injection
        public UserController(IDatabase db)
        {
            _db = db;
        }

        public async Task<IActionResult> GetUser(int id)
        {
            var user = await _db.GetUser(id);
            return Ok(user);
        }
    }

- Constructor injection (requires DI container)
- Full type safety
- Lifetime management by framework


## Flask (Python)

    from flask import g

    @app.before_request
    def setup():
        g.db = get_db()

    @app.route("/users/<int:user_id>")
    def get_user(user_id):
        user = g.db.get_user(user_id)  # Access via g (global)
        return user

- Uses 'g' (request-local storage) like our socket.state
- No type safety by default
- Manual setup in before_request


## Django (Python)

    class UserView(View):
        def get(self, request, user_id):
            # Access request, but services usually imported/instantiated
            from myapp.services import UserService

            service = UserService()  # Manual instantiation
            user = service.get_user(user_id)
            return JsonResponse(user)

- No built-in DI
- Services usually module-level or manually instantiated
- Request object available but not typed for user data


## PyView's Approach

With our RequestContext pattern:

    async def mount(self, socket, session):
        c = ctx(socket)

        # ✅ Type-safe service access (like FastAPI)
        # ✅ Available in all methods (like Phoenix assigns)
        # ✅ No instance variable assignments needed
        # ✅ Clean, simple API
        user = await c.database.get_user(session["user_id"])
"""


# =============================================================================
# Benefits of This Pattern
# =============================================================================

"""
1. **No Instance Variables Needed**
   - Don't do: self.db = get_db()
   - Do: ctx(socket).database

2. **Access Services Anywhere**
   - mount(), handle_event(), handle_info() all get socket
   - Just use ctx(socket) to get services

3. **Type Safety**
   - IDE autocomplete for services
   - Type checker validates usage
   - Refactoring support

4. **Testability**
   - Inject mocks into socket.state
   - ctx(socket) still works, now with mocks

5. **Lazy Loading (Optional)**
   - Services can be created on first access
   - Like svcs behavior

6. **Lifetime Management**
   - Services live on socket.state
   - Cleaned up with socket lifecycle
   - Can add explicit cleanup if needed

7. **Combines Both Worlds**
   - Services (database, cache) from socket.state
   - View data (user, posts) from socket.context
   - One unified, type-safe API
"""


if __name__ == "__main__":
    print(__doc__)
