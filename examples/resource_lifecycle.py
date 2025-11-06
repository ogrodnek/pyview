"""
Resource Lifecycle and Cleanup in PyView

This demonstrates:
1. What gets cleaned up automatically
2. What you need to clean up manually
3. Best practices for resource management
4. Understanding socket.state scoping
"""
import asyncio
from pyview import PyView, LiveView, LiveViewSocket
from pyview.live_socket import UnconnectedSocket, ConnectedLiveViewSocket
from dataclasses import dataclass
from contextlib import asynccontextmanager


# =============================================================================
# Understanding socket.state Scoping
# =============================================================================

print("=" * 70)
print("SOCKET.STATE SCOPING")
print("=" * 70)

"""
CRITICAL INSIGHT:

UnconnectedSocket.state (HTTP):
- Returns request.state
- Scoped to the HTTP REQUEST
- Lives only for the duration of the request
- Cleaned up when request completes

ConnectedLiveViewSocket.state (WebSocket):
- Returns app.state (application-wide!)
- Scoped to the ENTIRE APPLICATION
- Shared across ALL WebSocket connections
- Lives for the entire app lifetime

This means:
✓ HTTP: Services on socket.state are per-request
✗ WebSocket: Services on socket.state are SHARED!

Solution: Store per-connection data elsewhere (see below)
"""


# =============================================================================
# What PyView Already Cleans Up
# =============================================================================

def show_automatic_cleanup():
    """PyView automatically cleans up these resources."""

    print("\n✅ AUTOMATIC CLEANUP (PyView handles this):")
    print("-" * 70)

    cleanup_list = """
1. Scheduled Jobs
   - socket.schedule_info()
   - All jobs removed in socket.close()

2. PubSub Subscriptions
   - socket.subscribe()
   - All subscriptions removed in socket.close()

3. Upload Manager
   - socket.allow_upload()
   - Manager closed in socket.close()

4. LiveView.disconnect() called
   - Your custom cleanup hook
   - Called automatically in socket.close()

5. WebSocket connection
   - Closed by Starlette/ASGI
   - No manual cleanup needed
"""

    print(cleanup_list)


# =============================================================================
# What You MIGHT Need to Clean Up
# =============================================================================

def show_manual_cleanup():
    """Resources you might need to clean up manually."""

    print("\n⚠️  POTENTIAL MANUAL CLEANUP:")
    print("-" * 70)

    manual_cleanup = """
1. Database Connections (if per-connection)
   - If stored on socket as instance variable
   - Close in disconnect()

2. File Handles
   - Any files opened during connection
   - Close in disconnect()

3. External API Clients
   - If holding sessions/connections
   - Close in disconnect()

4. Background Tasks
   - If spawned outside of schedule_info()
   - Cancel in disconnect()

5. Services with __aexit__
   - Context managers that weren't entered
   - Call cleanup in disconnect()
"""

    print(manual_cleanup)


# =============================================================================
# PATTERN 1: Services on app.state (Shared, Long-Lived)
# =============================================================================

