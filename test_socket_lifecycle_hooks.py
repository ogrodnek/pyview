"""
Test the generic socket lifecycle hook system (socket.register_cleanup).

This demonstrates how integrations and user code can register cleanup handlers
without PyView needing to know about specific integrations.
"""
import asyncio
from pyview.live_socket import ConnectedLiveViewSocket
from pyview.live_view import LiveView
from starlette.applications import Starlette
from unittest.mock import Mock, AsyncMock


class CustomResource:
    """Example custom resource that needs cleanup"""

    def __init__(self, name):
        self.name = name
        self.closed = False
        print(f"  ✅ {name} created")

    def close(self):
        self.closed = True
        print(f"  🔒 {self.name} closed (sync)")


class AsyncResource:
    """Example async resource that needs cleanup"""

    def __init__(self, name):
        self.name = name
        self.closed = False
        print(f"  ✅ {name} created")

    async def aclose(self):
        self.closed = True
        print(f"  🔒 {self.name} closed (async)")


async def test_sync_cleanup():
    """Test that sync cleanup callbacks work"""
    print("\n" + "="*70)
    print("TEST: Sync cleanup callbacks")
    print("="*70)

    # Create socket
    mock_websocket = Mock()
    mock_websocket.app = Starlette()
    mock_liveview = Mock(spec=LiveView)
    mock_liveview.disconnect = AsyncMock()

    socket = ConnectedLiveViewSocket(
        websocket=mock_websocket,
        topic="test:topic",
        liveview=mock_liveview,
        scheduler=Mock(),
        instrumentation=None
    )

    print("\n📦 Creating resources and registering cleanup...")
    resource1 = CustomResource("resource1")
    resource2 = CustomResource("resource2")

    # Register cleanup handlers
    socket.register_cleanup(resource1.close)
    socket.register_cleanup(resource2.close)

    print("\n📞 Closing socket...")
    await socket.close()

    print("\n✅ Verification:")
    assert resource1.closed, "resource1 should be closed"
    assert resource2.closed, "resource2 should be closed"
    print(f"  ✅ Both sync resources closed")

    print("\n" + "="*70)
    print("✅ TEST PASSED!")
    print("="*70)


async def test_async_cleanup():
    """Test that async cleanup callbacks work"""
    print("\n" + "="*70)
    print("TEST: Async cleanup callbacks")
    print("="*70)

    mock_websocket = Mock()
    mock_websocket.app = Starlette()
    mock_liveview = Mock(spec=LiveView)
    mock_liveview.disconnect = AsyncMock()

    socket = ConnectedLiveViewSocket(
        websocket=mock_websocket,
        topic="test:topic",
        liveview=mock_liveview,
        scheduler=Mock(),
        instrumentation=None
    )

    print("\n📦 Creating async resources and registering cleanup...")
    resource1 = AsyncResource("async_resource1")
    resource2 = AsyncResource("async_resource2")

    # Register async cleanup handlers
    async def cleanup1():
        await resource1.aclose()
    async def cleanup2():
        await resource2.aclose()
    socket.register_cleanup(cleanup1)
    socket.register_cleanup(cleanup2)

    print("\n📞 Closing socket...")
    await socket.close()

    print("\n✅ Verification:")
    assert resource1.closed, "async_resource1 should be closed"
    assert resource2.closed, "async_resource2 should be closed"
    print(f"  ✅ Both async resources closed")

    print("\n" + "="*70)
    print("✅ TEST PASSED!")
    print("="*70)


async def test_mixed_cleanup():
    """Test that sync and async cleanup callbacks can be mixed"""
    print("\n" + "="*70)
    print("TEST: Mixed sync and async cleanup callbacks")
    print("="*70)

    mock_websocket = Mock()
    mock_websocket.app = Starlette()
    mock_liveview = Mock(spec=LiveView)
    mock_liveview.disconnect = AsyncMock()

    socket = ConnectedLiveViewSocket(
        websocket=mock_websocket,
        topic="test:topic",
        liveview=mock_liveview,
        scheduler=Mock(),
        instrumentation=None
    )

    print("\n📦 Creating mixed resources and registering cleanup...")
    sync_resource = CustomResource("sync_resource")
    async_resource = AsyncResource("async_resource")

    # Register mixed cleanup handlers
    socket.register_cleanup(sync_resource.close)
    async def cleanup_async():
        await async_resource.aclose()
    socket.register_cleanup(cleanup_async)

    print("\n📞 Closing socket...")
    await socket.close()

    print("\n✅ Verification:")
    assert sync_resource.closed, "sync_resource should be closed"
    assert async_resource.closed, "async_resource should be closed"
    print(f"  ✅ Both sync and async resources closed")

    print("\n" + "="*70)
    print("✅ TEST PASSED!")
    print("="*70)


