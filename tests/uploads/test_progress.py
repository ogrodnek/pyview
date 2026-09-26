import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketDisconnect

from pyview.uploads import (
    ConstraintViolation,
    ExternalUploadMeta,
    UploadConstraints,
    UploadFailure,
    UploadSuccess,
)

from .factories import upload_entry_data


@pytest.fixture
async def approved_external_upload(connected_socket):
    _, socket = connected_socket
    config = socket.allow_upload(
        "document",
        UploadConstraints(accept=[".pdf"], max_files=1),
        external=AsyncMock(return_value=ExternalUploadMeta(uploader="S3")),
    )
    file = upload_entry_data(path=config.name)
    config.add_entries([file])
    await socket.upload_manager.process_allow_upload(
        {"ref": config.ref, "entries": [file]}, context=None
    )
    return config


async def send_progress(connected_socket, config, progress):
    handler, socket = connected_socket
    socket.render_with_components = AsyncMock(return_value={})
    payload = {"ref": config.ref, "entry_ref": "0", "progress": progress}
    socket.websocket.receive = AsyncMock(
        side_effect=[
            {"text": json.dumps(["lv:test", "2", "lv:test", "progress", payload])},
            WebSocketDisconnect(),
        ]
    )
    with pytest.raises(WebSocketDisconnect):
        await handler._handle_connected_loop("lv:test", socket)


async def test_progress_callback_sees_cloud_upload_failure(
    connected_socket, approved_external_upload
):
    # Given a cloud upload halfway finished and an app that observes its progress
    _, socket = connected_socket
    config = approved_external_upload
    config.update_progress("0", 50)

    async def observe_failure(entry, callback_socket):
        # Then the progress callback sees the failure already recorded
        assert callback_socket is socket
        assert not entry.valid
        assert not entry.done
        assert entry.progress == 50
        assert entry.errors == [ConstraintViolation(ref="0", code="upload_failed")]

    config.progress_callback = AsyncMock(side_effect=observe_failure)
    config.entry_complete_callback = AsyncMock()

    # When the browser reports that the cloud upload failed
    await send_progress(connected_socket, config, {"error": "Connection lost"})

    # And both callbacks run once, with the completion callback receiving the failure
    config.progress_callback.assert_awaited_once()
    entry = config.entries_by_ref["0"]
    config.entry_complete_callback.assert_awaited_once_with(
        entry, UploadFailure(error="Connection lost"), socket
    )
    assert entry.errors == [ConstraintViolation(ref="0", code="upload_failed")]


async def test_progress_callback_can_consume_completed_multipart_upload(
    connected_socket, approved_external_upload
):
    # Given an app that consumes cloud uploads as soon as its progress callback sees completion
    config = approved_external_upload
    consumed = []

    async def consume_completed(entry, socket):
        # Then the callback sees completion and can consume the upload immediately
        assert entry.done
        assert entry.progress == 100
        with config.consume_external_upload(entry.ref) as upload:
            consumed.append(upload)

    config.progress_callback = AsyncMock(side_effect=consume_completed)
    entry = config.entries_by_ref["0"]

    # When the browser reports multipart completion with its uploaded parts
    await send_progress(
        connected_socket,
        config,
        {"complete": True, "upload_id": "upload-1", "parts": [{"PartNumber": 1, "ETag": "abc"}]},
    )

    # And the consumed entry is removed without being restored after the callback
    config.progress_callback.assert_awaited_once()
    assert consumed == [entry]
    assert config.entries_by_ref == {}


async def test_progress_callback_runs_before_completion_callback_consumes_upload(
    connected_socket, approved_external_upload
):
    # Given an app that observes progress and consumes cloud uploads in its completion callback
    config = approved_external_upload
    callbacks = []

    async def observe_completion(entry, socket):
        assert entry.done
        assert entry.progress == 100
        callbacks.append("progress")

    async def consume_completed(entry, result, socket):
        assert result == UploadSuccess()
        with config.consume_external_upload(entry.ref):
            callbacks.append("complete")

    config.progress_callback = observe_completion
    config.entry_complete_callback = consume_completed

    # When the browser reports that the cloud upload reached 100 percent
    await send_progress(connected_socket, config, 100)

    # Then progress is observed before the completion callback consumes the entry
    assert callbacks == ["progress", "complete"]
    assert config.entries_by_ref == {}


async def test_progress_callback_can_consume_fully_received_local_upload(connected_socket):
    # Given a local upload whose bytes have all arrived
    _, socket = connected_socket
    manager = socket.upload_manager
    config = socket.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
    file = upload_entry_data(path=config.name)
    config.add_entries([file])
    response = await manager.process_allow_upload({"ref": config.ref, "entries": [file]}, None)
    manager.add_upload("upload-join", {"token": response["entries"]["0"]})
    manager.add_chunk("upload-join", b"abcd")
    upload = config.uploads.for_entry("0")
    temporary_path = Path(upload.file.name)
    received = []

    async def consume_completed(entry, socket):
        assert entry.done
        with config.consume_upload_entry(entry.ref) as completed:
            received.append(Path(completed.file.name).read_bytes())

    config.progress_callback = AsyncMock(side_effect=consume_completed)

    # When the browser reports completion and the app consumes the file in its progress callback
    await send_progress(connected_socket, config, 100)

    # Then the callback receives the complete file and consumption cleans it up
    config.progress_callback.assert_awaited_once()
    assert received == [b"abcd"]
    assert config.entries_by_ref == {}
    assert upload.file.closed
    assert not temporary_path.exists()
