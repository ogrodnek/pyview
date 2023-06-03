from pyview import LiveView, LiveViewSocket


class JsCommandsLiveView(LiveView[dict]):
    async def mount(self, socket: LiveViewSocket[dict], _session):
        socket.context = {}