async def test_cleanup_errors_dont_break_other_cleanups():
    """Test that errors in one cleanup don't prevent other cleanups"""
    print("\n" + "="*70)
    print("TEST: Cleanup errors are isolated")
    print("="*70)

    mock_websocket = Mock()
    mock_websocket.app = Starlette()
    mock_liveview = Mock(spec=LiveView)
    mock_liveview.disconnect = AsyncMock()

    socket = ConnectedLiveViewSocket(
        websocket=mock_websocket,
        topic="test:topic",
        liveview=mock_liveview,
        scheduler=Mock(),
        instrumentation=None
    )

    print("\n📦 Registering cleanup with errors...")
    resource1 = CustomResource("resource1")
    resource2 = CustomResource("resource2")

    def failing_cleanup():
        print("  ⚠️  Cleanup error (this should be caught)")
        raise RuntimeError("Intentional error")

    # Register cleanups: good, bad, good
    socket.register_cleanup(resource1.close)
    socket.register_cleanup(failing_cleanup)
    socket.register_cleanup(resource2.close)

    print("\n📞 Closing socket (error should be logged but not raised)...")
    await socket.close()

    print("\n✅ Verification:")
    assert resource1.closed, "resource1 should be closed despite error in next cleanup"
    assert resource2.closed, "resource2 should be closed despite error in previous cleanup"
    print(f"  ✅ Both resources closed despite error")

    print("\n" + "="*70)
    print("✅ TEST PASSED!")
    print("="*70)


async def test_custom_integration_pattern():
    """
    Demonstrate how a custom integration would use register_cleanup.

    This shows the pattern that svcs and other integrations can follow.
    """
    print("\n" + "="*70)
    print("DEMO: Custom integration pattern")
    print("="*70)

    # Example: Custom database integration
    class DatabaseIntegration:
        """Example integration that uses socket lifecycle hooks"""

        @staticmethod
        async def get_connection(socket):
            """Get or create a database connection for this socket"""
            if not hasattr(socket, '_db_connection'):
                print("  📦 Creating database connection...")
                connection = AsyncResource("database_connection")
                socket._db_connection = connection

                # Register cleanup - no need for socket to know about databases!
                async def cleanup_connection():
                    await connection.aclose()
                socket.register_cleanup(cleanup_connection)
                print("  ✅ Cleanup registered")

            return socket._db_connection

    mock_websocket = Mock()
    mock_websocket.app = Starlette()
    mock_liveview = Mock(spec=LiveView)
    mock_liveview.disconnect = AsyncMock()

    socket = ConnectedLiveViewSocket(
        websocket=mock_websocket,
        topic="test:topic",
        liveview=mock_liveview,
        scheduler=Mock(),
        instrumentation=None
    )

    print("\n📞 Connection established...")

    # Get connection multiple times (reuses same instance)
    print("\n🔍 First call to get_connection:")
    conn1 = await DatabaseIntegration.get_connection(socket)

    print("\n🔍 Second call to get_connection (should reuse):")
    conn2 = await DatabaseIntegration.get_connection(socket)
    assert conn1 is conn2, "Should reuse same connection"
    print("  ✅ Reused existing connection")

    print("\n📞 Closing connection...")
    await socket.close()

    print("\n✅ Verification:")
    assert conn1.closed, "Connection should be closed"
    print("  ✅ Database connection cleaned up automatically")

    print("\n" + "="*70)
    print("✅ DEMO COMPLETE!")
    print("="*70)
    print("""
Key takeaway:
- Integrations call socket.register_cleanup() when creating resources
- Socket calls all cleanup callbacks automatically in close()
- No tight coupling - socket doesn't know about specific integrations
- Same pattern works for svcs, database pools, file handles, etc.
    """)


if __name__ == "__main__":
    asyncio.run(test_sync_cleanup())
    asyncio.run(test_async_cleanup())
    asyncio.run(test_mixed_cleanup())
    asyncio.run(test_cleanup_errors_dont_break_other_cleanups())
    asyncio.run(test_custom_integration_pattern())

    print("\n" + "="*70)
    print("ALL TESTS PASSED!")
    print("="*70)
