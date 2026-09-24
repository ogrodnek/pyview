from unittest.mock import AsyncMock, MagicMock

import pytest

from pyview.instrumentation import NoOpInstrumentation
from pyview.live_routes import LiveViewLookup
from pyview.live_socket import ConnectedLiveViewSocket
from pyview.live_view import LiveView
from pyview.ws_handler import LiveSocketHandler


@pytest.fixture
async def connected_socket():
    instrumentation = NoOpInstrumentation()
    handler = LiveSocketHandler(LiveViewLookup(), instrumentation)
    websocket = MagicMock()
    websocket.send_text = AsyncMock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="lv:test",
        liveview=LiveView(),
        scheduler=handler.scheduler,
        instrumentation=instrumentation,
    )

    try:
        yield handler, socket
    finally:
        await socket.close()
