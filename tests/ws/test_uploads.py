"""Uploads over the websocket, as the Phoenix JS client sends them."""

from pathlib import Path

from pyview.uploads import UploadConfig, UploadConstraints

from .fake_upload import FakeUploadClient
from .views import StaticView

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


async def test_allow_upload_replies_with_the_chunk_size_and_an_entry_token(connect):
    # Given a view with an upload, where the user has chosen a file
    configs = []
    client = connect({"/": document_upload_view(configs, [])})
    await client.join("/")
    uploads = FakeUploadClient(client)
    upload_ref = configs[0].ref
    await uploads.select("document", upload_ref, [PDF])

    # When the client asks to upload it
    reply = await uploads.allow(upload_ref, [PDF])

    # Then the reply has what the client uses: the chunk size and a token for the file
    assert reply["status"] == "ok"
    response = reply["response"]
    assert response["config"]["chunk_size"] == 64 * 1024
    assert set(response["entries"]) == {"0"}
    assert "diff" in response


async def test_file_uploaded_in_chunks_can_be_consumed_by_the_view(connect):
    # Given a view with an upload, where the user has chosen a file and it was allowed
    configs = []
    saved = []
    client = connect({"/": document_upload_view(configs, saved)})
    await client.join("/")
    uploads = FakeUploadClient(client)
    upload_ref = configs[0].ref
    await uploads.select("document", upload_ref, [PDF])
    token = (await uploads.allow(upload_ref, [PDF]))["response"]["entries"]["0"]

    # When the client joins the upload channel, sends the file in two chunks, and reports progress
    upload = await uploads.join(token)
    first = await upload.chunk(b"ab")
    second = await upload.chunk(b"cd")
    progress = await uploads.progress(upload_ref, "0", 100)

    # Then every step is accepted
    assert upload.join_reply["status"] == "ok"
    assert [first["status"], second["status"], progress["status"]] == ["ok", "ok", "ok"]

    # And the view can consume the file, with the bytes that were sent
    await client.event("save")
    assert saved == [b"abcd"]
