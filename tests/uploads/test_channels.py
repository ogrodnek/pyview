import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from starlette.types import Message
from starlette.websockets import WebSocketDisconnect

from pyview.uploads import UploadConstraints, UploadJoinResult, UploadManager

from .factories import upload_entry_data


@pytest.mark.parametrize("late_chunk", [False, True], ids=["leave", "leave-then-late-chunk"])
async def test_leaving_canceled_upload_channel_preserves_liveview_and_other_uploads(
    connected_socket, late_chunk
):
    # Given a connected LiveView with one canceled upload and another still underway
    handler, socket = connected_socket
    websocket = socket.websocket
    manager = socket.upload_manager
    config = manager.allow_upload("documents", UploadConstraints(accept=[".pdf"], max_files=2))
    first_file = upload_entry_data(
        name="first.pdf", file_type="application/pdf", size=4, path=config.name
    )
    second_file = {**first_file, "ref": "1", "name": "second.pdf"}
    config.add_entries([first_file, second_file])
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [first_file, second_file]}, context=None
    )
    manager.add_upload("first-join", {"token": response["entries"]["0"]})
    manager.add_upload("second-join", {"token": response["entries"]["1"]})
    manager.add_chunk("second-join", b"ab")
    second_upload = config.uploads.uploads["second-join"]
    config.cancel_entry("0")

    # When the browser leaves the canceled file's channel, with bytes possibly still in transit
    messages: list[Message] = [{"text": json.dumps(["first-join", "3", "lvu:0", "phx_leave", {}])}]
    if late_chunk:
        fields = [b"first-join", b"4", b"lvu:0", b"chunk"]
        header = bytes([0, *(len(field) for field in fields)])
        messages.append({"bytes": header + b"".join(fields) + b"cd"})
    websocket.receive = AsyncMock(side_effect=[*messages, WebSocketDisconnect()])
    with pytest.raises(WebSocketDisconnect):
        await handler._handle_connected_loop("lv:test", socket)

    # Then the LiveView stays connected and the other upload remains usable
    assert socket.connected
    assert manager.config_for_name("documents") is config
    assert not second_upload.file.closed
    manager.add_chunk("second-join", b"cd")
    assert Path(second_upload.file.name).read_bytes() == b"abcd"

    # And only the canceled upload's channel registration is removed
    assert "first-join" not in manager.upload_config_join_refs
    assert manager.upload_config_join_refs["second-join"] is config
    assert set(config.uploads.uploads) == {"second-join"}
    assert set(config.entries_by_ref) == {"1"}
    replies = [json.loads(call.args[0]) for call in websocket.send_text.await_args_list]
    assert replies == [
        ["first-join", message_ref, "lvu:0", "phx_reply", {"response": {}, "status": "ok"}]
        for message_ref in (["3", "4"] if late_chunk else ["3"])
    ]


async def test_upload_channel_join_rejects_unknown_file(connected_socket, tmp_path, monkeypatch):
    # Given a connected LiveView with an upload input but no selected files
    handler, socket = connected_socket
    websocket = socket.websocket
    manager = socket.upload_manager
    config = manager.allow_upload("document", UploadConstraints(max_files=1))
    monkeypatch.setattr("pyview.uploads.tempfile.tempdir", str(tmp_path))
    token = upload_entry_data(
        ref="unknown", name="example.pdf", file_type="application/pdf", size=4, path=config.name
    )

    # When the browser tries to start uploading a file that was never selected
    websocket.receive = AsyncMock(
        side_effect=[
            {"text": json.dumps(["upload-join", "2", "lvu:unknown", "phx_join", {"token": token}])},
            WebSocketDisconnect(),
        ]
    )
    with pytest.raises(WebSocketDisconnect):
        await handler._handle_connected_loop("lv:test", socket)

    # Then the join is rejected while the LiveView stays connected
    websocket.send_text.assert_awaited_once()
    assert json.loads(websocket.send_text.call_args.args[0]) == [
        "upload-join",
        "2",
        "lvu:unknown",
        "phx_reply",
        {"response": {"reason": "disallowed"}, "status": "error"},
    ]
    assert socket.connected

    # And no upload, channel registration, or temporary file is created
    assert config.entries_by_ref == {}
    assert config.uploads.uploads == {}
    assert manager.upload_config_join_refs == {}
    assert list(tmp_path.iterdir()) == []


