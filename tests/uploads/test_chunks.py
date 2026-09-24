import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.websockets import WebSocketDisconnect

from pyview.instrumentation import NoOpInstrumentation
from pyview.live_routes import LiveViewLookup
from pyview.live_socket import ConnectedLiveViewSocket
from pyview.live_view import LiveView
from pyview.uploads import UploadConstraints
from pyview.ws_handler import LiveSocketHandler


@pytest.fixture
async def partial_upload():
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
    manager = socket.upload_manager
    config = manager.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
    file = {
        "ref": "0",
        "name": "example.pdf",
        "type": "application/pdf",
        "size": 4,
        "path": "document",
    }
    config.add_entries([file])
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [file]}, context=None
    )
    try:
        manager.add_upload("upload-join", {"token": response["entries"]["0"]})
        manager.add_chunk("upload-join", b"ab")
        yield handler, socket, config.uploads.uploads["upload-join"]
    finally:
        await socket.close()


async def send_chunk(handler, socket, chunk):
    fields = [b"upload-join", b"3", b"lvu:0", b"chunk"]
    header = bytes([0, *(len(field) for field in fields)])
    socket.websocket.receive = AsyncMock(
        side_effect=[{"bytes": header + b"".join(fields) + chunk}, WebSocketDisconnect()]
    )
    with pytest.raises(WebSocketDisconnect):
        await handler._handle_connected_loop("lv:test", socket)
    socket.websocket.send_text.assert_awaited_once()
    return json.loads(socket.websocket.send_text.call_args.args[0])[4]


async def test_chunk_exceeding_declared_file_size_is_rejected(partial_upload):
    # Given an approved four-byte file with two bytes already received
    handler, socket, upload = partial_upload

    # When three more bytes arrive, exceeding the file's declared size
    response = await send_chunk(handler, socket, b"cde")

    # Then the browser receives a size error and none of the new bytes are written
    assert response == {
        "response": {"reason": "file_size_limit_exceeded"},
        "status": "error",
    }
    assert Path(upload.file.name).read_bytes() == b"ab"

    # And the parent LiveView stays connected
    assert socket.connected


async def test_chunk_reaching_declared_file_size_is_accepted(partial_upload):
    # Given an approved four-byte file with two bytes already received
    handler, socket, upload = partial_upload

    # When the remaining two bytes arrive
    response = await send_chunk(handler, socket, b"cd")

    # Then the browser receives success and the complete file is stored
    assert response == {"response": {}, "status": "ok"}
    assert Path(upload.file.name).read_bytes() == b"abcd"
    assert socket.connected
