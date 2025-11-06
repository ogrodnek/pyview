"""
Dependency Injection support for PyView using svcs.

This module provides a clean API for accessing services from LiveView mount
and event handlers. It works with both HTTP requests (UnconnectedSocket) and
WebSocket connections (ConnectedLiveViewSocket).

Example usage:

    # In your app setup
    from pyview import PyView
    from pyview.di import configure_di

    app = PyView()

    @configure_di(app)
    def register_services(registry):
        registry.register_factory(Database, get_database)
        registry.register_value(Config, config)

    # In your LiveView
    from pyview.di import get_services

    async def mount(self, socket, session):
        db, config = await get_services(socket, Database, Config)
        # Use your services...
"""
from __future__ import annotations
from typing import TypeVar, TYPE_CHECKING, Any
import svcs
from starlette.applications import Starlette
from contextlib import asynccontextmanager

if TYPE_CHECKING:
    from pyview.live_socket import LiveViewSocket

T = TypeVar("T")


def configure_di(app: Starlette):
    """
    Decorator to configure dependency injection for a PyView app.

    Usage:
        @configure_di(app)
        def register_services(registry: svcs.Registry):
            registry.register_factory(Database, get_database)
            registry.register_value(Config, config)

    Args:
        app: The PyView/Starlette application instance

    Returns:
        A decorator function that takes a registration function
    """
    def decorator(register_fn):
        # Create a lifespan that wraps svcs.starlette.lifespan
        @asynccontextmanager
        async def di_lifespan(app: Starlette):
            registry = svcs.Registry()

            # Call user's registration function
            register_fn(registry)

            # Store registry on app state for later access
            app.state.svcs_registry = registry

            try:
                yield
            finally:
                await registry.aclose()

        # If app already has a lifespan, we need to chain them
        existing_lifespan = app.router.lifespan_context

        if existing_lifespan:
            @asynccontextmanager
            async def combined_lifespan(app: Starlette):
                async with di_lifespan(app):
                    async with existing_lifespan(app):
                        yield
            app.router.lifespan_context = combined_lifespan
        else:
            app.router.lifespan_context = di_lifespan

        # Add svcs middleware to the app
        from starlette.middleware import Middleware
        app.user_middleware.insert(0, Middleware(svcs.starlette.SVCSMiddleware))
        app.middleware_stack = app.build_middleware_stack()

        return register_fn

    return decorator


async def get_services(socket: "LiveViewSocket", *service_types: type[T]) -> tuple[Any, ...]:
    """
    Get one or more services from the dependency injection container.

    This function works with both HTTP requests (UnconnectedSocket) and
    WebSocket connections (ConnectedLiveViewSocket).

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
    if not service_types:
        raise ValueError("At least one service type must be provided")

    # Check if socket has a DI container attached
    # (This will be set for both HTTP and WebSocket scenarios)
    if hasattr(socket, '_svcs_container') and socket._svcs_container is not None:
        container = socket._svcs_container
        services = await container.aget(*service_types)
    else:
        raise RuntimeError(
            "Dependency injection not configured. "
            "Make sure you've called configure_di() on your PyView app "
            "and that the socket has been properly initialized."
        )

    # Return single service directly, or tuple for multiple
    if len(service_types) == 1:
        return services[0]
    return services


def has_di_configured(socket: "LiveViewSocket") -> bool:
    """
    Check if dependency injection is configured for this socket.

    Args:
        socket: The LiveViewSocket to check

    Returns:
        True if DI is configured, False otherwise
    """
    return hasattr(socket, '_svcs_container')
