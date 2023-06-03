from pyview import LiveView, LiveViewSocket
from typing import TypedDict


class CountContext(TypedDict):
    count: int


class CountLiveView(LiveView[CountContext]):
    async def mount(self, socket: LiveViewSocket[CountContext], _session):
        socket.context = {"count": 0}

    async def handle_event(self, event, payload, socket: LiveViewSocket[CountContext]):
        if event == "decrement":
            socket.context["count"] -= 1

        if event == "increment":
            socket.context["count"] += 1

    async def handle_params(self, url, params, socket: LiveViewSocket[CountContext]):
        # check if "c" is in params
        # and if so set self.count to the value
        if "c" in params:
            socket.context["count"] = int(params["c"][0])
