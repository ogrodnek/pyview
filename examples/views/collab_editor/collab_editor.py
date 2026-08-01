import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket, is_connected
from pyview.live_socket import pub_sub_hub

from ..presence.avatars import Avatar
from .rooms import (
    MAX_COLLABORATORS,
    MAX_DOCUMENT_BYTES,
    CollabRoom,
    DocAuthority,
    DocumentTooLarge,
    Editor,
    InvalidChangeSet,
    RoomCapacityReached,
    RoomStore,
    utf8_len,
    utf16_len,
)

INITIAL_DOC = """# Shared scratchpad

This is a temporary, unlisted document. Use the invite button to open the
same document in another window and type in both.

Every connected editor pushes changes to the LiveView process, which acts
as the central authority for CodeMirror's collab extension. Documents are
kept only in memory and are automatically deleted.
"""


ROOMS = RoomStore(authority_factory=lambda: DocAuthority(doc=INITIAL_DOC))


async def expire_collab_rooms() -> None:
    ROOMS.delete_expired()
    for topic in ROOMS.drain_expired_topics():
        await pub_sub_hub.send_all_on_topic_async(topic, {"kind": "expired"})


@dataclass
class CollabEditorContext:
    room_id: str = ""
    room_url: str = ""
    status: str = "loading"
    unavailable_title: str = "Document unavailable"
    unavailable_message: str = "This temporary document does not exist or has expired."
    client_id: str = ""
    current_user: Optional[Avatar] = None
    editors: list[Editor] = field(default_factory=list)
    version: int = 0
    doc_bytes: int = 0
    max_doc_bytes: int = MAX_DOCUMENT_BYTES

    def sync_from_room(self, room: CollabRoom) -> None:
        self.status = "available"
        self.editors = list(room.editors.values())
        self.version = room.authority.version
        self.doc_bytes = utf8_len(room.authority.doc)

    def set_unavailable(
        self,
        *,
        title: str = "Document unavailable",
        message: str = "This temporary document does not exist or has expired.",
    ) -> None:
        self.status = "unavailable"
        self.unavailable_title = title
        self.unavailable_message = message
        self.editors = []
        self.version = 0
        self.doc_bytes = 0


