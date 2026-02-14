from dataclasses import dataclass
from typing import Optional

from pyview import LiveView, LiveViewSocket
from pyview.events import AutoEventDispatch, event


@dataclass
class FlashDemoContext:
    name: str = ""


class FlashDemoLiveView(AutoEventDispatch, LiveView[FlashDemoContext]):
    """
    Flash Messages

    Show and dismiss user feedback with flash messages. Flash values live on the
    socket and are automatically available in your template.
    """

    async def mount(self, socket: LiveViewSocket[FlashDemoContext], session):
        socket.context = FlashDemoContext()

    @event
    async def save(self, name: Optional[str], socket: LiveViewSocket[FlashDemoContext]):
        if not name:
            socket.put_flash("error", "Name cannot be blank.")
            return

        socket.context.name = name
        socket.clear_flash()
        socket.put_flash("info", f"Saved — welcome, {name}!")

    @event
    async def danger(self, socket: LiveViewSocket[FlashDemoContext]):
        socket.put_flash("error", "Something went wrong.")
