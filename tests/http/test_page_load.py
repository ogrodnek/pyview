"""The first page load: an HTTP GET that renders a live view before its websocket connects."""

import re

import httpx2

from pyview import PyView
from pyview.csrf import validate_csrf_token
from pyview.live_view import LiveView

from ..ws.views import StaticView, TextRendered


async def load(routes: dict[str, type[LiveView]], path: str) -> httpx2.Response:
    """Serve the given live views and GET `path`, as a browser's first request would."""
    app = PyView()
    for route, view in routes.items():
        app.add_live_view(route, view)
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path)


def attribute(html: str, pattern: str) -> str:
    match = re.search(pattern, html)
    assert match is not None, f"{pattern!r} not found in the page"
    return match.group(1)


async def test_page_shows_what_the_view_rendered_after_mount():
    # Given a view that sets its greeting when it mounts
    class Greeting(StaticView):
        async def mount(self, socket, session):
            socket.context = {"text": "hello"}

        async def render(self, assigns, meta):
            return TextRendered(assigns["text"])

    # When the page is loaded
    response = await load({"/": Greeting}, "/")

    # Then it contains the rendered view
    assert response.status_code == 200
    assert "<p>hello</p>" in response.text


async def test_page_load_passes_query_and_path_params_to_handle_params():
    # Given a view at a route with a path parameter, that records its params
    received = []

    class Profile(StaticView):
        async def handle_params(self, url, params, socket):
            received.append((params.getlist("tab"), params["id"]))

    # When the page is loaded with a query string
    await load({"/users/{id:int}": Profile}, "/users/7?tab=posts")

    # Then handle_params gets both: the query param, and the path param converted to an int
    assert received == [(["posts"], 7)]


async def test_page_title_comes_from_the_live_title():
    # Given a view that sets its title when it mounts
    class Inbox(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            socket.live_title = "Inbox"

    # When the page is loaded
    response = await load({"/": Inbox}, "/")

    # Then the page title is the live title, with the default suffix
    assert attribute(response.text, r"<title[^>]*>([^<]*)</title>") == "Inbox | LiveView"


async def test_page_embeds_a_csrf_token_for_its_view():
    # Given a page that has been loaded
    response = await load({"/": StaticView}, "/")

    # Then its CSRF token is valid for the topic the client joins: "lv:" and the view's element id
    view_id = attribute(response.text, r'data-phx-main="true"[^>]*id="([^"]+)"')
    token = attribute(response.text, r'<meta name="csrf-token" content="([^"]+)"')
    assert validate_csrf_token(token, f"lv:{view_id}")


async def test_each_page_load_gets_its_own_view_id():
    # When the same page is loaded twice
    first = await load({"/": StaticView}, "/")
    second = await load({"/": StaticView}, "/")

    # Then each load has a different view id, so each websocket joins its own topic
    pattern = r'data-phx-main="true"[^>]*id="([^"]+)"'
    assert attribute(first.text, pattern) != attribute(second.text, pattern)
