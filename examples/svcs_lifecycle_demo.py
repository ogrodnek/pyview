"""
Understanding svcs Lifecycle and Comparison with RequestContext Pattern

This demonstrates:
1. How svcs manages service lifecycle
2. Comparison with socket.state pattern
3. When to use each approach
"""
import asyncio
import svcs
from contextlib import asynccontextmanager


# =============================================================================
# svcs Lifecycle Explained
# =============================================================================

print("=" * 70)
print("SVCS LIFECYCLE DEMONSTRATION")
print("=" * 70)


class Database:
    """Example service with lifecycle."""

    def __init__(self, name: str):
        self.name = name
        print(f"  ✅ Database '{name}' created")

    async def query(self, sql: str):
        return f"Results from {self.name}"

    async def close(self):
        print(f"  🔒 Database '{self.name}' closed")


async def demo_svcs_lifecycle():
    """Shows how svcs manages service lifecycle."""

    print("\n1. Creating registry and registering factory...")

    registry = svcs.Registry()

    # Factory function - called when service is needed
    def create_db():
        print("  📦 Factory called: creating database")
        return Database("MyDB")

    registry.register_factory(Database, create_db)
    print("  ✅ Factory registered (but NOT called yet!)")

    print("\n2. Creating container...")
    container = svcs.Container(registry)
    print("  ✅ Container created (services still NOT created!)")

    print("\n3. First access - service created NOW...")
    db1 = await container.aget(Database)
    print(f"  ✅ Got database: {db1.name}")

    print("\n4. Second access - SAME instance returned...")
    db2 = await container.aget(Database)
    print(f"  ✅ Got database: {db2.name}")
    print(f"  ✅ Same instance? {db1 is db2}")

    print("\n5. Container cleanup...")
    await container.aclose()
    print("  ✅ Container closed")

    print("\n" + "=" * 70)
    print("KEY POINTS ABOUT SVCS:")
    print("=" * 70)
    print("✓ Lazy instantiation - services created on first access")
    print("✓ Singleton per container - same instance on subsequent access")
    print("✓ Automatic cleanup - resources cleaned up when container closes")
    print("✓ Scoped lifecycle - container = request/connection scope")


# =============================================================================
# Comparison: svcs vs socket.state Pattern
# =============================================================================

async def demo_comparison():
    """Compare svcs with socket.state pattern."""

    print("\n" + "=" * 70)
    print("COMPARISON: svcs vs socket.state")
    print("=" * 70)

    # With svcs
    print("\n📦 WITH SVCS:")
    print("-" * 70)

    registry = svcs.Registry()

    def db_factory():
        print("    Creating DB via factory")
        return Database("svcs-db")

    registry.register_factory(Database, db_factory)
    container = svcs.Container(registry)

    print("  1. Container created")
    print("  2. Service NOT created yet")

    db = await container.aget(Database)
    print("  3. Service created on first access")

    db2 = await container.aget(Database)
    print(f"  4. Same instance returned: {db is db2}")

    await container.aclose()

    # With socket.state
    print("\n📦 WITH SOCKET.STATE:")
    print("-" * 70)

    from starlette.datastructures import State

    state = State()

    print("  1. State created")

    # Eagerly create service
    state.database = Database("state-db")
    print("  2. Service created EAGERLY (when assigned)")

    db = state.database
    print("  3. Access service")

    db2 = state.database
    print(f"  4. Same instance returned: {db is db2}")

    # Manual cleanup if needed
    if hasattr(state.database, "close"):
        await state.database.close()
    print("  5. Manual cleanup (if needed)")

    print("\n" + "=" * 70)
    print("KEY DIFFERENCES:")
    print("=" * 70)
    print("svcs:")
    print("  ✓ Lazy instantiation")
    print("  ✓ Factory-based (can be complex)")
    print("  ✓ Automatic cleanup")
    print("  ✓ Type-safe with get_services()")
    print()
    print("socket.state:")
    print("  ✓ Eager instantiation (or you control when)")
    print("  ✓ Direct assignment (simpler)")
    print("  ✓ Manual cleanup (if needed)")
    print("  ✓ Type-safe with RequestContext wrapper")


# =============================================================================
# Pattern: Don't Store Services as Instance Variables!
# =============================================================================

