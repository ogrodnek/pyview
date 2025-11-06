"""
Simple test script to verify DI integration works.
"""
import asyncio
from pyview import PyView
from pyview.di import configure_di, get_services
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

    @configure_di(app)
    def register_services(registry):
        print("Registering services...")
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

        # Test that we can instantiate the view and mount it
        view = TestLiveView()
        socket = UnconnectedSocket()

        # Simulate having a DI container (like the HTTP handler would set)
        import svcs
        socket._svcs_container = svcs.Container(app.state.svcs_registry)

        print("Testing mount with DI...")
        await view.mount(socket, {})

        print(f"✅ Mount successful! Context message: {socket.context.message}")

        # Render the view
        from pyview.meta import PyViewMeta
        result = await view.render(socket.context, PyViewMeta())
        print(f"✅ Render successful! Output: {result}")

        print("\n🎉 All tests passed!")


if __name__ == "__main__":
    asyncio.run(test_di())
