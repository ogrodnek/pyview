from typing import TypedDict

from pyview import LiveView, LiveViewSocket


class FlashDemoContext(TypedDict):
    name: str


class FlashDemoLiveView(LiveView[FlashDemoContext]):
    """
    Flash Messages

    Show and dismiss user feedback with flash messages. Flash values live on the
    socket and are automatically available in your template.
    """

    async def mount(self, socket: LiveViewSocket[FlashDemoContext], session):
        socket.context = FlashDemoContext(name="")

    async def handle_event(self, event, payload, socket: LiveViewSocket[FlashDemoContext]):
        if event == "save":
            name = payload.get("name", "").strip()
            if not name:
                socket.put_flash("error", "Name cannot be blank.")
                return
            socket.context["name"] = name
            socket.put_flash("info", f"Saved — welcome, {name}!")
        elif event == "danger":
            socket.put_flash("error", "Something went wrong.")
