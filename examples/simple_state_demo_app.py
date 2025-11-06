"""
Simple demo app showing socket.state usage without external DI libraries.

This demonstrates the simplest way to pass dependencies to your LiveViews
using PyView's built-in socket.state feature.

Run with: uvicorn examples.simple_state_demo_app:app --reload
Then visit: http://localhost:8000
"""
from pyview import PyView, LiveView, LiveViewSocket
from dataclasses import dataclass
from datetime import datetime
from contextlib import asynccontextmanager


# Simple services (no external DI library needed)
class SimpleDatabase:
    def __init__(self):
        self.users = ["Alice", "Bob", "Charlie"]

    def get_users(self):
        return self.users


class SimpleConfig:
    def __init__(self):
        self.app_name = "PyView State Demo"
        self.version = "1.0.0"


# Context for the LiveView
@dataclass
class StateExampleContext:
    users: list[str]
    app_info: str
    timestamp: str


# LiveView that uses socket.state
class StateExampleLiveView(LiveView[StateExampleContext]):
    """
    Socket State Example

    Demonstrates using socket.state to access dependencies without
    any external DI library.
    """

    async def mount(self, socket: LiveViewSocket[StateExampleContext], session):
        # Access dependencies from socket.state
        # These were set up in the app lifespan
        db = socket.state.database
        config = socket.state.config

        # Use the dependencies
        users = db.get_users()
        app_info = f"{config.app_name} v{config.version}"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        socket.context = StateExampleContext(
            users=users,
            app_info=app_info,
            timestamp=timestamp
        )

    async def render(self, context: StateExampleContext, meta):
        return f"""
        <div class="max-w-4xl mx-auto px-4 py-8">
            <div class="bg-white rounded-lg shadow-md p-6 mb-6">
                <h1 class="text-3xl font-bold text-gray-900 mb-4">
                    {context.app_info}
                </h1>
                <p class="text-gray-600 mb-2">
                    Using socket.state - no external DI library needed!
                </p>
                <p class="text-sm text-gray-500">
                    Timestamp: {context.timestamp}
                </p>
            </div>

            <div class="bg-white rounded-lg shadow-md p-6">
                <h2 class="text-xl font-semibold text-gray-900 mb-4">
                    Users (from socket.state.database)
                </h2>
                <ul class="space-y-2">
                    {"".join([f'''
                    <li class="flex items-center p-3 bg-gray-50 rounded">
                        <span class="w-8 h-8 bg-blue-500 text-white rounded-full flex items-center justify-center mr-3">
                            {user[0]}
                        </span>
                        <span class="text-gray-800">{user}</span>
                    </li>
                    ''' for user in context.users])}
                </ul>
            </div>

            <div class="mt-6 bg-green-50 border border-green-200 rounded-lg p-4">
                <h3 class="font-semibold text-green-900 mb-2">How it works</h3>
                <ul class="text-sm text-green-800 space-y-1">
                    <li>• Dependencies are stored on <code>app.state</code> during startup</li>
                    <li>• Access them via <code>socket.state</code> in your LiveView</li>
                    <li>• No external DI library required</li>
                    <li>• Works with both HTTP and WebSocket connections</li>
                </ul>
            </div>
        </div>
        """


# Create the PyView app
app = PyView()


# Use lifespan to set up dependencies
@asynccontextmanager
async def lifespan(app):
    # Initialize dependencies
    print("Setting up dependencies...")
    app.state.database = SimpleDatabase()
    app.state.config = SimpleConfig()
    print("✅ Dependencies ready on app.state")

    yield

    # Cleanup (if needed)
    print("Shutting down...")


app.router.lifespan_context = lifespan

# Add the LiveView route
app.add_live_view("/", StateExampleLiveView)

print("🚀 Simple State Demo App is ready!")
print("   Visit: http://localhost:8000")
print("   No external DI library needed!")
