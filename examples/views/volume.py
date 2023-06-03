from pyview import LiveView, LiveViewSocket
from dataclasses import dataclass


@dataclass
class Volume:
    volume: int = 10


class VolumeLiveView(LiveView[Volume]):
    async def mount(self, socket: LiveViewSocket[Volume], _session):
        socket.context = Volume()

    async def handle_event(self, event, payload, socket: LiveViewSocket[Volume]):
        if event == "key_update":
            event = payload["key"]

        if event == "off" or event == "ArrowLeft":
            socket.context.volume = 0
        if event == "on" or event == "ArrowRight":
            socket.context.volume = 100
        if event == "down" or event == "ArrowDown":
            socket.context.volume = socket.context.volume - 10
        if event == "up" or event == "ArrowUp":
            socket.context.volume = socket.context.volume + 10

        if socket.context.volume < 0:
            socket.context.volume = 0
        if socket.context.volume > 100:
            socket.context.volume = 100
