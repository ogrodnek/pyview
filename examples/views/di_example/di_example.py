"""
Example LiveView demonstrating dependency injection with svcs.
"""
from pyview import LiveView, LiveViewSocket
from pyview.di import get_services
from dataclasses import dataclass, field
from .services import Database, TimeService, MessageService


@dataclass
class DIExampleContext:
    users: list[dict] = field(default_factory=list)
    current_time: str = ""
    message: str = ""
    selected_user: str = "Alice"


class DIExampleLiveView(LiveView[DIExampleContext]):
    """
    Dependency Injection Example

    Demonstrates how to use dependency injection with PyView.
    Services are injected using get_services() in the mount method.
    """

    async def mount(self, socket: LiveViewSocket[DIExampleContext], session):
        # Get multiple services at once
        db, time_service, msg_service = await get_services(
            socket,
            Database,
            TimeService,
            MessageService
        )

        # Use the services
        users = db.list_users()
        current_time = time_service.get_current_time()
        message = msg_service.greet("PyView Developer")

        # Set the context
        socket.context = DIExampleContext(
            users=users,
            current_time=current_time,
            message=message
        )

    async def render(self, context: DIExampleContext, meta):
        return f"""
        <div class="max-w-4xl mx-auto px-4 py-8">
            <div class="bg-white rounded-lg shadow-md p-6 mb-6">
                <h1 class="text-3xl font-bold text-gray-900 mb-4">
                    Dependency Injection Example
                </h1>
                <p class="text-gray-600 mb-2">
                    {context.message}
                </p>
                <p class="text-sm text-gray-500">
                    Current time (from TimeService): {context.current_time}
                </p>
            </div>

            <div class="bg-white rounded-lg shadow-md p-6">
                <h2 class="text-xl font-semibold text-gray-900 mb-4">
                    Users (from Database service)
                </h2>
                <div class="space-y-3">
                    {"".join([f'''
                    <div class="border border-gray-200 rounded-lg p-4 hover:bg-gray-50">
                        <div class="flex items-center justify-between">
                            <div>
                                <h3 class="font-medium text-gray-900">{user['name']}</h3>
                                <p class="text-sm text-gray-500">{user['email']}</p>
                            </div>
                            <span class="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                                ID: {user['id']}
                            </span>
                        </div>
                    </div>
                    ''' for user in context.users])}
                </div>
            </div>

            <div class="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
                <h3 class="font-semibold text-blue-900 mb-2">How it works</h3>
                <ul class="text-sm text-blue-800 space-y-1">
                    <li>• Services are registered in the app setup using <code>configure_di()</code></li>
                    <li>• Services are retrieved in mount() using <code>get_services()</code></li>
                    <li>• Services are automatically cleaned up when the view disconnects</li>
                    <li>• Works with both HTTP requests and WebSocket connections</li>
                </ul>
            </div>
        </div>
        """
