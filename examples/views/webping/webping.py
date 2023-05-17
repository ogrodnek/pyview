from pyview import LiveView, LiveViewSocket
from dataclasses import dataclass, field
import datetime
from collections import deque
from .chart import Point
import time
import aiohttp
from pyview.events import InfoEvent


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


class PingLiveView(LiveView[PingContext]):
    async def mount(self, socket: LiveViewSocket[PingContext]):
        socket.context = PingContext(
            [
                PingSite("https://pyview.rocks"),
                PingSite("https://examples.pyview.rocks"),
            ]
        )
        if socket.connected:
            socket.schedule_info("ping", 10)
            await self.handle_info(InfoEvent("ping"), socket)

    async def handle_event(self, event, payload, socket: LiveViewSocket[PingContext]):
        await self.handle_info(InfoEvent("ping"), socket)

    async def ping(self, site: PingSite):
        start = time.time_ns()
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.head(site.url) as response:
                status = response.status
                diff = (time.time_ns() - start) / 1_000_000
                site.responses.append(PingResponse(status, diff, datetime.datetime.now()))
                site.status = "OK" if status == 200 else "Error"

    async def handle_info(self, event, socket: LiveViewSocket[PingContext]):
        for site in socket.context.sites:
            await self.ping(site)
