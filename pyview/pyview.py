import uuid
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import parse_qs, urlparse

from starlette.applications import Starlette
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route, WebSocketRoute

from pyview.auth import AuthProviderFactory
from pyview.binding import call_handle_params
from pyview.components.lifecycle import run_nested_component_lifecycle
from pyview.csrf import generate_csrf_token
from pyview.css import CSSRegistry
from pyview.instrumentation import InstrumentationProvider, NoOpInstrumentation
from pyview.live_socket import UnconnectedSocket
from pyview.meta import PyViewMeta
from pyview.render_hooks import HookContext, RenderHookRunner
from pyview.render_hooks.css import CSSRenderHook
from pyview.session import serialize_session

from .live_routes import LiveViewLookup
from .live_view import LiveView
from .template import (
    RootTemplate,
    RootTemplateContext,
    defaultRootTemplate,
)
from .ws_handler import LiveSocketHandler


class PyView(Starlette):
    rootTemplate: RootTemplate
    instrumentation: InstrumentationProvider
    css_registry: CSSRegistry
    render_hooks: RenderHookRunner

    def __init__(
        self,
        *args,
        instrumentation: Optional[InstrumentationProvider] = None,
        css_auto_refresh: bool = False,
        **kwargs,
    ):
        # Extract user's lifespan if provided, then always use our composed lifespan
        user_lifespan = kwargs.pop("lifespan", None)
        kwargs["lifespan"] = self._create_lifespan(user_lifespan)

        super().__init__(*args, **kwargs)
        self.rootTemplate = defaultRootTemplate()
        self.instrumentation = instrumentation or NoOpInstrumentation()
        self.view_lookup = LiveViewLookup()

        # CSS registry and render hooks
        self.css_registry = CSSRegistry(auto_refresh=css_auto_refresh)
        self.render_hooks = RenderHookRunner()
        self.render_hooks.add(CSSRenderHook(self.css_registry))

        self.live_handler = LiveSocketHandler(
            self.view_lookup, self.instrumentation, self.render_hooks, self.css_registry
        )

        self.routes.append(WebSocketRoute("/live/websocket", self.live_handler.handle))
        self.routes.append(Route("/pyview-css/{name:path}.{hash}.css", self._serve_css))
        self.add_middleware(GZipMiddleware)

    async def _serve_css(self, request: Request) -> Response:
        """Serve CSS files with content-hash based caching."""
        name = request.path_params["name"]
        hash = request.path_params["hash"]
        entry = self.css_registry.get_for_serving(f"{name}.{hash}")

        if entry:
            return Response(
                entry.content,
                media_type="text/css",
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                },
            )
        return Response(status_code=404)

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
            return await liveview_container(
                self.rootTemplate, self.view_lookup, self.render_hooks, request
            )

        self.view_lookup.add(path, view)
        auth = AuthProviderFactory.get(view)
        self.routes.append(Route(path, auth.wrap(lv), methods=["GET"]))

    def add_render_hook(self, hook) -> None:
        """Add a custom render hook."""
        self.render_hooks.add(hook)


async def liveview_container(
    template: RootTemplate,
    view_lookup: LiveViewLookup,
    render_hooks: RenderHookRunner,
    request: Request,
):
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

    id = str(uuid.uuid4())

    context: RootTemplateContext = {
        "id": id,
        "content": r.text(socket=s),  # Pass socket for ComponentMarker resolution
        "title": s.live_title,
        "csrf_token": generate_csrf_token("lv:phx-" + id),
        "session": serialize_session(session),
        "additional_head_elements": [],
    }

    # Run render hooks for initial render (CSS injection, etc.)
    hook_ctx = HookContext(view=lv, socket=s, is_connected=False)
    await render_hooks.run_on_initial_render(hook_ctx, context)

    return HTMLResponse(template(context))
