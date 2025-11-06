"""
Dependency Injection support for PyView.

PyView provides access to request/app state through socket.state, which allows
you to implement dependency injection in your own way or integrate with any
DI library.

## Using socket.state directly

The simplest approach is to use socket.state directly:

    # In middleware or app lifespan:
    @app.on_event("startup")
    def setup():
        app.state.db = Database()
        app.state.cache = Cache()

    # In your LiveView:
    async def mount(self, socket, session):
        db = socket.state.db
        cache = socket.state.cache

## Integration with svcs

If you want to use the svcs library, use the optional integration:

    from pyview.integrations.svcs_integration import configure_svcs, get_services

    @configure_svcs(app)
    def register_services(registry):
        registry.register_factory(Database, create_database)

    class MyLiveView(LiveView):
        async def mount(self, socket, session):
            db = await get_services(socket, Database)

## Custom DI Implementation

You can implement your own DI helper that works with any library:

    # my_di.py
    from pyview.live_socket import LiveViewSocket

    class DIContainer:
        def __init__(self):
            self.factories = {}

        def register(self, type_, factory):
            self.factories[type_] = factory

        async def get(self, type_):
            return await self.factories[type_]()

    # Setup in app:
    from starlette.middleware import Middleware

    container = DIContainer()
    container.register(Database, create_database)
    container.register(Cache, create_cache)

    class DIMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                # Attach container to request state
                from starlette.requests import Request
                request = Request(scope, receive, send)
                request.state.di_container = container
            await self.app(scope, receive, send)

    app.add_middleware(DIMiddleware)
    app.state.di_container = container  # For WebSocket connections

    # Use in LiveView:
    async def mount(self, socket, session):
        if hasattr(socket, 'request') and socket.request:
            # HTTP request
            container = socket.request.state.di_container
        else:
            # WebSocket connection
            container = socket.state.di_container

        db = await container.get(Database)
        cache = await container.get(Cache)

## Integration with dependency-injector

    from dependency_injector import containers, providers
    from dependency_injector.wiring import Provide, inject

    class Container(containers.DeclarativeContainer):
        db = providers.Singleton(Database)
        cache = providers.Singleton(Cache)

    container = Container()

    # Store on app state
    app.state.di_container = container

    # Use in LiveView with helper:
    async def get_service(socket, provider):
        if hasattr(socket, 'request') and socket.request:
            container = socket.request.state.di_container
        else:
            container = socket.state.di_container
        return provider()

    async def mount(self, socket, session):
        container = socket.state.di_container if hasattr(socket, 'websocket') \
                    else socket.request.state.di_container
        db = container.db()
        cache = container.cache()
"""
