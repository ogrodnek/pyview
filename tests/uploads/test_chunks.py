import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.websockets import WebSocketDisconnect

from pyview.uploads import UploadConstraints


@pytest.fixture
async def partial_upload(connected_socket):
    handler, socket = connected_socket
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
    manager.add_upload("upload-join", {"token": response["entries"]["0"]})
    manager.add_chunk("upload-join", b"ab")
    return handler, socket, config.uploads.uploads["upload-join"]


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


async def test_chunk_exceeding_declared_file_size_is_rejected(partial_upload, monkeypatch):
    # Given an approved four-byte file with two bytes already received
    handler, socket, upload = partial_upload
    write = MagicMock(wraps=upload.file.write)
    monkeypatch.setattr(upload.file, "write", write)

    # When three more bytes arrive, exceeding the file's declared size
    response = await send_chunk(handler, socket, b"cde")

    # Then the browser receives a size error and none of the new bytes are written
    assert response == {
        "response": {"reason": "file_size_limit_exceeded"},
        "status": "error",
    }
    write.assert_not_called()

    # And the parent LiveView stays connected
    assert socket.connected


async def test_oversized_chunk_cleans_up_partial_upload(partial_upload):
    # Given an approved upload with a temporary file containing its first two bytes
    handler, socket, upload = partial_upload
    manager = socket.upload_manager
    config = manager.config_for_name("document")
    assert config is not None
    temporary_path = Path(upload.file.name)
    assert temporary_path.read_bytes() == b"ab"

    # When another chunk would exceed the file's declared size
    await send_chunk(handler, socket, b"cde")

    # Then the partial file is closed and deleted, and its upload registration is removed
    assert upload.file.closed
    assert not temporary_path.exists()
    assert config.uploads.uploads == {}
    assert config.entries_by_ref == {}
    assert manager.upload_config_join_refs == {}

    # And the failed file cannot be consumed while the LiveView stays connected
    with config.consume_uploads() as uploads:
        assert uploads == []
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


async def test_received_bytes_are_counted_separately_from_percentage_progress(partial_upload):
    # Given a four-byte upload with two bytes received and the browser reporting 50 percent
    handler, socket, upload = partial_upload
    config = socket.upload_manager.config_for_name("document")
    assert config is not None
    config.update_progress("0", 50)
    assert not upload.is_complete

    # When the remaining two bytes arrive before another browser progress update
    await send_chunk(handler, socket, b"cd")

    # Then the byte count includes both chunks and the file is complete
    assert upload.bytes_received == 4
    assert upload.is_complete
    assert not config.uploads.no_progress()

    # And receiving bytes does not turn either entry's percentage progress into a byte count
    assert config.entries_by_ref["0"].progress == 50
    assert upload.entry.progress == 0
