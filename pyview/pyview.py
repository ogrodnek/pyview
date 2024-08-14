from starlette.applications import Starlette
from starlette.websockets import WebSocket
from starlette.responses import HTMLResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.routing import Route
from starlette.requests import Request
import uuid
from urllib.parse import parse_qs, urlparse

from pyview.live_socket import UnconnectedSocket
from pyview.csrf import generate_csrf_token
from pyview.session import serialize_session
from pyview.auth import AuthProviderFactory
from .ws_handler import LiveSocketHandler
from .live_view import LiveView
from .live_routes import LiveViewLookup
from .template import (
    RootTemplate,
    RootTemplateContext,
    defaultRootTemplate,
    find_associated_css,
)


class PyView(Starlette):
    rootTemplate: RootTemplate

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rootTemplate = defaultRootTemplate()
        self.view_lookup = LiveViewLookup()
        self.live_handler = LiveSocketHandler(self.view_lookup)

        async def live_websocket_endpoint(websocket: WebSocket):
            await self.live_handler.handle(websocket)

        self.add_websocket_route("/live/websocket", live_websocket_endpoint)
        self.add_middleware(GZipMiddleware)

    def add_live_view(self, path: str, view: type[LiveView]):
        async def lv(request: Request):
            return await liveview_container(
                self.rootTemplate, self.view_lookup, request
            )

        self.view_lookup.add(path, view)
        auth = AuthProviderFactory.get(view)
        self.routes.append(Route(path, auth.wrap(lv), methods=["GET"]))


async def liveview_container(
    template: RootTemplate, view_lookup: LiveViewLookup, request: Request
):
    url = request.url
    path = url.path
    lv: LiveView = view_lookup.get(path)
    s = UnconnectedSocket()

    session = request.session if "session" in request.scope else {}

    await lv.mount(s, session)
    await lv.handle_params(urlparse(url._url), parse_qs(url.query), s)
    r = await lv.render(s.context)

    liveview_css = find_associated_css(lv)

    id = str(uuid.uuid4())

    context: RootTemplateContext = {
        "id": id,
        "content": r.text(),
        "title": s.live_title,
        "csrf_token": generate_csrf_token("lv:phx-" + id),
        "session": serialize_session(session),
        "additional_head_elements": liveview_css,
    }

    return HTMLResponse(template(context))
