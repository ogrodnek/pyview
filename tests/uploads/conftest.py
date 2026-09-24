from unittest.mock import AsyncMock, MagicMock

import pytest

from pyview.instrumentation import NoOpInstrumentation
from pyview.live_routes import LiveViewLookup
from pyview.live_socket import ConnectedLiveViewSocket
from pyview.live_view import LiveView
from pyview.uploads import UploadConstraints, UploadManager
from pyview.ws_handler import LiveSocketHandler

from .factories import upload_entry_data


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


@pytest.fixture
async def started_upload():
    manager = UploadManager()
    config = manager.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
    file = upload_entry_data(
        name="example.pdf", file_type="application/pdf", size=4, path=config.name
    )
    config.add_entries([file])
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [file]}, context=None
    )
    try:
        manager.add_upload("upload-join", {"token": response["entries"]["0"]})
        yield manager, config, config.uploads.uploads["upload-join"]
    finally:
        manager.close()