class CollabEditorLiveView(LiveView[CollabEditorContext]):
    """
    Collaborative Editor

    A collaborative scratchpad using CodeMirror's collab extension,
    LiveView events, room-scoped pubsub, and live cursors.
    """

    async def mount(self, socket: LiveViewSocket[CollabEditorContext], session):
        socket.context = CollabEditorContext()

    async def handle_params(
        self,
        socket: LiveViewSocket[CollabEditorContext],
        document_id: Optional[str] = None,
    ):
        ctx = socket.context

        if document_id is None:
            ctx.status = "creating"
            if is_connected(socket):
                await expire_collab_rooms()
                try:
                    room = ROOMS.create()
                except RoomCapacityReached:
                    ctx.set_unavailable(
                        title="Editor is at capacity",
                        message="Please try creating a document again shortly.",
                    )
                    return
                ctx.room_id = room.room_id
                await socket.replace_navigate(f"/collab_editor/{room.room_id}")
            return

        ctx.room_id = document_id
        ctx.room_url = f"/collab_editor/{document_id}"
        room = ROOMS.get(document_id)
        if room is None:
            ctx.set_unavailable()
            return

        if is_connected(socket) and not ctx.client_id:
            editor = Editor(client_id=uuid.uuid4().hex[:12], user=Avatar.generate())
            if not room.join(editor):
                ctx.set_unavailable(
                    title="Document is full",
                    message=f"This document already has {MAX_COLLABORATORS} collaborators.",
                )
                return

            ctx.client_id = editor.client_id
            ctx.current_user = editor.user
            socket.live_title = f"{editor.user.name} · Collab Editor"
            await socket.subscribe(room.topic)
            await socket.broadcast(room.topic, {"kind": "presence"})

        ctx.sync_from_room(room)

    async def handle_event(
        self, event, payload, socket: ConnectedLiveViewSocket[CollabEditorContext]
    ):
        ctx = socket.context
        room = ROOMS.get(ctx.room_id)
        if room is None or ctx.client_id not in room.editors:
            await self._expire_socket(socket)
            return

        editor = room.editors[ctx.client_id]

        if event not in ("request_init", "push_updates", "cursor"):
            return
        if not isinstance(payload, dict):
            if event == "push_updates":
                await socket.push_event("editor_error", {"message": "Invalid editor update."})
                await socket.push_event("resync", {})
            return
        event_limit = 3 if event == "request_init" else 30
        if not editor.allow_event(event, time.monotonic(), event_limit):
            return

        if event == "request_init":
            await socket.push_event(
                "init",
                {
                    "doc": room.authority.doc,
                    "version": room.authority.version,
                    "clientId": ctx.client_id,
                    "name": editor.user.name,
                    "color": editor.user.color,
                    "maxBytes": MAX_DOCUMENT_BYTES,
                },
            )
            return

        if event == "push_updates":
            version = payload.get("version")
            if type(version) is not int:
                await socket.push_event("editor_error", {"message": "Invalid editor update."})
                await socket.push_event("resync", {})
                return
            try:
                accepted = room.authority.receive(version, payload.get("updates"), ctx.client_id)
            except DocumentTooLarge:
                await socket.push_event(
                    "limit_exceeded", {"message": "This document has reached its 64 KiB limit."}
                )
                return
            except InvalidChangeSet:
                await socket.push_event("editor_error", {"message": "Invalid editor update."})
                await socket.push_event("resync", {})
                return

            if accepted is None:
                missing = room.authority.updates_since(version)
                if missing is None:
                    await socket.push_event("resync", {})
                elif missing:
                    await socket.push_event(
                        "updates", {"from_version": version, "updates": missing}
                    )
                return

            from_version, updates = accepted
            await socket.broadcast(
                room.topic,
                {"kind": "updates", "from_version": from_version, "updates": updates},
            )
            return

        if event == "cursor":
            anchor = payload.get("anchor") if isinstance(payload, dict) else None
            head = payload.get("head") if isinstance(payload, dict) else None
            doc_length = utf16_len(room.authority.doc)
            if (
                type(anchor) is not int
                or type(head) is not int
                or not 0 <= anchor <= doc_length
                or not 0 <= head <= doc_length
            ):
                return
            await socket.broadcast(
                room.topic,
                {
                    "kind": "cursor",
                    "clientId": ctx.client_id,
                    "anchor": anchor,
                    "head": head,
                    "name": editor.user.name,
                    "color": editor.user.color,
                },
            )

    async def handle_info(self, event, socket: ConnectedLiveViewSocket[CollabEditorContext]):
        msg = event.payload
        if not isinstance(msg, dict):
            return
        kind = msg.get("kind")

        if kind == "expired":
            await self._expire_socket(socket)
            return

        room = ROOMS.get(socket.context.room_id)
        if room is None:
            await self._expire_socket(socket)
            return

        if kind == "updates":
            socket.context.sync_from_room(room)
            await socket.push_event(
                "updates",
                {"from_version": msg["from_version"], "updates": msg["updates"]},
            )
        elif kind == "cursor" and msg.get("clientId") != socket.context.client_id:
            await socket.push_event("cursor", msg)
        elif kind == "presence":
            socket.context.editors = list(room.editors.values())
        elif kind == "left":
            socket.context.editors = list(room.editors.values())
            await socket.push_event("editor_left", {"clientId": msg["clientId"]})

    async def disconnect(self, socket: ConnectedLiveViewSocket[CollabEditorContext]):
        ctx = socket.context
        if not ctx.room_id or not ctx.client_id:
            return
        room = ROOMS.leave(ctx.room_id, ctx.client_id)
        if room is not None:
            await socket.broadcast(room.topic, {"kind": "left", "clientId": ctx.client_id})

    async def _expire_socket(self, socket: ConnectedLiveViewSocket[CollabEditorContext]) -> None:
        socket.context.set_unavailable()
        await socket.push_event("expired", {})
