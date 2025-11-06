"""
Quick example showing the recommended type-safe pattern in action.
"""
from pyview import PyView, LiveView, LiveViewSocket
from pyview.live_socket import UnconnectedSocket
from starlette.datastructures import State
from dataclasses import dataclass
from unittest.mock import Mock, AsyncMock
import asyncio


# =============================================================================
# Step 1: Define Your Services
# =============================================================================

class Database:
    """Your database service."""
    async def get_user(self, user_id: int) -> dict:
        return {"id": user_id, "name": f"User {user_id}"}


class Cache:
    """Your cache service."""
    async def get(self, key: str) -> str | None:
        return f"cached:{key}"


# =============================================================================
# Step 2: Create Type-Safe Service Locator (One Time Setup)
# =============================================================================

class Services:
    """
    Type-safe service locator.

    Add a @property for each service you want type-safe access to.
    """

    def __init__(self, state: State):
        self._state = state

    @property
    def database(self) -> Database:
        """Get database with full type checking."""
        return self._state.database

    @property
    def cache(self) -> Cache:
        """Get cache with full type checking."""
        return self._state.cache


def services(socket) -> Services:
    """Helper to get type-safe services from socket."""
    return Services(socket.state)


# =============================================================================
# Step 3: Use in Your LiveViews - Full Type Safety!
# =============================================================================

@dataclass
class UserContext:
    user: dict
    cached_data: str | None


class UserView(LiveView[UserContext]):
    """Example view using type-safe services."""

    async def mount(self, socket: LiveViewSocket[UserContext], session):
        # Get services with full type safety
        svc = services(socket)

        # ✅ Your IDE autocompletes these methods
        # ✅ Type checker validates the arguments
        # ✅ You get Database type, not Any
        user = await svc.database.get_user(session.get("user_id", 1))
        cached = await svc.cache.get(f"user:{user['id']}")

        socket.context = UserContext(user=user, cached_data=cached)

    async def render(self, context: UserContext, meta):
        return f"""
        <div>
            <h1>{context.user['name']}</h1>
            <p>Cached: {context.cached_data}</p>
        </div>
        """


# =============================================================================
# Demonstration
# =============================================================================

async def demo():
    """Show it in action!"""
    print("=" * 60)
    print("Type-Safe State Pattern Demo")
    print("=" * 60)

    # Setup socket with services
    socket = UnconnectedSocket()
    socket.state.database = Database()
    socket.state.cache = Cache()

    # Test the view
    view = UserView()
    await view.mount(socket, {"user_id": 42})

    print(f"\n✅ User loaded: {socket.context.user}")
    print(f"✅ Cached data: {socket.context.cached_data}")

    # Render
    html = await view.render(socket.context, None)
    print(f"\n✅ Rendered HTML:\n{html}")

    print("\n" + "=" * 60)
    print("Type Safety Benefits:")
    print("=" * 60)
    print("1. IDE autocomplete for service methods")
    print("2. Type checker catches typos at dev time")
    print("3. Method signature validation")
    print("4. Refactoring support")
    print("5. Better documentation via types")


async def demo_with_mocks():
    """Show testing with mocks."""
    print("\n" + "=" * 60)
    print("Testing with Mocks (Still Type-Safe!)")
    print("=" * 60)

    # Create mocks
    mock_db = Mock(spec=Database)
    mock_db.get_user = AsyncMock(return_value={"id": 1, "name": "Mock User"})

    mock_cache = Mock(spec=Cache)
    mock_cache.get = AsyncMock(return_value="mock_cached_data")

    # Inject mocks
    socket = UnconnectedSocket()
    socket.state.database = mock_db
    socket.state.cache = mock_cache

    # Test the view
    view = UserView()
    await view.mount(socket, {"user_id": 1})

    print(f"\n✅ Mock user: {socket.context.user}")
    print(f"✅ Mock cached: {socket.context.cached_data}")
    print(f"✅ Database called: {mock_db.get_user.called}")
    print(f"✅ Cache called: {mock_cache.get.called}")


if __name__ == "__main__":
    asyncio.run(demo())
    asyncio.run(demo_with_mocks())

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print("""
The pattern is simple:

1. Define a Services class with @property methods
2. Use services(socket) to get type-safe access
3. Enjoy full IDE support and type checking!

No runtime overhead, just better developer experience.
    """)
