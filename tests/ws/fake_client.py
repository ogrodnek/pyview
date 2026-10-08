import asyncio
import itertools
import json
from typing import Any, Optional, cast

from starlette.types import Message
from starlette.websockets import WebSocket, WebSocketDisconnect

from pyview.csrf import generate_csrf_token
from pyview.ws_handler import LiveSocketHandler

REPLY_TIMEOUT = 1.0


class FakeWebSocket:
    """In-memory stand-in for a Starlette WebSocket.

    Frames the client sends are queued for the handler to receive; frames the
    handler sends are decoded and recorded in `sent`.
    """

    def __init__(self):
        self.inbox: asyncio.Queue[Message] = asyncio.Queue()
        self.sent: list[list[Any]] = []
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
        self.sent.append(json.loads(text))

    async def close(self, code: int = 1000):
        self.closed = True


class FakeClient:
    """Drives LiveSocketHandler.handle() the way the Phoenix JS client does.

    Each push returns the matching phx_reply payload ({"status", "response"}).
    Server pushes (diff, live_redirect, ...) are available in `websocket.sent`.
    """

    def __init__(self, handler: LiveSocketHandler, topic: str = "lv:phx-test"):
        self.handler = handler
        self.topic = topic
        self.websocket = FakeWebSocket()
        self.join_ref: Optional[str] = None
        self._refs = itertools.count(1)
        self._task: Optional[asyncio.Task] = None

    async def join(self, path: str, *, redirect: bool = False) -> dict[str, Any]:
        """Join the LiveView at `path`.

        The first join uses `url`. A join after live navigation (live_redirect)
        sends `redirect` instead, on the same topic with a new join ref.
        """
        ref = self._next_ref()
        self.join_ref = ref
        payload = {
            "redirect" if redirect else "url": f"http://testserver{path}",
            "params": {"_csrf_token": generate_csrf_token(self.topic)},
        }
        if self._task is None:
            self._task = asyncio.create_task(self.handler.handle(cast(WebSocket, self.websocket)))
        return await self._push(ref, "phx_join", payload)

    async def event(self, name: str, value: Any = None, *, type: str = "click") -> dict[str, Any]:
        payload = {"type": type, "event": name, "value": {} if value is None else value}
        return await self._push(self._next_ref(), "event", payload)

    async def leave(self) -> dict[str, Any]:
        return await self._push(self._next_ref(), "phx_leave", {})

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

    async def _push(self, ref: str, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        frame = [self.join_ref, ref, self.topic, event, payload]
        await self.websocket.inbox.put({"type": "websocket.receive", "text": json.dumps(frame)})
        return await asyncio.wait_for(self._reply_for(ref), REPLY_TIMEOUT)

    async def _reply_for(self, ref: str) -> dict[str, Any]:
        while True:
            for frame in self.websocket.sent:
                if frame[1] == ref and frame[3] == "phx_reply":
                    return frame[4]
            if self._task is not None and self._task.done():
                self._task.result()
                raise AssertionError(f"handler exited without replying to ref {ref}")
            await asyncio.sleep(0)
