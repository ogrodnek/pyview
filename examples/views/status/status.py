from pyview import LiveView, LiveViewSocket
import os
import psutil
from dataclasses import dataclass


PROCESS = None


def _get_process():
    global PROCESS
    if PROCESS is None:
        PROCESS = psutil.Process(os.getpid())
    return PROCESS


@dataclass
class StatusContext:
    rss: int
    cpu_pct: float = 0.0
    _mem_pct: float = 0.0

    def __init__(self):
        process = _get_process()
        self.rss = process.memory_info().rss
        self.cpu_pct = process.cpu_percent()
        self._mem_pct = process.memory_percent()

    @property
    def mem_pct(self) -> str:
        return f"{self._mem_pct:.2f}"

    @property
    def mem(self) -> str:
        return f"{(self.rss / 1024 / 1024):.2f}"


class StatusLiveView(LiveView[StatusContext]):
    async def mount(self, socket: LiveViewSocket[StatusContext]):
        socket.context = StatusContext()
        if socket.connected:
            socket.schedule_info("refresh", 5)

    async def handle_event(self, event, payload, socket: LiveViewSocket[StatusContext]):
        await self.handle_info("refresh", socket)

    async def handle_info(self, event, socket: LiveViewSocket[StatusContext]):
        socket.context = StatusContext()
