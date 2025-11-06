"""
Simple test script to verify DI integration works.

This tests the svcs integration. Run with:
    poetry run python test_di.py
"""
import asyncio
from pyview import PyView
from pyview.integrations.svcs_integration import configure_svcs, get_services
from pyview.live_view import LiveView
from pyview.live_socket import UnconnectedSocket, LiveViewSocket
from dataclasses import dataclass


# Simple test services
class TestDatabase:
    def __init__(self):
        self.name = "TestDB"

    def query(self):
        return "data"


class TestCache:
    def __init__(self):
        self.name = "TestCache"

    def get(self, key):
        return f"cached_{key}"


@dataclass
class TestContext:
    message: str = ""


class TestLiveView(LiveView[TestContext]):
    async def mount(self, socket: LiveViewSocket[TestContext], session):
        # Test getting services
        db, cache = await get_services(socket, TestDatabase, TestCache)

        socket.context = TestContext(
            message=f"DB: {db.name}, Cache: {cache.name}, Query: {db.query()}"
        )

    async def render(self, context: TestContext, meta):
        return f"<div>{context.message}</div>"


# Test the integration
async def test_di():
    print("Creating PyView app...")
    app = PyView()

    @configure_svcs(app)
    def register_services(registry):
        print("Registering services with svcs...")
        registry.register_factory(TestDatabase, TestDatabase)
        registry.register_factory(TestCache, TestCache)

    # Add the test view
    app.add_live_view("/test", TestLiveView)

    print("✅ App created successfully!")
    print("✅ Services registered!")
    print("✅ LiveView added!")

    # Run the lifespan context to initialize the registry
    async with app.router.lifespan_context(app):
        print("✅ Lifespan initialized!")
        print("✅ svcs registry available on app.state")

        # Test with WebSocket-style access (socket.state)
        view = TestLiveView()
        from unittest.mock import Mock
        from starlette.websockets import WebSocket
        from starlette.datastructures import State

        # Create a mock websocket that has app.state with svcs_registry
        mock_ws = Mock(spec=WebSocket)
        mock_ws.app = app

        from pyview.live_socket import ConnectedLiveViewSocket
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from pyview.instrumentation import NoOpInstrumentation

        scheduler = AsyncIOScheduler()
        socket = ConnectedLiveViewSocket(
            mock_ws, "test", view, scheduler, NoOpInstrumentation()
        )

        print("Testing mount with WebSocket-style socket...")
        await view.mount(socket, {})

        print(f"✅ Mount successful! Context message: {socket.context.message}")

        # Render the view
        from pyview.meta import PyViewMeta
        result = await view.render(socket.context, PyViewMeta())
        print(f"✅ Render successful! Output: {result}")

        print("\n🎉 All tests passed!")


if __name__ == "__main__":
    asyncio.run(test_di())