async def test_upload_channel_join_rejects_file_awaiting_preflight(
    connected_socket, tmp_path, monkeypatch
):
    # Given a connected LiveView with a selected PDF still awaiting upload approval
    handler, socket = connected_socket
    websocket = socket.websocket
    manager = socket.upload_manager
    config = manager.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
    monkeypatch.setattr("pyview.uploads.tempfile.tempdir", str(tmp_path))
    file = upload_entry_data(
        name="example.pdf", file_type="application/pdf", size=4, path=config.name
    )
    config.add_entries([file])

    # When the browser tries to start uploading before requesting approval
    websocket.receive = AsyncMock(
        side_effect=[
            {"text": json.dumps(["upload-join", "2", "lvu:0", "phx_join", {"token": file}])},
            WebSocketDisconnect(),
        ]
    )
    with pytest.raises(WebSocketDisconnect):
        await handler._handle_connected_loop("lv:test", socket)

    # Then the join is rejected and the selected file still awaits approval
    websocket.send_text.assert_awaited_once()
    assert json.loads(websocket.send_text.call_args.args[0]) == [
        "upload-join",
        "2",
        "lvu:0",
        "phx_reply",
        {"response": {"reason": "disallowed"}, "status": "error"},
    ]
    assert socket.connected
    assert set(config.entries_by_ref) == {"0"}
    assert not config.entries_by_ref["0"].preflighted

    # And no upload, channel registration, or temporary file is created
    assert config.uploads.uploads == {}
    assert manager.upload_config_join_refs == {}
    assert list(tmp_path.iterdir()) == []


async def test_upload_channel_join_accepts_preflighted_file(connected_socket):
    # Given a connected LiveView with a selected PDF approved for direct upload
    handler, socket = connected_socket
    websocket = socket.websocket
    manager = socket.upload_manager
    config = manager.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
    file = upload_entry_data(
        name="example.pdf", file_type="application/pdf", size=4, path=config.name
    )
    config.add_entries([file])
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [file]}, context=None
    )

    # When the browser joins the upload channel using its preflight response
    websocket.receive = AsyncMock(
        side_effect=[
            {
                "text": json.dumps(
                    [
                        "upload-join",
                        "2",
                        "lvu:0",
                        "phx_join",
                        {"token": response["entries"]["0"]},
                    ]
                )
            },
            WebSocketDisconnect(),
        ]
    )
    with pytest.raises(WebSocketDisconnect):
        await handler._handle_connected_loop("lv:test", socket)

    # Then the join is accepted and the file can receive bytes
    websocket.send_text.assert_awaited_once()
    assert json.loads(websocket.send_text.call_args.args[0]) == [
        "upload-join",
        "2",
        "lvu:0",
        "phx_reply",
        {"response": {}, "status": "ok"},
    ]
    assert socket.connected
    assert manager.upload_config_join_refs["upload-join"] is config
    manager.add_chunk("upload-join", b"ab")
    upload = config.uploads.uploads["upload-join"]
    assert Path(upload.file.name).read_bytes() == b"ab"


async def test_upload_channel_join_rejects_file_already_uploading(
    connected_socket, tmp_path, monkeypatch
):
    # Given an approved PDF already uploading with some bytes received
    handler, socket = connected_socket
    websocket = socket.websocket
    manager = socket.upload_manager
    config = manager.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
    monkeypatch.setattr("pyview.uploads.tempfile.tempdir", str(tmp_path))
    file = upload_entry_data(
        name="example.pdf", file_type="application/pdf", size=4, path=config.name
    )
    config.add_entries([file])
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [file]}, context=None
    )
    payload = {"token": response["entries"]["0"]}
    manager.add_upload("original-join", payload)
    manager.add_chunk("original-join", b"ab")
    original_upload = config.uploads.uploads["original-join"]
    original_path = Path(original_upload.file.name)

    # When a second channel tries to upload the same file
    websocket.receive = AsyncMock(
        side_effect=[
            {"text": json.dumps(["duplicate-join", "3", "lvu:0", "phx_join", payload])},
            WebSocketDisconnect(),
        ]
    )
    with pytest.raises(WebSocketDisconnect):
        await handler._handle_connected_loop("lv:test", socket)

    # Then the second join is rejected without creating another upload or file
    websocket.send_text.assert_awaited_once()
    assert json.loads(websocket.send_text.call_args.args[0]) == [
        "duplicate-join",
        "3",
        "lvu:0",
        "phx_reply",
        {"response": {"reason": "already_registered"}, "status": "error"},
    ]
    assert set(manager.upload_config_join_refs) == {"original-join"}
    assert set(config.uploads.uploads) == {"original-join"}
    assert list(tmp_path.iterdir()) == [original_path]

    # And the original upload keeps its received bytes and can continue
    assert socket.connected
    assert config.uploads.uploads["original-join"] is original_upload
    assert not original_upload.file.closed
    assert original_path.read_bytes() == b"ab"
    manager.add_chunk("original-join", b"cd")
    assert original_path.read_bytes() == b"abcd"


async def test_upload_join_uses_registered_file_metadata():
    # Given a four-byte PDF selected and approved for direct upload
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
        # When the browser starts that upload but supplies a different name, size, and type
        token = {
            **response["entries"]["0"],
            "name": "different.txt",
            "size": 1000,
            "type": "text/plain",
        }
        result = manager.add_upload("upload-join", {"token": token})

        # Then the upload uses the file metadata recorded when it was selected
        assert result is UploadJoinResult.ACCEPTED
        upload = config.uploads.uploads["upload-join"]
        assert upload.entry.name == "example.pdf"
        assert upload.entry.size == 4
        assert upload.entry.type == "application/pdf"

        # And receiving bytes does not overwrite the selected file's percentage progress
        manager.add_chunk("upload-join", b"ab")
        assert config.entries_by_ref["0"].progress == 0
    finally:
        manager.close()
