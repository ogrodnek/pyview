from typing import TypedDict

from pyview import LiveView, LiveViewSocket


class JsCommandsLiveViewContext(TypedDict):
    value: int


class JsCommandsLiveView(LiveView[JsCommandsLiveViewContext]):
    """
    JS Commands

    JS Commands let you update the DOM without making a trip to the server.
    """

    async def mount(self, socket: LiveViewSocket[JsCommandsLiveViewContext], session):
        socket.context = JsCommandsLiveViewContext({"value": 0})

    async def handle_event(self, event, payload, socket):
        print(event, payload)
        if event == "increment":
            socket.context["value"] += 1
