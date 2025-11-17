import datetime
import ssl
import time
from collections import deque
from dataclasses import dataclass, field

import aiohttp
import certifi

from pyview import LiveView, LiveViewSocket, is_connected
from pyview.events import BaseEventHandler, InfoEvent, info

from .chart import Point


@dataclass
class PingResponse:
    status: int
    time: float
    date: datetime.datetime

    @property
    def time_formatted(self) -> str:
        return f"{self.time:.2f}"


@dataclass
class PingSite:
    url: str
    status: str = "Not started"
    responses: deque[PingResponse] = field(default_factory=lambda: deque(maxlen=25))

    @property
    def points(self) -> list[Point]:
        return [Point(i, r.time) for i, r in enumerate(self.responses)]


@dataclass
class PingContext:
    sites: list[PingSite]


timeout = aiohttp.ClientTimeout(total=10)
ssl_context = ssl.create_default_context(cafile=certifi.where())


class PingLiveView(BaseEventHandler, LiveView[PingContext]):
    """
    Web Ping

    Another example of pushing updates from the backend to the client.
    """

    async def mount(self, socket: LiveViewSocket[PingContext], session):
        socket.context = PingContext(
            [
                PingSite("https://pyview.rocks"),
                PingSite("https://examples.pyview.rocks"),
            ]
        )
        if is_connected(socket):
            socket.schedule_info(InfoEvent("ping"), 10)
            await self.handle_ping(InfoEvent("ping"), socket)

    async def handle_event(self, event, payload, socket: LiveViewSocket[PingContext]):
        await self.handle_ping(InfoEvent("ping"), socket)

    async def ping(self, site: PingSite):
        start = time.time_ns()
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with (
            aiohttp.ClientSession(timeout=timeout, connector=connector) as session,
            session.head(site.url) as response,
        ):
            status = response.status
            diff = (time.time_ns() - start) / 1_000_000
            site.responses.append(
                PingResponse(status, diff, datetime.datetime.now())
            )
            site.status = "OK" if status == 200 else "Error"

    @info("ping")
    async def handle_ping(self, event, socket: LiveViewSocket[PingContext]):
        for site in socket.context.sites:
            await self.ping(site)
