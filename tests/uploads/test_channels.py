import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.types import Message
from starlette.websockets import WebSocketDisconnect

from pyview.instrumentation import NoOpInstrumentation
from pyview.live_routes import LiveViewLookup
from pyview.live_socket import ConnectedLiveViewSocket
from pyview.live_view import LiveView
from pyview.uploads import UploadConstraints
from pyview.ws_handler import LiveSocketHandler


@pytest.mark.parametrize("late_chunk", [False, True], ids=["leave", "leave-then-late-chunk"])
async def test_leaving_canceled_upload_channel_preserves_liveview_and_other_uploads(late_chunk):
    # Given a connected LiveView with one canceled upload and another still underway
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
    config = manager.allow_upload("documents", UploadConstraints(accept=[".pdf"], max_files=2))
    first_file = {
        "ref": "0",
        "name": "first.pdf",
        "type": "application/pdf",
        "size": 4,
        "path": "documents",
    }
    second_file = {**first_file, "ref": "1", "name": "second.pdf"}
    config.add_entries([first_file, second_file])
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [first_file, second_file]}, context=None
    )
    try:
        manager.add_upload("first-join", {"token": response["entries"]["0"]})
        manager.add_upload("second-join", {"token": response["entries"]["1"]})
        manager.add_chunk("second-join", b"ab")
        second_upload = config.uploads.uploads["second-join"]
        config.cancel_entry("0")

        # When the browser leaves the canceled file's channel, with bytes possibly still in transit
        messages: list[Message] = [
            {"text": json.dumps(["first-join", "3", "lvu:0", "phx_leave", {}])}
        ]
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
    finally:
        await socket.close()
