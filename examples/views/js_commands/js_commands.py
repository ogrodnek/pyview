from pyview import LiveView, LiveViewSocket


class JsCommandsLiveView(LiveView[dict]):
    """
    JS Commands

    JS Commands let you update the DOM without making a trip to the server.
    """

    async def mount(self, socket: LiveViewSocket[dict], _session):
        socket.context = {}
