from pyview import LiveView, LiveViewSocket
from typing import TypedDict

from pyview.vendor.ibis import filters


@filters.register
def mod(a: int, b: int) -> bool:
    return a % b == 0


class CheckboxContext(TypedDict):
    checkboxes: list[bool]


GLOBAL_CHECKBOXES = [False] * 500


class CheckboxLiveView(LiveView[CheckboxContext]):
    async def mount(self, socket: LiveViewSocket[CheckboxContext], _session):
        # random list of 100 true/false values
        socket.context = {"checkboxes": GLOBAL_CHECKBOXES}

        if socket.connected:
            await socket.subscribe("checkboxes")

    async def handle_event(
        self, event, payload, socket: LiveViewSocket[CheckboxContext]
    ):
        if event == "toggle":

            index = int(payload["index"])
            value = not socket.context["checkboxes"][index]

            global GLOBAL_CHECKBOXES
            GLOBAL_CHECKBOXES[index] = value

            await socket.broadcast("checkboxes", {"index": index, "value": value})

    async def handle_info(self, event, socket: LiveViewSocket[CheckboxContext]):
        index = event.payload["index"]
        value = event.payload["value"]

        print("index", index, "value", value)
