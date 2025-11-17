from dataclasses import dataclass

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket, is_connected


@dataclass
class Count:
    count: int = 0

    def decrement(self):
        self.count = self.count - 1

    def increment(self):
        self.count = self.count + 1


class CountLiveViewPubSub(LiveView[Count]):
    """
    Basic Counter with PubSub

    The counter example, but with PubSub.  Open this example in multiple windows
    to see the state update in real time across all windows.
    """

    async def mount(self, socket: LiveViewSocket[Count], session):
        socket.context = Count()
        if is_connected(socket):
            await socket.subscribe("count")

    async def handle_event(
        self, event, payload, socket: ConnectedLiveViewSocket[Count]
    ):
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
        socket.context.count = event.payload