class SharedDatabase:
    """Database connection pool shared across all connections."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.pool = []  # Imagine a connection pool
        print(f"  📦 SharedDatabase created")

    async def get_user(self, user_id: int):
        return {"id": user_id, "name": f"User {user_id}"}

    async def close(self):
        """Close the entire pool."""
        print(f"  🔒 SharedDatabase closed")


async def demo_shared_services():
    """Services on app.state are shared and long-lived."""

    print("\n" + "=" * 70)
    print("PATTERN 1: Shared Services (app.state)")
    print("=" * 70)

    from starlette.applications import Starlette

    app = Starlette()

    # Setup shared service (in app lifespan)
    @asynccontextmanager
    async def lifespan(app):
        print("\n📦 App starting - creating shared services...")
        app.state.database = SharedDatabase("postgresql://...")

        yield

        print("\n🔒 App shutting down - cleaning up shared services...")
        await app.state.database.close()

    app.router.lifespan_context = lifespan

    # Simulate app lifecycle
    async with app.router.lifespan_context(app):
        print("✅ App running")
        print("   app.state.database is SHARED across all connections")
        print("   ALL WebSocket connections see the SAME instance")

        # Simulate multiple connections accessing the same service
        from unittest.mock import Mock
        from starlette.websockets import WebSocket

        mock_ws = Mock(spec=WebSocket)
        mock_ws.app = app

        # Connection 1
        socket1 = ConnectedLiveViewSocket(
            mock_ws, "conn1", None, None, None
        )
        db1 = socket1.state.database
        print(f"\n   Connection 1: {id(db1)}")

        # Connection 2
        socket2 = ConnectedLiveViewSocket(
            mock_ws, "conn2", None, None, None
        )
        db2 = socket2.state.database
        print(f"   Connection 2: {id(db2)}")

        print(f"   Same instance? {db1 is db2}  ← YES! Shared!")

    print("\n✅ App stopped, services cleaned up")


# =============================================================================
# PATTERN 2: Per-Connection Resources (Manual Cleanup)
# =============================================================================

class PerConnectionDatabase:
    """Database connection specific to one WebSocket connection."""

    def __init__(self, connection_id: str):
        self.connection_id = connection_id
        print(f"  📦 PerConnectionDB created for {connection_id}")

    async def close(self):
        print(f"  🔒 PerConnectionDB closed for {self.connection_id}")


@dataclass
class UserContext:
    user: dict
    db: PerConnectionDatabase = None  # Per-connection resource!


class ResourceManagementView(LiveView[UserContext]):
    """View that properly manages per-connection resources."""

    async def mount(self, socket: LiveViewSocket[UserContext], session):
        # Create per-connection database
        # (Don't store on socket.state - that's app-wide!)
        db = PerConnectionDatabase(f"conn-{id(socket)}")

        socket.context = UserContext(
            user={"id": 1, "name": "Test"},
            db=db  # Store on context, not socket.state
        )

    async def disconnect(self, socket: LiveViewSocket[UserContext]):
        """Clean up per-connection resources."""
        print(f"\n🧹 Cleaning up connection {id(socket)}...")

        # Close per-connection database
        if socket.context.db:
            await socket.context.db.close()

    async def render(self, context: UserContext, meta):
        return "<div>User view</div>"


async def demo_per_connection_cleanup():
    """Show per-connection resource cleanup."""

    print("\n" + "=" * 70)
    print("PATTERN 2: Per-Connection Resources")
    print("=" * 70)

    from unittest.mock import Mock, AsyncMock
    from starlette.websockets import WebSocket
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from pyview.instrumentation import NoOpInstrumentation

    mock_ws = Mock(spec=WebSocket)
    mock_ws.app = PyView()

    view = ResourceManagementView()
    scheduler = AsyncIOScheduler()

    # Create connection
    socket = ConnectedLiveViewSocket(
        mock_ws, "test", view, scheduler, NoOpInstrumentation()
    )

    print("\n📞 Connection established...")
    await view.mount(socket, {"user_id": 1})

    print("\n📞 Connection active...")
    # ... connection doing work ...

    print("\n📞 Connection closing...")
    await socket.close()  # This calls disconnect()

    print("✅ Per-connection resources cleaned up")


# =============================================================================
# PATTERN 3: Using svcs (Automatic Per-Request Cleanup)
# =============================================================================

async def demo_svcs_cleanup():
    """svcs provides automatic cleanup."""

    print("\n" + "=" * 70)
    print("PATTERN 3: svcs (Automatic Cleanup)")
    print("=" * 70)

    import svcs

    class AutoCleanupDB:
        def __init__(self):
            print("  📦 AutoCleanupDB created")

        async def close(self):
            print("  🔒 AutoCleanupDB closed")

        async def __aenter__(self):
            print("  🔓 AutoCleanupDB entered")
            return self

        async def __aexit__(self, *args):
            print("  🔒 AutoCleanupDB exited (automatic cleanup)")
            await self.close()

    # Register with context manager
    registry = svcs.Registry()

    async def create_db():
        """Factory that returns a context manager."""
        return AutoCleanupDB()

    registry.register_factory(AutoCleanupDB, create_db)

    # Create container (per-request/connection)
    print("\n📦 Creating container...")
    container = svcs.Container(registry)

    print("\n📞 Getting service...")
    db = await container.aget(AutoCleanupDB)

    print("\n🔒 Closing container...")
    await container.aclose()  # Automatic cleanup!

    print("\n✅ svcs handled cleanup automatically")


# =============================================================================
# PATTERN 4: Using RequestContext with Cleanup
# =============================================================================

class ManagedRequestContext:
    """Request context that manages resource cleanup."""

    def __init__(self, socket):
        self._socket = socket
        self._resources = []  # Track resources for cleanup

    def register_cleanup(self, resource, cleanup_fn):
        """Register a resource for cleanup."""
        self._resources.append((resource, cleanup_fn))

    async def cleanup(self):
        """Clean up all registered resources."""
        for resource, cleanup_fn in self._resources:
            try:
                await cleanup_fn(resource)
            except Exception as e:
                print(f"Error cleaning up {resource}: {e}")

    @property
    def database(self):
        # Get or create database
        if not hasattr(self, '_db'):
            db = PerConnectionDatabase("managed")
            self._db = db
            # Register for cleanup
            self.register_cleanup(db, lambda d: d.close())
        return self._db


class ManagedView(LiveView):
    async def mount(self, socket, session):
        ctx = ManagedRequestContext(socket)
        # Store context for later cleanup
        socket._managed_ctx = ctx

        # Use services - they're tracked for cleanup
        db = ctx.database
        # ...

    async def disconnect(self, socket):
        """Clean up managed context."""
        if hasattr(socket, '_managed_ctx'):
            await socket._managed_ctx.cleanup()


# =============================================================================
# Best Practices Summary
# =============================================================================

def print_best_practices():
    print("\n" + "=" * 70)
    print("BEST PRACTICES")
    print("=" * 70)

    practices = """
