from typing import Optional, TypedDict

from pyview import LiveView, LiveViewSocket


class CountContext(TypedDict):
    count: int


class CountLiveView(LiveView[CountContext]):
    """
    Basic Counter

    Gotta start somewhere, right? This example shows how to send click events
    to the backend to update state.  We also snuck in handling URL params.
    """

    async def mount(self, socket: LiveViewSocket[CountContext], session):
        socket.context = CountContext({"count": 0})

    async def handle_event(self, event, payload, socket: LiveViewSocket[CountContext]):
        if event == "decrement":
            socket.context["count"] -= 1

        if event == "increment":
            socket.context["count"] += 1

    async def handle_params(self, socket: LiveViewSocket[CountContext], c: Optional[int] = None):
        if c is not None:
            socket.context["count"] = c
