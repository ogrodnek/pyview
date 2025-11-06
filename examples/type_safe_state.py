"""
Understanding Starlette's State and Adding Type Safety

This guide explains what State is and shows patterns for adding type safety
to socket.state in PyView applications.
"""
from typing import Protocol, TypeVar, Generic, runtime_checkable
from starlette.datastructures import State
from dataclasses import dataclass


# =============================================================================
# What is State?
# =============================================================================

"""
State is a simple wrapper around a dictionary that allows attribute access:

    state = State()
    state.foo = "bar"      # Sets state._state["foo"] = "bar"
    print(state.foo)       # Gets state._state["foo"]

It's implemented as:

    class State:
        _state: dict[str, Any]

        def __setattr__(self, key, value):
            self._state[key] = value

        def __getattr__(self, key):
            return self._state[key]  # Raises AttributeError if missing

Key points:
- It's just a dictionary with attribute access syntax
- NOT type-safe by default - you can assign anything
- Raises AttributeError (not KeyError) for missing attributes
- Used for both request.state and app.state in Starlette
"""


# =============================================================================
# The Problem: No Type Safety
# =============================================================================

def example_no_type_safety():
    """Without type hints, you get no autocomplete or type checking."""
    state = State()

    # No autocomplete here - your IDE doesn't know what's available
    state.database = "some db"
    state.cache = "some cache"

    # Typos aren't caught
    db = state.databse  # Oops! Runtime AttributeError

    # Type checker can't help
    result = state.database.query()  # Type checker: database is Any


# =============================================================================
# SOLUTION 1: Typed Service Locator Pattern (Recommended)
# =============================================================================

class Database:
    """Example service."""
    async def query(self, sql: str) -> list:
        return []


class Cache:
    """Example service."""
    async def get(self, key: str) -> str | None:
        return None


class Services:
    """
    Type-safe service locator.

    This is a simple, effective pattern for getting type safety with
    socket.state. Define all your services as properties.
    """

    def __init__(self, state: State):
        self._state = state

    @property
    def database(self) -> Database:
        """Get the database service."""
        return self._state.database

    @property
    def cache(self) -> Cache:
        """Get the cache service."""
        return self._state.cache


def get_services(socket) -> Services:
    """Helper to get type-safe services from socket.state."""
    return Services(socket.state)


# Usage in LiveView:
async def mount_example_1(socket, session):
    """
    Now you get full type safety and autocomplete!
    """
    services = get_services(socket)

    # ✅ Autocomplete works!
    # ✅ Type checker knows this is Database
    # ✅ IDE shows you available methods
    result = await services.database.query("SELECT * FROM users")

    # ✅ Type checker catches typos
    # result = await services.databse.query(...)  # Error: no attribute 'databse'

    # ✅ Type checker validates method calls
    # result = await services.database.query(123)  # Error: expected str, got int


# =============================================================================
# SOLUTION 2: Protocol-Based Approach (More Flexible)
# =============================================================================

@runtime_checkable
class HasDatabase(Protocol):
    """Protocol for objects that have a database attribute."""
    database: Database


@runtime_checkable
class HasCache(Protocol):
    """Protocol for objects that have a cache attribute."""
    cache: Cache


# Combine protocols as needed
@runtime_checkable
class HasServices(HasDatabase, HasCache, Protocol):
    """Protocol for objects with all services."""
    pass


def get_database(socket: HasDatabase) -> Database:
    """Type-safe database access using Protocol."""
    return socket.state.database


# Usage in LiveView:
async def mount_example_2(socket, session):
    """
    Protocols give you flexibility - socket just needs to have .state.database.
    """
    db = get_database(socket)
    # ✅ Type checker knows db is Database
    result = await db.query("SELECT * FROM users")


# =============================================================================
# SOLUTION 3: Typed State Container (Most Type-Safe)
# =============================================================================

class TypedState(Generic[T]):
    """
    Generic typed state container.

    This gives you the strongest type safety by wrapping State with a
    user-defined type.
    """

    def __init__(self, state: State, services: T):
        self._state = state
        self._services = services
        # Store services on the underlying state
        for key, value in vars(services).items():
            setattr(state, key, value)

    @property
    def services(self) -> T:
        return self._services


@dataclass
class AppServices:
    """Define all your app's services with types."""
    database: Database
    cache: Cache
    # Add more services here...


# Setup in app:
def setup_typed_state(app, services: AppServices):
    """Helper to set up typed state."""
    # Store each service on app.state
    for key, value in vars(services).items():
        setattr(app.state, key, value)


# Usage in LiveView:
async def mount_example_3(socket, session):
    """
    Access services with full type safety.
    """
    # Direct access with type annotation
    db: Database = socket.state.database
    cache: Cache = socket.state.cache

    # ✅ Type checker knows the types
    result = await db.query("SELECT * FROM users")
    cached = await cache.get("key")


# =============================================================================
# SOLUTION 4: Extension Method Pattern (Clean API)
# =============================================================================

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyview.live_socket import LiveViewSocket


