"""
Test that svcs containers are automatically cleaned up for WebSocket connections.
"""
import asyncio
from contextlib import asynccontextmanager
from pyview.live_socket import ConnectedLiveViewSocket
from pyview.live_view import LiveView
from starlette.applications import Starlette
from starlette.datastructures import State
from unittest.mock import Mock, AsyncMock

try:
    import pytest
except ImportError:
    pytest = None


class TrackableDatabase:
    """Database that tracks creation and cleanup"""

    instances_created = 0
    instances_closed = 0

    def __init__(self):
        self.name = f"db-{TrackableDatabase.instances_created}"
        TrackableDatabase.instances_created += 1
        print(f"  ✅ {self.name} created")

    async def __aenter__(self):
        print(f"  🔓 {self.name} entered (connection opened)")
        return self

    async def __aexit__(self, *args):
        print(f"  🔒 {self.name} exited (connection closed)")
        TrackableDatabase.instances_closed += 1


async def create_db():
    """Factory that returns an async context manager"""
    return TrackableDatabase()


def reset_counters():
    """Reset class-level counters before each test"""
    TrackableDatabase.instances_created = 0
    TrackableDatabase.instances_closed = 0


async def test_svcs_container_reused_and_cleaned_up():
    """Test that svcs container is created once per connection and cleaned up automatically"""
    reset_counters()

    try:
        import svcs
        from pyview.integrations.svcs_integration import get_services
    except ImportError:
        print("⚠️  svcs not installed, skipping test")
        return

    print("\n" + "="*70)
    print("TEST: svcs container reuse and automatic cleanup")
    print("="*70)

    # Create a mock WebSocket connection
    mock_websocket = Mock()
    mock_websocket.app = Starlette()

    # Set up svcs registry on app state
    registry = svcs.Registry()
    registry.register_factory(TrackableDatabase, create_db)
    mock_websocket.app.state.svcs_registry = registry

    # Create a socket (simulating WebSocket connection)
    mock_liveview = Mock(spec=LiveView)
    mock_liveview.disconnect = AsyncMock()
    socket = ConnectedLiveViewSocket(
        websocket=mock_websocket,
        topic="test:topic",
        liveview=mock_liveview,
        scheduler=Mock(),
        instrumentation=None
    )

    print("\n📞 Connection established")

    # Get the same service multiple times
    print("\n🔍 First get_services call:")
    db1 = await get_services(socket, TrackableDatabase)
    assert TrackableDatabase.instances_created == 1, "Should create instance on first access"
    assert TrackableDatabase.instances_closed == 0, "Should not close yet"

    print("\n🔍 Second get_services call:")
    db2 = await get_services(socket, TrackableDatabase)
    assert TrackableDatabase.instances_created == 1, "Should reuse same instance"
    assert db1 is db2, "Should return same instance (singleton per container)"

    print("\n🔍 Third get_services call:")
    db3 = await get_services(socket, TrackableDatabase)
    assert TrackableDatabase.instances_created == 1, "Should still reuse same instance"
    assert db1 is db3, "Should return same instance"

    # Verify container is stored on socket
    assert hasattr(socket, '_svcs_container'), "Container should be stored on socket"

    print("\n📞 Closing connection...")
    await socket.close()

    print("\n✅ Verification:")
    assert TrackableDatabase.instances_closed == 1, "Should have called __aexit__ on cleanup"
    print(f"  ✅ Created {TrackableDatabase.instances_created} instance(s)")
    print(f"  ✅ Cleaned up {TrackableDatabase.instances_closed} instance(s)")
    print(f"  ✅ Context manager properly entered and exited")

    # Clean up registry
    await registry.aclose()

    print("\n" + "="*70)
    print("✅ TEST PASSED: Container reused and cleaned up automatically!")
    print("="*70)


async def test_multiple_connections_get_separate_containers():
    """Test that different WebSocket connections get separate containers"""
    reset_counters()

    try:
        import svcs
        from pyview.integrations.svcs_integration import get_services
    except ImportError:
        print("⚠️  svcs not installed, skipping test")
        return

    print("\n" + "="*70)
    print("TEST: Multiple connections get separate containers")
    print("="*70)

    # Create app with registry
    app = Starlette()
    registry = svcs.Registry()
    registry.register_factory(TrackableDatabase, create_db)
    app.state.svcs_registry = registry

    # Create two separate connections
    mock_liveview = Mock(spec=LiveView)
    mock_liveview.disconnect = AsyncMock()

    mock_ws1 = Mock()
    mock_ws1.app = app
    socket1 = ConnectedLiveViewSocket(
        websocket=mock_ws1,
        topic="test:socket1",
        liveview=mock_liveview,
        scheduler=Mock(),
        instrumentation=None
    )

    mock_ws2 = Mock()
    mock_ws2.app = app
    socket2 = ConnectedLiveViewSocket(
        websocket=mock_ws2,
        topic="test:socket2",
        liveview=mock_liveview,
        scheduler=Mock(),
        instrumentation=None
    )

    print("\n📞 Connection 1 established")
    db1 = await get_services(socket1, TrackableDatabase)
    assert TrackableDatabase.instances_created == 1

    print("\n📞 Connection 2 established")
    db2 = await get_services(socket2, TrackableDatabase)
    assert TrackableDatabase.instances_created == 2, "Each connection gets its own instance"
    assert db1 is not db2, "Different connections get different instances"

    print(f"\n🔍 Connection 1 DB: {db1.name}")
    print(f"🔍 Connection 2 DB: {db2.name}")

    print("\n📞 Closing connection 1...")
    await socket1.close()
    assert TrackableDatabase.instances_closed == 1, "Should clean up connection 1 only"

    print("\n📞 Closing connection 2...")
    await socket2.close()
    assert TrackableDatabase.instances_closed == 2, "Should clean up connection 2"

    # Clean up registry
    await registry.aclose()

    print("\n" + "="*70)
    print("✅ TEST PASSED: Each connection gets separate container!")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(test_svcs_container_reused_and_cleaned_up())
    asyncio.run(test_multiple_connections_get_separate_containers())
