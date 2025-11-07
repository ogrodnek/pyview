"""
Optional svcs integration for PyView.

This module provides helpers for integrating the svcs dependency injection
library with PyView. To use this, install svcs separately:

    pip install svcs

Example usage:

    from pyview import PyView
    from pyview.integrations.svcs_integration import configure_svcs, get_services

    app = PyView()

    @configure_svcs(app)
    def register_services(registry):
        registry.register_factory(Database, create_database)
        registry.register_factory(Cache, create_cache)

    class MyLiveView(LiveView[MyContext]):
        async def mount(self, socket, session):
            db, cache = await get_services(socket, Database, Cache)
            # Use your services...
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, TypeVar
from contextlib import asynccontextmanager

if TYPE_CHECKING:
    from starlette.applications import Starlette
    from pyview.live_socket import LiveViewSocket

T = TypeVar("T")


def configure_svcs(app: "Starlette"):
    """
    Decorator to configure svcs dependency injection for a PyView app.

    Usage:
        @configure_svcs(app)
        def register_services(registry: svcs.Registry):
            registry.register_factory(Database, create_database)
            registry.register_value(Config, config)

    Args:
        app: The PyView/Starlette application instance

    Returns:
        A decorator function that takes a registration function
    """
    try:
        import svcs
        import svcs.starlette
    except ImportError:
        raise ImportError(
            "svcs is not installed. Install it with: pip install svcs"
        )

    def decorator(register_fn):
        # Create a lifespan that sets up svcs
        @asynccontextmanager
        async def svcs_lifespan(app: "Starlette"):
            registry = svcs.Registry()

            # Call user's registration function
            register_fn(registry)

            # Store registry on app state for WebSocket connections
            app.state.svcs_registry = registry

            try:
                yield
            finally:
                await registry.aclose()

        # If app already has a lifespan, chain them
        existing_lifespan = app.router.lifespan_context

        if existing_lifespan:
            @asynccontextmanager
            async def combined_lifespan(app: "Starlette"):
                async with svcs_lifespan(app):
                    async with existing_lifespan(app):
                        yield
            app.router.lifespan_context = combined_lifespan
        else:
            app.router.lifespan_context = svcs_lifespan

        # Add svcs middleware to the app
        from starlette.middleware import Middleware
        app.user_middleware.insert(0, Middleware(svcs.starlette.SVCSMiddleware))
        app.middleware_stack = app.build_middleware_stack()

        return register_fn

    return decorator


async def get_services(socket: "LiveViewSocket", *service_types: type[T]) -> tuple[Any, ...]:
    """
    Get one or more services from the svcs container.

    This function works with both HTTP requests (UnconnectedSocket) and
    WebSocket connections (ConnectedLiveViewSocket).

    For WebSocket connections, the container is created once and reused for
    all service requests during the connection lifetime. It's automatically
    cleaned up when the connection closes.

    Args:
        socket: The LiveViewSocket (connected or unconnected)
        *service_types: One or more service types to retrieve

    Returns:
        If one service type is requested, returns the service directly.
        If multiple service types are requested, returns a tuple of services.

    Example:
        # Get single service
        db = await get_services(socket, Database)

        # Get multiple services
        db, cache, api = await get_services(socket, Database, Cache, WebAPI)
    """
    try:
        import svcs
    except ImportError:
        raise ImportError(
            "svcs is not installed. Install it with: pip install svcs"
        )

    if not service_types:
        raise ValueError("At least one service type must be provided")

    # Check if this is an HTTP request (UnconnectedSocket with request)
    # vs WebSocket (ConnectedLiveViewSocket)
    request = getattr(socket, 'request', None)

    if request is not None:
        # UnconnectedSocket - get from request state
        # SVCSMiddleware creates and cleans up the container automatically
        if not hasattr(request.state, 'svcs'):
            raise RuntimeError(
                "svcs not configured. Make sure SVCSMiddleware is installed "
                "and configure_svcs() was called."
            )
        container = request.state.svcs
    else:
        # ConnectedLiveViewSocket - create ONE container per connection
        # Store it on the socket itself (not on context which may not exist yet)
        if not hasattr(socket, '_svcs_container'):
            if not hasattr(socket.state, 'svcs_registry'):
                raise RuntimeError(
                    "svcs not configured. Make sure configure_svcs() was called."
                )
            container = svcs.Container(socket.state.svcs_registry)
            socket._svcs_container = container

            # Register cleanup callback - socket will call this automatically
            async def cleanup_container():
                await container.aclose()
            socket.register_cleanup(cleanup_container)

        container = socket._svcs_container

    # aget returns the service directly for single requests,
    # or a list for multiple requests
    services = await container.aget(*service_types)
    return services