class SocketServices:
    """
    Extension methods for socket that provide type-safe service access.

    This pattern adds helper methods to your socket wrapper.
    """

    def __init__(self, socket: "LiveViewSocket"):
        self._socket = socket

    @property
    def database(self) -> Database:
        """Get database service with type safety."""
        return self._socket.state.database

    @property
    def cache(self) -> Cache:
        """Get cache service with type safety."""
        return self._socket.state.cache


def services(socket: "LiveViewSocket") -> SocketServices:
    """Get type-safe services from socket."""
    return SocketServices(socket)


# Usage in LiveView:
async def mount_example_4(socket, session):
    """
    Clean API with full type safety.
    """
    s = services(socket)

    # ✅ Autocomplete works
    # ✅ Type checker validates
    db_result = await s.database.query("SELECT * FROM users")
    cache_result = await s.cache.get("key")


# =============================================================================
# SOLUTION 5: TypedDict Approach (Documentation)
# =============================================================================

from typing import TypedDict, cast


class StateDict(TypedDict):
    """
    Use TypedDict to document expected state structure.

    Note: This is for documentation only - no runtime enforcement.
    """
    database: Database
    cache: Cache


# Usage:
async def mount_example_5(socket, session):
    """
    Use cast to tell type checker what's in state.
    """
    # Cast state to typed version
    state = cast(StateDict, socket.state._state)

    # ✅ Type checker knows the structure
    db = state["database"]  # Type: Database
    result = await db.query("SELECT * FROM users")

    # Note: This is documentation only - no runtime checking!


# =============================================================================
# COMPARISON
# =============================================================================

"""
| Approach | Type Safety | Runtime Safety | Complexity | Autocomplete |
|----------|-------------|----------------|------------|--------------|
| Service Locator | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | Low | ✅ Excellent |
| Protocol | ⭐⭐⭐⭐ | ⭐⭐ | Low | ✅ Good |
| Typed State | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Medium | ✅ Excellent |
| Extension | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | Low | ✅ Excellent |
| TypedDict | ⭐⭐⭐ | ⭐ | Low | ⭐ Fair |

RECOMMENDED: **Service Locator Pattern (Solution 1)**
- Simple to implement
- Excellent type safety
- Great IDE support
- Easy to test
"""


# =============================================================================
# PRACTICAL EXAMPLE: Full Implementation
# =============================================================================

# 1. Define your services
class DatabaseService:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    async def get_user(self, user_id: int) -> dict:
        return {"id": user_id, "name": "User"}


class CacheService:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url

    async def get(self, key: str) -> str | None:
        return None


class EmailService:
    async def send(self, to: str, subject: str, body: str) -> None:
        pass


# 2. Create typed service locator
class AppServices:
    """Type-safe service locator for the application."""

    def __init__(self, state: State):
        self._state = state

    @property
    def database(self) -> DatabaseService:
        return self._state.database

    @property
    def cache(self) -> CacheService:
        return self._state.cache

    @property
    def email(self) -> EmailService:
        return self._state.email


# 3. Create helper function
def services(socket) -> AppServices:
    """Get type-safe services from socket."""
    return AppServices(socket.state)


# 4. Use in your LiveView with full type safety!
from pyview import LiveView, LiveViewSocket
from dataclasses import dataclass as dc


@dc
class UserContext:
    user: dict
    cached_value: str | None = None


class UserProfileView(LiveView[UserContext]):
    async def mount(self, socket: LiveViewSocket[UserContext], session):
        # Get services with full type safety
        svc = services(socket)

        # ✅ IDE autocompletes all methods
        # ✅ Type checker validates argument types
        # ✅ Catch errors at development time
        user = await svc.database.get_user(session["user_id"])
        cached = await svc.cache.get(f"user:{session['user_id']}")

        socket.context = UserContext(user=user, cached_value=cached)

    async def render(self, context: UserContext, meta):
        return f"<div>User: {context.user['name']}</div>"


# =============================================================================
# TESTING WITH TYPE SAFETY
# =============================================================================

import pytest
from unittest.mock import Mock, AsyncMock


@pytest.mark.asyncio
async def test_user_profile_with_type_safety():
    """
    Test with mocks - type safety still works!
    """
    from pyview.live_socket import UnconnectedSocket

    # Create typed mocks
    mock_db = Mock(spec=DatabaseService)
    mock_db.get_user = AsyncMock(return_value={"id": 1, "name": "Test"})

    mock_cache = Mock(spec=CacheService)
    mock_cache.get = AsyncMock(return_value="cached_value")

    # Inject into socket.state
    socket = UnconnectedSocket()
    socket.state.database = mock_db
    socket.state.cache = mock_cache
    socket.state.email = Mock(spec=EmailService)

    # Test the view
    view = UserProfileView()
    await view.mount(socket, {"user_id": 1})

    # Verify
    assert socket.context.user["name"] == "Test"
    mock_db.get_user.assert_called_once_with(1)


if __name__ == "__main__":
    print(__doc__)
