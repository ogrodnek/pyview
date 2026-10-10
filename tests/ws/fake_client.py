import asyncio
import itertools
import json
from typing import Any, NamedTuple, Optional, cast

from starlette.types import Message
from starlette.websockets import WebSocket, WebSocketDisconnect

from pyview.csrf import generate_csrf_token
from pyview.ws_handler import LiveSocketHandler

REPLY_TIMEOUT = 1.0


class Frame(NamedTuple):
    """A Phoenix channel message, sent on the wire as [join_ref, ref, topic, event, payload]."""

    join_ref: Optional[str]
    ref: Optional[str]
    topic: str
    event: str
    payload: Any


class FakeWebSocket:
    """In-memory stand-in for a Starlette WebSocket.

    Frames the client sends are queued for the handler to receive; frames the
    handler sends are decoded and recorded in `sent`. Frames it sends on its own,
    rather than as a reply, are also queued in `pushed`.
    """

    def __init__(self):
        self.inbox: asyncio.Queue[Message] = asyncio.Queue()
        self.sent: list[Frame] = []
        self.pushed: asyncio.Queue[Frame] = asyncio.Queue()
        self.closed = False

    async def accept(self):
        pass

    async def receive(self) -> Message:
        return await self.inbox.get()

    async def receive_text(self) -> str:
        message = await self.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message["code"])
        return message["text"]

    async def send_text(self, text: str):
        frame = Frame(*json.loads(text))
        self.sent.append(frame)
        if frame.event != "phx_reply":
            self.pushed.put_nowait(frame)

    async def close(self, code: int = 1000):
        self.closed = True


class FakeClient:
    """Drives LiveSocketHandler.handle() the way the Phoenix JS client does.

    Each push returns the matching phx_reply payload ({"status", "response"}).
    Messages the server sends on its own (diff, live_redirect, ...) are in `pushes()`.
    """

    def __init__(self, handler: LiveSocketHandler, topic: str = "lv:phx-test"):
        self.handler = handler
        self.topic = topic
        self.websocket = FakeWebSocket()
        self.join_ref: Optional[str] = None
        self._refs = itertools.count(1)
        self._task: Optional[asyncio.Task] = None

    async def join(
        self, path: str, *, redirect: bool = False, params: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Join the LiveView at `path`.

        The first join uses `url`. A join after live navigation (live_redirect)
        sends `redirect` instead, on the same topic with a new join ref.
        `params` replaces the join params, which by default carry a valid CSRF token.
        """
        ref = self._next_ref()
        self.join_ref = ref
        payload = {
            "redirect" if redirect else "url": f"http://testserver{path}",
            "params": {"_csrf_token": generate_csrf_token(self.topic)}
            if params is None
            else params,
        }
        if self._task is None:
            self._task = asyncio.create_task(self.handler.handle(cast(WebSocket, self.websocket)))
        return await self._push(ref, "phx_join", payload)

    async def event(
        self, name: str, value: Any = None, *, type: str = "click", topic: Optional[str] = None
    ) -> dict[str, Any]:
        payload = {"type": type, "event": name, "value": {} if value is None else value}
        return await self._push(self._next_ref(), "event", payload, topic)

    async def leave(self, *, topic: Optional[str] = None) -> dict[str, Any]:
        return await self._push(self._next_ref(), "phx_leave", {}, topic)

    async def live_patch(self, path: str) -> dict[str, Any]:
        payload = {"url": f"http://testserver{path}"}
        return await self._push(self._next_ref(), "live_patch", payload)

    async def push(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send any other client event on the client's topic."""
        return await self._push(self._next_ref(), event, payload)

    async def heartbeat(self) -> dict[str, Any]:
        """Send the socket-level heartbeat, which uses the "phoenix" topic and no join ref."""
        return await self._send(Frame(None, self._next_ref(), "phoenix", "heartbeat", {}))

    def pushes(self) -> list[Frame]:
        """Frames the server sent on its own rather than in reply to the client."""
        return [frame for frame in self.websocket.sent if frame.event != "phx_reply"]

    async def next_push(self) -> Frame:
        """The next frame the server pushed on its own, waiting for it if needed."""
        return await asyncio.wait_for(self.websocket.pushed.get(), REPLY_TIMEOUT)

    async def disconnect(self):
        """Close the websocket from the client side and wait for the handler to finish."""
        await self.websocket.inbox.put({"type": "websocket.disconnect", "code": 1001})
        await self.wait_closed()

    async def wait_closed(self):
        if self._task is not None:
            await asyncio.wait_for(self._task, REPLY_TIMEOUT)

    async def close(self):
        """Test teardown: disconnect if the handler is still running."""
        if self._task is not None and not self._task.done():
            await self.disconnect()

    def _next_ref(self) -> str:
        return str(next(self._refs))

    async def _push(
        self, ref: str, event: str, payload: dict[str, Any], topic: Optional[str] = None
    ) -> dict[str, Any]:
        """Send a frame, by default on the client's own topic, and wait for its reply."""
        return await self._send(Frame(self.join_ref, ref, topic or self.topic, event, payload))

    async def _send(self, frame: Frame) -> dict[str, Any]:
        await self.websocket.inbox.put({"type": "websocket.receive", "text": json.dumps(frame)})
        assert frame.ref is not None
        return await asyncio.wait_for(self._reply_for(frame.ref), REPLY_TIMEOUT)

    async def _reply_for(self, ref: str) -> dict[str, Any]:
        while True:
            for frame in self.websocket.sent:
                if frame.ref == ref and frame.event == "phx_reply":
                    return frame.payload
            if self._task is not None and self._task.done():
                self._task.result()
                raise AssertionError(f"handler exited without replying to ref {ref}")
            await asyncio.sleep(0)
