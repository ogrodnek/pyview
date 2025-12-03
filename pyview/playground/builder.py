"""
Playground helpers for creating single-file PyView examples.

Example usage:

    from pyview.playground import playground
    from pyview import LiveView, LiveViewSocket

    class CounterView(LiveView):
        async def mount(self, socket: LiveViewSocket, session):
            socket.context = {"count": 0}

        async def handle_event(self, event, payload, socket: LiveViewSocket):
            if event == "increment":
                socket.context["count"] += 1

        async def render(self, context, meta):
            return f"<button phx-click='increment'>Count: {context['count']}</button>"

    # Create app, run with: uvicorn module:app --reload
    app = playground().with_live_view(CounterView).with_title("Counter").build()
"""

from typing import Optional

from markupsafe import Markup
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from pyview.live_view import LiveView
from pyview.playground.favicon import Favicon, generate_favicon_svg
from pyview.pyview import PyView
from pyview.template import defaultRootTemplate


class PlaygroundBuilder:
    """Fluent builder for creating PyView playground applications."""

    def __init__(self) -> None:
        self._views: list[tuple[str, type[LiveView]]] = []
        self._css: list[Markup] = []
        self._title: Optional[str] = None
        self._title_suffix: Optional[str] = " | LiveView"
        self._favicon: Optional[Favicon] = Favicon()

    def with_live_view(self, view: type[LiveView], path: str = "/") -> "PlaygroundBuilder":
        """Add a LiveView to the application."""
        self._views.append((path, view))
        return self

    def with_css(self, css: Markup | str) -> "PlaygroundBuilder":
        """Add CSS/head content. Can be called multiple times to accumulate."""
        self._css.append(Markup(css) if isinstance(css, str) else css)
        return self

    def with_title(self, title: str, suffix: Optional[str] = " | LiveView") -> "PlaygroundBuilder":
        """Set the page title and optional suffix."""
        self._title = title
        self._title_suffix = suffix
        return self

    def with_favicon(self, favicon: Optional[Favicon]) -> "PlaygroundBuilder":
        """Configure favicon generation. Pass None to disable."""
        self._favicon = favicon
        return self

    def no_favicon(self) -> "PlaygroundBuilder":
        """Disable auto-generated favicon."""
        self._favicon = None
        return self

    def build(self) -> PyView:
        """Build and return the configured PyView application."""
        if not self._views:
            raise ValueError("Must add at least one LiveView via with_live_view()")

        app = PyView()

        # Auto-mount static files
        app.mount("/static", StaticFiles(packages=[("pyview", "static")]), name="static")

        # Collect CSS entries
        css_parts = list(self._css)

        # Add favicon route and link tag if favicon config exists and title is set
        if self._favicon is not None and self._title:
            favicon_svg = generate_favicon_svg(
                self._title,
                bg_color=self._favicon.bg_color,
                text_color=self._favicon.text_color,
            )

            async def favicon_route(request: Request) -> Response:
                return Response(content=favicon_svg, media_type="image/svg+xml")

            app.routes.append(Route("/favicon.svg", favicon_route, methods=["GET"]))
            css_parts.append(Markup('<link rel="icon" href="/favicon.svg" type="image/svg+xml">'))

        # Configure root template - join all CSS entries
        combined_css = Markup("\n".join(css_parts)) if css_parts else None
        app.rootTemplate = defaultRootTemplate(
            css=combined_css,
            title=self._title,
            title_suffix=self._title_suffix,
        )

        # Add all LiveViews
        for path, view in self._views:
            app.add_live_view(path, view)

        return app


def playground() -> PlaygroundBuilder:
    """Create a new playground builder."""
    return PlaygroundBuilder()