┌──────────────────────────────────────────────────────────────────┐
│ 1. UNDERSTAND SCOPING                                            │
├──────────────────────────────────────────────────────────────────┤
│ • HTTP: socket.state = request.state (per-request)               │
│ • WebSocket: socket.state = app.state (app-wide!)                │
│                                                                  │
│ ✅ DO: Store shared services on app.state                        │
│ ❌ DON'T: Store per-connection data on app.state                 │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ 2. SHARED SERVICES (Connection Pools, Config)                   │
├──────────────────────────────────────────────────────────────────┤
│ • Create in app lifespan                                        │
│ • Store on app.state                                            │
│ • Clean up in lifespan exit                                     │
│                                                                  │
│ Example:                                                         │
│   @asynccontextmanager                                           │
│   async def lifespan(app):                                       │
│       app.state.db_pool = create_pool()                          │
│       yield                                                      │
│       await app.state.db_pool.close()                            │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ 3. PER-CONNECTION RESOURCES                                     │
├──────────────────────────────────────────────────────────────────┤
│ • Create in mount()                                              │
│ • Store on socket.context (NOT socket.state!)                   │
│ • Clean up in disconnect()                                       │
│                                                                  │
│ Example:                                                         │
│   async def mount(self, socket, session):                        │
│       socket.context.db_conn = await create_connection()         │
│                                                                  │
│   async def disconnect(self, socket):                            │
│       await socket.context.db_conn.close()                       │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ 4. USE svcs FOR AUTOMATIC CLEANUP                               │
├──────────────────────────────────────────────────────────────────┤
│ • svcs manages cleanup automatically                             │
│ • Context managers are entered/exited                            │
│ • Container cleanup on close                                     │
│                                                                  │
│ Example:                                                         │
│   registry.register_factory(DB, create_db)                       │
│   db = await get_services(socket, DB)                            │
│   # Cleanup automatic when connection closes                     │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ 5. WHAT TO CLEAN UP MANUALLY                                    │
├──────────────────────────────────────────────────────────────────┤
│ ✅ Database connections (per-connection)                         │
│ ✅ File handles                                                  │
│ ✅ External API clients with state                               │
│ ✅ Background tasks you spawned                                  │
│                                                                  │
│ ❌ Scheduled jobs (PyView handles)                               │
│ ❌ PubSub subscriptions (PyView handles)                         │
│ ❌ Upload manager (PyView handles)                               │
│ ❌ WebSocket connection (Starlette handles)                      │
└──────────────────────────────────────────────────────────────────┘
"""

    print(practices)


# =============================================================================
# Run All Demos
# =============================================================================

async def main():
    show_automatic_cleanup()
    show_manual_cleanup()
    await demo_shared_services()
    await demo_per_connection_cleanup()
    await demo_svcs_cleanup()
    print_best_practices()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
PyView handles most cleanup automatically:
✅ Scheduled jobs
✅ PubSub subscriptions
✅ Upload manager
✅ Calls your disconnect() hook

You need to clean up in disconnect():
⚠️  Per-connection database connections
⚠️  File handles
⚠️  External API clients
⚠️  Background tasks

Best approach:
1. Shared services → app.state (cleanup in lifespan)
2. Per-connection → socket.context (cleanup in disconnect)
3. Use svcs for automatic cleanup
    """)


if __name__ == "__main__":
    asyncio.run(main())
