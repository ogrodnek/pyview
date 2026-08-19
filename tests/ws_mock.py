import json
from typing import Any, Optional, Union
from unittest.mock import AsyncMock, MagicMock

from starlette.websockets import WebSocketDisconnect

from pyview.csrf import generate_csrf_token
from pyview.session import serialize_session


def make_join_websocket(payload=None):
    """Create a mock websocket that returns a phx_join for /demo."""
    if payload is None:
        payload = {
            "url": "http://testserver/demo",
            "params": {"_csrf_token": generate_csrf_token("lv:test")},
        }
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.receive_text = AsyncMock(return_value=json.dumps(["1", "1", "lv:test", "phx_join", payload]))
    return ws


class MemoryWebSocket:
    """In-memory stand-in for Starlette's WebSocket.

    The handler and ConnectedLiveViewSocket only ever call five methods on the
    websocket -- accept, receive_text, receive, send_text and close -- so a fake
    implementing those can drive the full message loop without a server.

    Frames are scripted in with the push_* helpers and consumed in order; the
    inbox running dry raises WebSocketDisconnect, the same way a closed
    connection does. Outbound frames are recorded in `sent`.
    """

    def __init__(self, auth: Any = None):
        self._inbox: list[Union[str, dict[str, Any]]] = []
        self.sent: list[str] = []
        self.accepted = False
        self.closed = False
        if auth is not None:
            # starlette's has_required_scope() reads conn.auth
            self.auth = auth

    # -- scripting --------------------------------------------------------

    def push_text(self, data: str) -> "MemoryWebSocket":
        """Queue a raw string, consumed by receive_text (the initial join)."""
        self._inbox.append(data)
        return self

    def push_join(
        self,
        topic: str = "lv:test",
        url: str = "http://testserver/demo",
        join_ref: str = "1",
        msg_ref: str = "1",
        csrf_token: Optional[str] = None,
        session: Optional[dict[str, Any]] = None,
        redirect: bool = False,
        initial: bool = True,
    ) -> "MemoryWebSocket":
        """Queue a phx_join.

        `initial` joins arrive over receive_text (the first frame of the
        connection); later joins are navigation joins delivered to the message
        loop. `redirect` sends the url as the 'redirect' field, which is what
        the client does when navigating.
        """
        payload: dict[str, Any] = {
            "redirect" if redirect else "url": url,
            "params": {
                "_csrf_token": csrf_token if csrf_token is not None else generate_csrf_token(topic)
            },
        }
        if session is not None:
            payload["session"] = serialize_session(session)

        frame = [join_ref, msg_ref, topic, "phx_join", payload]
        if initial:
            return self.push_text(json.dumps(frame))
        return self.push_message({"type": "websocket.receive", "text": json.dumps(frame)})

    def push_phx(
        self,
        join_ref: Optional[str],
        msg_ref: Optional[str],
        topic: str,
        event: str,
        payload: Any,
    ) -> "MemoryWebSocket":
        """Queue a Phoenix frame, consumed by receive (the message loop)."""
        text = json.dumps([join_ref, msg_ref, topic, event, payload])
        return self.push_message({"type": "websocket.receive", "text": text})

    def push_event(
        self,
        event: str,
        value: Any = None,
        topic: str = "lv:test",
        type: str = "click",
        msg_ref: str = "2",
        join_ref: str = "1",
        **payload_extra: Any,
    ) -> "MemoryWebSocket":
        """Queue an 'event' frame (a click, form submit, etc.)."""
        payload = {"type": type, "event": event, "value": {} if value is None else value}
        payload.update(payload_extra)
        return self.push_phx(join_ref, msg_ref, topic, "event", payload)

    def push_message(self, msg: dict[str, Any]) -> "MemoryWebSocket":
        """Queue a raw ASGI message dict, consumed by receive."""
        self._inbox.append(msg)
        return self

    def push_disconnect(self, code: int = 1000) -> "MemoryWebSocket":
        self._inbox.append({"type": "websocket.disconnect", "code": code})
        return self

    # -- websocket surface ------------------------------------------------

    async def accept(self) -> None:
        self.accepted = True

    async def receive_text(self) -> str:
        if not self._inbox:
            raise WebSocketDisconnect(1000)
        item = self._inbox.pop(0)
        if isinstance(item, str):
            return item
        # a disconnect (or any framed message) queued where text was expected
        raise WebSocketDisconnect(item.get("code", 1000))

    async def receive(self) -> dict[str, Any]:
        if not self._inbox:
            raise WebSocketDisconnect(1000)
        item = self._inbox.pop(0)
        if isinstance(item, dict):
            return item
        return {"type": "websocket.receive", "text": item}

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000, reason: Optional[str] = None) -> None:
        self.closed = True

    # -- assertions -------------------------------------------------------

    @property
    def frames(self) -> list[list[Any]]:
        """Every sent frame, parsed."""
        return [json.loads(m) for m in self.sent]

    def frame_at(self, index: int) -> list[Any]:
        return self.frames[index]

    def reply_at(self, index: int) -> dict[str, Any]:
        """The phx_reply envelope of the frame at `index`."""
        frame = self.frames[index]
        assert frame[3] == "phx_reply", f"expected phx_reply, got {frame[3]}"
        return frame[4]

    def response_at(self, index: int) -> dict[str, Any]:
        """The response body of the phx_reply at `index`."""
        return self.reply_at(index)["response"]
