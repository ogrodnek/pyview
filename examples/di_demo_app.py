"""
Simple demo app showcasing dependency injection with PyView.

Run with: uvicorn examples.di_demo_app:app --reload
Then visit: http://localhost:8000
"""
from pyview import PyView
from pyview.di import configure_di
from examples.views.di_example import DIExampleLiveView
from examples.views.di_example.services import (
    Database,
    TimeService,
    MessageService,
    create_database,
    create_time_service,
    create_message_service,
)

# Create the PyView app
app = PyView()


# Configure dependency injection
@configure_di(app)
def register_services(registry):
    """Register all services with the DI container."""
    # Register services with factory functions
    # These will be created once per request (HTTP) or connection (WebSocket)
    registry.register_factory(Database, create_database)
    registry.register_factory(TimeService, create_time_service)
    registry.register_factory(MessageService, create_message_service)

    print("✅ Services registered with DI container")


# Add the LiveView route
app.add_live_view("/", DIExampleLiveView)

print("🚀 DI Demo App is ready!")
print("   Visit: http://localhost:8000")
