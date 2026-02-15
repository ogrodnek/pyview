"""Transport abstraction over WebSocket connections.

Provides a protocol-based interface so the handler and live socket don't
depend directly on Starlette's WebSocket class. This enables testing with
a TestTransport that feeds scripted messages and records outbound responses.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from starlette.types import Message
from starlette.websockets import WebSocket


@runtime_checkable
class Transport(Protocol):
    """Minimal interface consumed by LiveSocketHandler and ConnectedLiveViewSocket."""

    async def accept(self) -> None: ...
    async def receive_text(self) -> str: ...
    async def receive(self) -> Message: ...
    async def send_text(self, data: str) -> None: ...
    async def close(self) -> None: ...


class WebSocketTransport:
    """Wraps a Starlette WebSocket to satisfy the Transport protocol."""

    def __init__(self, ws: WebSocket):
        self._ws = ws

    async def accept(self) -> None:
        await self._ws.accept()

    async def receive_text(self) -> str:
        return await self._ws.receive_text()

    async def receive(self) -> Message:
        return await self._ws.receive()

    async def send_text(self, data: str) -> None:
        await self._ws.send_text(data)

    async def close(self) -> None:
        await self._ws.close()
