from pyview import LiveView, LiveViewSocket
from pyview.events import InfoEvent
from typing import Optional
from .avatars import Avatar, UserRepository
from datetime import datetime
from dataclasses import dataclass, field

USER_REPO = UserRepository()


@dataclass
class Message:
    user: Avatar
    action: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class PresenceContext:
    connected: list[Avatar]
    current_user: Optional[Avatar] = None
    message: Optional[Message] = None


class PresenceLiveView(LiveView[PresenceContext]):
    async def mount(self, socket: LiveViewSocket[PresenceContext], _session):

        socket.context = PresenceContext(connected=USER_REPO.all())

        if socket.connected:
            user = USER_REPO.register_avatar()
            socket.context.current_user = user
            socket.live_title = user.name

            await socket.broadcast("presence", {"user": user, "action": "joined"})
            await socket.subscribe("presence")

    async def handle_info(self, event, socket: LiveViewSocket[PresenceContext]):
        if event.name == "disconnect":
            USER_REPO.unregister_avatar(socket.context.current_user)

            await socket.broadcast(
                "presence", {"user": socket.context.current_user, "action": "left"}
            )

        if event.name == "presence":
            socket.context.message = Message(
                user=event.payload["user"], action=event.payload["action"]
            )
            socket.context.connected = USER_REPO.all()
            socket.schedule_info_once(InfoEvent("clear_message"), 5)

        if event.name == "clear_message":
            socket.context.message = None
