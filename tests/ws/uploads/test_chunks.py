"""File chunks over an upload channel, checked against the file's declared size."""

from pathlib import Path
from unittest.mock import MagicMock

from ..fake_upload import FakeUpload, FakeUploadClient
from .documents import DocumentsPage, pdf


async def start_half_received_upload(client, page: DocumentsPage) -> FakeUpload:
    """Choose and allow the four-byte PDF, join its upload channel, and send two bytes."""
    uploads = FakeUploadClient(client)
    tokens = await uploads.choose(page.config, [pdf()])
    upload = await uploads.join(tokens["0"])
    await upload.chunk(b"ab")
    return upload


async def test_chunk_past_the_declared_size_is_rejected_without_writing(connect, monkeypatch):
    # Given a four-byte PDF with two bytes already received
    page = DocumentsPage()
    client = connect({"/": page.view})
    await client.join("/")
    upload = await start_half_received_upload(client, page)
    file = page.config.uploads.uploads[upload.join_ref].file
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
    page = DocumentsPage()
    client = connect({"/": page.view})
    await client.join("/")
    config = page.config
    upload = await start_half_received_upload(client, page)
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
    assert page.saved == []