async def demo_no_instance_vars():
    """Show the pattern of accessing services from socket directly."""

    print("\n" + "=" * 70)
    print("PATTERN: Access Services from Socket (No self.x = ...)")
    print("=" * 70)

    from pyview import LiveView
    from pyview.live_socket import UnconnectedSocket
    from dataclasses import dataclass

    @dataclass
    class UserContext:
        user: dict

    # ❌ OLD PATTERN (storing on self)
    print("\n❌ OLD PATTERN (Don't do this):")
    print("-" * 70)

    class OldPatternView(LiveView[UserContext]):
        async def mount(self, socket, session):
            # ❌ Store services as instance variables
            self.database = socket.state.database
            self.cache = socket.state.cache

            user = await self.database.get_user(1)
            socket.context = UserContext(user=user)

        async def handle_event(self, event, payload, socket):
            # ❌ Access via self
            user = await self.database.get_user(2)

    print("  class OldPatternView(LiveView):")
    print("      async def mount(self, socket, session):")
    print("          self.database = socket.state.database  # ❌ Don't do this")
    print("          self.cache = socket.state.cache")
    print()
    print("      async def handle_event(self, event, payload, socket):")
    print("          user = await self.database.get_user(2)  # ❌ Via self")

    # ✅ NEW PATTERN (access from socket)
    print("\n✅ NEW PATTERN (Do this):")
    print("-" * 70)

    class RequestContext:
        def __init__(self, socket):
            self._socket = socket

        @property
        def database(self) -> Database:
            return self._socket.state.database

        @property
        def cache(self):
            return self._socket.state.cache

    def ctx(socket):
        return RequestContext(socket)

    class NewPatternView(LiveView[UserContext]):
        async def mount(self, socket, session):
            # ✅ Access services directly from socket
            c = ctx(socket)
            user = await c.database.get_user(1)
            socket.context = UserContext(user=user)

        async def handle_event(self, event, payload, socket):
            # ✅ Access services from socket when needed
            c = ctx(socket)
            user = await c.database.get_user(2)
            socket.context.user = user

    print("  class NewPatternView(LiveView):")
    print("      async def mount(self, socket, session):")
    print("          c = ctx(socket)  # ✅ Get context from socket")
    print("          user = await c.database.get_user(1)")
    print()
    print("      async def handle_event(self, event, payload, socket):")
    print("          c = ctx(socket)  # ✅ Get context from socket")
    print("          user = await c.database.get_user(2)")

    print("\n" + "=" * 70)
    print("WHY THIS IS BETTER:")
    print("=" * 70)
    print("✓ No instance state - LiveView stays stateless")
    print("✓ Services available in ALL methods that get socket")
    print("✓ Easier to test - just mock socket.state")
    print("✓ More functional style - socket is the source of truth")
    print("✓ Similar to Phoenix LiveView's socket.assigns pattern")


# =============================================================================
# When to Use Each Approach
# =============================================================================

def print_recommendations():
    """Print recommendations for when to use each approach."""

    print("\n" + "=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)

    print("""
┌─────────────────────────────────────────────────────────────────────┐
│ USE socket.state + RequestContext WHEN:                            │
├─────────────────────────────────────────────────────────────────────┤
│ ✓ You want simplicity                                              │
│ ✓ You control service instantiation                                │
│ ✓ Your services don't need complex factories                       │
│ ✓ You want direct, obvious code                                    │
│ ✓ You want maximum testability                                     │
│                                                                     │
│ Example:                                                            │
│   c = ctx(socket)                                                   │
│   user = await c.database.get_user(1)                              │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ USE svcs WHEN:                                                      │
├─────────────────────────────────────────────────────────────────────┤
│ ✓ You need lazy instantiation                                      │
│ ✓ You have complex service factories                               │
│ ✓ You need automatic resource cleanup                              │
│ ✓ You want to override services in different contexts              │
│ ✓ You're building a large app with many services                   │
│                                                                     │
│ Example:                                                            │
│   db, cache = await get_services(socket, Database, Cache)          │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ HYBRID APPROACH:                                                    │
├─────────────────────────────────────────────────────────────────────┤
│ You can even use BOTH:                                             │
│                                                                     │
│ 1. Use socket.state for simple services (config, etc.)             │
│ 2. Use svcs for complex services (DB with connection pooling)      │
│ 3. Create RequestContext that wraps both                           │
│                                                                     │
│ Best of both worlds!                                                │
└─────────────────────────────────────────────────────────────────────┘
    """)


# =============================================================================
# Run All Demos
# =============================================================================

async def main():
    await demo_svcs_lifecycle()
    await demo_comparison()
    await demo_no_instance_vars()
    print_recommendations()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
PyView gives you CHOICE:

1. Simple apps: Use socket.state + RequestContext
   - Direct, obvious, testable
   - Full type safety with simple wrapper

2. Complex apps: Use svcs integration
   - Lazy loading, automatic cleanup
   - Complex factory support

3. Hybrid: Use both!
   - Best tool for each job

Either way, you get:
✓ Type safety
✓ Testability
✓ Clean API
✓ No self.x = ... assignments needed!
    """)


if __name__ == "__main__":
    asyncio.run(main())
