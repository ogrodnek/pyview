import random
from typing import TypedDict

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket, is_connected


class CheckboxManager:
    checkboxes: list[bool]

    def __init__(self):
        self.checkboxes = [False] * 500

    def toggle(self, index: int):
        self.checkboxes[index] = not self.checkboxes[index]
        return self.checkboxes[index]

    def random_toggle(self):
        index = random.randint(0, len(self.checkboxes) - 1)
        return index, self.toggle(index)


CHECKBOXES = CheckboxManager()


class CheckboxContext(TypedDict):
    checkboxes: list[bool]


class CheckboxLiveView(LiveView[CheckboxContext]):
    async def mount(self, socket: LiveViewSocket[CheckboxContext], session):
        socket.context = CheckboxContext({"checkboxes": CHECKBOXES.checkboxes})

        if is_connected(socket):
            await socket.subscribe("checkboxes")
            socket.schedule_info("random_toggle", 3)

    async def handle_event(
        self, event, payload, socket: ConnectedLiveViewSocket[CheckboxContext]
    ):
        if event == "toggle":
            index = int(payload["index"])
            value = CHECKBOXES.toggle(index)

            await socket.broadcast("checkboxes", {"index": index, "value": value})

    async def handle_info(
        self, event, socket: ConnectedLiveViewSocket[CheckboxContext]
    ):
        if event == "random_toggle":
            index, value = CHECKBOXES.random_toggle()
            await socket.broadcast("checkboxes", {"index": index, "value": value})
