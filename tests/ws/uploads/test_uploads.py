"""Uploads over the websocket, as the Phoenix JS client sends them."""

from ..fake_upload import FakeUploadClient
from .documents import DocumentsPage, pdf


async def test_allow_upload_replies_with_the_chunk_size_and_an_entry_token(connect):
    # Given a view with an upload, where the user has chosen a file
    page = DocumentsPage()
    client = connect({"/": page.view})
    await client.join("/")
    uploads = FakeUploadClient(client)
    await uploads.select("document", page.config.ref, [pdf()])

    # When the client asks to upload it
    reply = await uploads.allow(page.config.ref, [pdf()])

    # Then the reply has what the client uses: the chunk size and a token for the file
    assert reply["status"] == "ok"
    response = reply["response"]
    assert response["config"]["chunk_size"] == 64 * 1024
    assert set(response["entries"]) == {"0"}
    assert "diff" in response


async def test_file_uploaded_in_chunks_can_be_consumed_by_the_view(connect):
    # Given a view with an upload, where the user has chosen a file and it was allowed
    page = DocumentsPage()
    client = connect({"/": page.view})
    await client.join("/")
    uploads = FakeUploadClient(client)
    tokens = await uploads.choose(page.config, [pdf()])

    # When the client joins the upload channel, sends the file in two chunks, and reports progress
    upload = await uploads.join(tokens["0"])
    first = await upload.chunk(b"ab")
    second = await upload.chunk(b"cd")
    progress = await uploads.progress(page.config.ref, "0", 100)

    # Then every step is accepted
    assert upload.join_reply["status"] == "ok"
    assert [first["status"], second["status"], progress["status"]] == ["ok", "ok", "ok"]

    # And the view can consume the file, with the bytes that were sent
    await client.event("save")
    assert page.saved == [b"abcd"]
