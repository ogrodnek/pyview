import uuid
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import parse_qs, urlparse

from starlette.applications import Starlette
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route, WebSocketRoute

from pyview.auth import AuthProviderFactory
from pyview.binding import call_handle_params
from pyview.components.lifecycle import run_nested_component_lifecycle
from pyview.csrf import generate_csrf_token
from pyview.instrumentation import InstrumentationProvider, NoOpInstrumentation
from pyview.live_socket import UnconnectedSocket
from pyview.meta import PyViewMeta
from pyview.session import serialize_session

from .live_routes import LiveViewLookup
from .live_view import LiveView
from .template import (
    RootTemplate,
    RootTemplateContext,
    defaultRootTemplate,
    find_associated_css,
)
from .ws_handler import LiveSocketHandler


class PyView(Starlette):
    rootTemplate: RootTemplate
    instrumentation: InstrumentationProvider

    def __init__(self, *args, instrumentation: Optional[InstrumentationProvider] = None, **kwargs):
        # Extract user's lifespan if provided, then always use our composed lifespan
        user_lifespan = kwargs.pop("lifespan", None)
        kwargs["lifespan"] = self._create_lifespan(user_lifespan)

        super().__init__(*args, **kwargs)
        self.rootTemplate = defaultRootTemplate()
        self.instrumentation = instrumentation or NoOpInstrumentation()
        self.view_lookup = LiveViewLookup()
        self.live_handler = LiveSocketHandler(self.view_lookup, self.instrumentation)

        self.routes.append(WebSocketRoute("/live/websocket", self.live_handler.handle))
        self.add_middleware(GZipMiddleware)

    def _create_lifespan(self, user_lifespan=None):
        """Create the lifespan context manager for proper startup/shutdown.

        Args:
            user_lifespan: Optional user-provided lifespan context manager to wrap
        """

        @asynccontextmanager
        async def lifespan(app):
            # Startup: Start the scheduler
            app.live_handler.start_scheduler()

            # Run user's lifespan if they provided one
            if user_lifespan:
                async with user_lifespan(app):
                    yield
            else:
                yield

            # Shutdown: Stop the scheduler
            await app.live_handler.shutdown_scheduler()

        return lifespan

    def add_live_view(self, path: str, view: type[LiveView]):
        async def lv(request: Request):
            return await liveview_container(self.rootTemplate, self.view_lookup, request)

        self.view_lookup.add(path, view)
        auth = AuthProviderFactory.get(view)
        self.routes.append(Route(path, auth.wrap(lv), methods=["GET"]))


async def liveview_container(template: RootTemplate, view_lookup: LiveViewLookup, request: Request):
    url = request.url
    path = url.path
    lv, path_params = view_lookup.get(path)
    s = UnconnectedSocket()

    session = request.session if "session" in request.scope else {}

    await lv.mount(s, session)

    # Parse query parameters
    query_params = parse_qs(url.query)

    # Merge path parameters with query parameters
    # Path parameters take precedence in case of conflict
    merged_params = {**query_params, **path_params}

    # Pass merged parameters to handle_params
    await call_handle_params(lv, urlparse(url._url), merged_params, s)

    # Pass socket to meta for component registration
    meta = PyViewMeta(socket=s)
    r = await lv.render(s.context, meta)

    # Run component lifecycle, including nested components
    await run_nested_component_lifecycle(s, meta)

    liveview_css = find_associated_css(lv)

    id = str(uuid.uuid4())

    context: RootTemplateContext = {
        "id": id,
        "content": r.text(socket=s),  # Pass socket for ComponentMarker resolution
        "title": s.live_title,
        "csrf_token": generate_csrf_token("lv:phx-" + id),
        "session": serialize_session(session),
        "additional_head_elements": liveview_css,
    }

    return HTMLResponse(template(context))
