from pyview.live_view import LiveView
from pyview.template import RenderedContent


class StaticRendered:
    def __init__(self, html: str):
        self.html = html

    def tree(self):
        return {"s": [self.html]}

    def text(self, socket=None):
        return self.html


class StaticView(LiveView[dict]):
    """A LiveView that renders its class name; subclass to hook lifecycle callbacks."""

    async def mount(self, socket, session):
        socket.context = {}

    async def render(self, assigns, meta) -> RenderedContent:
        return StaticRendered(f"<p>{type(self).__name__}</p>")


class TextRendered:
    """A render tree with one dynamic value, so changes show up in the diff as {"0": text}."""

    def __init__(self, text: str):
        self.value = text

    def tree(self):
        return {"0": self.value, "s": ["<p>", "</p>"]}

    def text(self, socket=None):
        return f"<p>{self.value}</p>"
