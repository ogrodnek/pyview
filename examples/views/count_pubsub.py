from pyview import LiveView, LiveViewSocket
from dataclasses import dataclass


@dataclass
class Count:
    count: int = 0

    def decrement(self):
        self.count = self.count - 1

    def increment(self):
        self.count = self.count + 1


class CountLiveViewPubSub(LiveView[Count]):
    async def mount(self, socket: LiveViewSocket[Count]):
        socket.context = Count()
        if socket.connected:
            await socket.subscribe("count")

    async def handle_event(self, event, payload, socket: LiveViewSocket[Count]):
        if event == "decrement":
            socket.context.decrement()
        if event == "increment":
            socket.context.increment()

        await socket.broadcast("count", socket.context.count)

    async def handle_params(self, url, params, socket: LiveViewSocket[Count]):
        # check if "c" is in params
        # and if so set self.count to the value
        if "c" in params:
            socket.context.count = int(params["c"][0])

    async def handle_info(self, event, socket: LiveViewSocket[Count]):
        socket.context.count = event.payload  # type: ignore
