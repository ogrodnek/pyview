from starlette.applications import Starlette
from fastapi import WebSocket
from fastapi.responses import HTMLResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.routing import Route
import uuid
from urllib.parse import parse_qs

from pyview.live_socket import UnconnectedSocket
from pyview.csrf import generate_csrf_token
from .ws_handler import LiveSocketHandler
from .live_view import LiveView
from .live_routes import LiveViewLookup
from typing import Callable, Optional, TypedDict


class RootTemplateContext(TypedDict):
    id: str
    content: str
    title: Optional[str]
    css: Optional[str]
    csrf_token: str


RootTemplate = Callable[[RootTemplateContext], str]


class PyView(Starlette):
    rootTemplate: RootTemplate

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rootTemplate = defaultRootTemplate("")
        self.view_lookup = LiveViewLookup()
        self.live_handler = LiveSocketHandler(self.view_lookup)

        async def live_websocket_endpoint(websocket: WebSocket):
            await self.live_handler.handle(websocket)

        self.add_websocket_route("/live/websocket", live_websocket_endpoint)
        self.add_middleware(GZipMiddleware)

    def add_live_view(self, path: str, view: Callable[[], LiveView]):
        async def lv(request):
            return await liveview_container(
                self.rootTemplate, self.view_lookup, request
            )

        self.view_lookup.add(path, view)
        self.routes.append(Route(path, lv, methods=["GET"]))


async def liveview_container(
    template: RootTemplate, view_lookup: LiveViewLookup, request
):
    url = request.url
    path = url.path
    lv: LiveView = view_lookup.get(path)
    s = UnconnectedSocket()
    await lv.mount(s)
    await lv.handle_params(url, parse_qs(url.query), s)
    r = await lv.render(s.context)

    id = str(uuid.uuid4())

    context: RootTemplateContext = {
        "id": id,
        "content": r.text(),
        "title": s.live_title,
        "csrf_token": generate_csrf_token("lv:phx-" + id),
        "css": None,
    }

    return HTMLResponse(template(context))


def defaultRootTemplate(css: str) -> RootTemplate:
    def template(context: RootTemplateContext) -> str:
        context["css"] = css
        return _defaultRootTemplate(context)

    return template


def _defaultRootTemplate(context: RootTemplateContext) -> str:
    suffix = " | LiveView"
    render_title = (
        (context["title"] + suffix)  # type: ignore
        if context.get("title", None) is not None
        else "LiveView"
    )
    css = context["css"] if context.get("css", None) is not None else ""
    return f"""
<!DOCTYPE html>
<html lang="en">
    <head>
      <title data-suffix="{suffix}">{render_title}</title>
      <meta name="csrf-token" content="{context['csrf_token']}" />
      <meta charset="utf-8">
      <meta http-equiv="X-UA-Compatible" content="IE=edge">
      <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
      <script defer type="text/javascript" src="/static/assets/app.js"></script>
      {css}
    </head>
    <body>
    <div>
      <a href="/">Home</a>
      <div
        data-phx-main="true"
        data-phx-session=""
        data-phx-static=""
        id="phx-{context['id']}"
        >
        {context['content']}
    </div>
    </div>
    </body>
</html>
"""
