import asyncio
from unittest.mock import AsyncMock, MagicMock

from pyview.events import InfoEvent
from pyview.instrumentation import NoOpInstrumentation
from pyview.live_socket import ConnectedLiveViewSocket
from pyview.live_view import LiveView


class DisconnectTrackingView(LiveView[dict]):
    def __init__(self):
        self.disconnect_calls = 0

    async def disconnect(self, socket):
        self.disconnect_calls += 1


async def test_close_cancels_streams_without_scheduling_cancel_jobs():
    cancelled = asyncio.Event()

    async def slow_gen():
        try:
            while True:
                await asyncio.sleep(10)
                yield "never"
        finally:
            cancelled.set()

    websocket = MagicMock()
    websocket.send_text = AsyncMock()
    scheduler = MagicMock()
    view = DisconnectTrackingView()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="lv:test",
        liveview=view,
        scheduler=scheduler,
        instrumentation=NoOpInstrumentation(),
    )

    socket.stream_runner.start_stream(
        slow_gen(),
        on_yield=lambda item: InfoEvent("chunk", item),
        on_cancel=InfoEvent("cancelled"),
    )

    await asyncio.sleep(0)
    await socket.close()
    await asyncio.sleep(0.05)
    # Generator cleanup runs asynchronously after close
    assert cancelled.is_set()
    scheduler.add_job.assert_not_called()
    assert view.disconnect_calls == 1

    await socket.close()

    assert view.disconnect_calls == 1
