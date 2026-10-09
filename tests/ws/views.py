from pyview.live_view import LiveView


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

    async def render(self, assigns, meta):
        return StaticRendered(f"<p>{type(self).__name__}</p>")
