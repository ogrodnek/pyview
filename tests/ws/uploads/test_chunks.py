"""File chunks over an upload channel, checked against the file's declared size."""

from pathlib import Path
from unittest.mock import MagicMock

from pyview.uploads import UploadConfig, UploadConstraints

from ..fake_upload import FakeUpload, FakeUploadClient
from ..views import StaticView

PDF = {
    "path": "document",
    "ref": "0",
    "last_modified": 1,
    "name": "example.pdf",
    "relative_path": "",
    "type": "application/pdf",
    "size": 4,
}


def document_upload_view(configs: list[UploadConfig], saved: list[bytes]):
    """A view with one "document" upload; its "save" event consumes the uploaded files."""

    class Documents(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            configs.append(
                socket.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
            )

        async def handle_event(self, event, payload, socket):
            if event == "save":
                with configs[-1].consume_uploads() as uploads:
                    saved.extend(Path(upload.file.name).read_bytes() for upload in uploads)

    return Documents


async def start_half_received_upload(client, config: UploadConfig) -> FakeUpload:
    """Choose and allow the four-byte PDF, join its upload channel, and send two bytes."""
    uploads = FakeUploadClient(client)
    await uploads.select("document", config.ref, [PDF])
    token = (await uploads.allow(config.ref, [PDF]))["response"]["entries"]["0"]
    upload = await uploads.join(token)
    await upload.chunk(b"ab")
    return upload


async def test_chunk_past_the_declared_size_is_rejected_without_writing(connect, monkeypatch):
    # Given a four-byte PDF with two bytes already received
    configs: list[UploadConfig] = []
    client = connect({"/": document_upload_view(configs, [])})
    await client.join("/")
    upload = await start_half_received_upload(client, configs[0])
    file = configs[0].uploads.uploads[upload.join_ref].file
    write = MagicMock(wraps=file.write)
    monkeypatch.setattr(file, "write", write)

    # When three more bytes arrive, past the file's declared size
    reply = await upload.chunk(b"cde")

    # Then the browser receives a size error and none of the new bytes are written
    assert reply == {"status": "error", "response": {"reason": "file_size_limit_exceeded"}}
    write.assert_not_called()

    # And the view stays connected
    assert (await client.event("ping"))["status"] == "ok"


async def test_oversized_chunk_cleans_up_the_partial_upload(connect):
    # Given a four-byte PDF with two bytes already received
    configs: list[UploadConfig] = []
    saved: list[bytes] = []
    client = connect({"/": document_upload_view(configs, saved)})
    await client.join("/")
    config = configs[0]
    upload = await start_half_received_upload(client, config)
    file = config.uploads.uploads[upload.join_ref].file
    assert Path(file.name).read_bytes() == b"ab"

    # When another chunk would go past the file's declared size
    await upload.chunk(b"cde")

    # Then the partial file is closed and deleted, and the file is no longer selected
    assert file.closed
    assert not Path(file.name).exists()
    assert config.uploads.uploads == {}
    assert config.entries_by_ref == {}

    # And the view stays connected, with nothing to consume
    assert (await client.event("save"))["status"] == "ok"
    assert saved == []
