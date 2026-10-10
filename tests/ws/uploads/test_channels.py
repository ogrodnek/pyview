"""Upload channels (lvu:*): joining, sending chunks, and leaving."""

from pathlib import Path
from typing import Any

from pyview.uploads import UploadConfig, UploadConstraints

from ..fake_upload import FakeUploadClient
from ..views import StaticView


def pdf(ref: str, name: str, size: int = 4) -> dict[str, Any]:
    """File metadata as the browser sends it for a file chosen in the "documents" input."""
    return {
        "path": "documents",
        "ref": ref,
        "last_modified": 1,
        "name": name,
        "relative_path": "",
        "type": "application/pdf",
        "size": size,
    }


def documents_view(configs: list[UploadConfig], saved: list[bytes]):
    """A view with a "documents" upload for up to two PDFs.

    "save" consumes the uploads, "cancel" cancels one entry, and anything else is a no-op.
    """

    class Documents(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            configs.append(
                socket.allow_upload("documents", UploadConstraints(accept=[".pdf"], max_files=2))
            )

        async def handle_event(self, event, payload, socket):
            if event == "save":
                with configs[-1].consume_uploads() as uploads:
                    saved.extend(Path(upload.file.name).read_bytes() for upload in uploads)
            elif event == "cancel":
                configs[-1].cancel_entry(payload["ref"])

    return Documents


async def start_two_uploads(client, configs):
    """Choose and allow two PDFs, join an upload channel for each, and send half of each."""
    uploads = FakeUploadClient(client)
    config = configs[0]
    files = [pdf("0", "first.pdf"), pdf("1", "second.pdf")]
    await uploads.select("documents", config.ref, files)
    tokens = (await uploads.allow(config.ref, files))["response"]["entries"]
    first = await uploads.join(tokens["0"])
    second = await uploads.join(tokens["1"])
    await first.chunk(b"ab")
    await second.chunk(b"ab")
    return first, second


async def test_leaving_an_active_upload_channel_cleans_up_only_that_upload(connect):
    # Given two PDFs being uploaded, each halfway received
    configs: list[UploadConfig] = []
    saved: list[bytes] = []
    client = connect({"/": documents_view(configs, saved)})
    await client.join("/")
    config = configs[0]
    first, second = await start_two_uploads(client, configs)
    first_path = Path(config.uploads.uploads[first.join_ref].file.name)

    # When the browser leaves the first file's channel without the app canceling it first
    reply = await first.leave()

    # Then the leave is acknowledged, and the abandoned file is removed and deleted from disk
    assert reply == {"status": "ok", "response": {}}
    assert set(config.entries_by_ref) == {"1"}
    assert not first_path.exists()

    # And the second upload can still finish, and is the only one the view consumes
    assert (await second.chunk(b"cd"))["status"] == "ok"
    await client.event("save")
    assert saved == [b"abcd"]


async def test_leaving_a_canceled_upload_channel_keeps_the_view_and_the_other_upload(connect):
    # Given two PDFs being uploaded, where the app has canceled the first
    configs: list[UploadConfig] = []
    saved: list[bytes] = []
    client = connect({"/": documents_view(configs, saved)})
    await client.join("/")
    first, second = await start_two_uploads(client, configs)
    await client.event("cancel", {"ref": "0"})

    # When the browser leaves the canceled file's channel
    reply = await first.leave()

    # Then the leave is acknowledged and only the second file remains
    assert reply == {"status": "ok", "response": {}}
    assert set(configs[0].entries_by_ref) == {"1"}

    # And the second upload can still finish, and is the only one the view consumes
    assert (await second.chunk(b"cd"))["status"] == "ok"
    await client.event("save")
    assert saved == [b"abcd"]


async def test_chunk_after_leaving_an_upload_channel_is_ignored(connect):
    # Given a canceled upload whose channel the browser has left
    configs: list[UploadConfig] = []
    saved: list[bytes] = []
    client = connect({"/": documents_view(configs, saved)})
    await client.join("/")
    first, second = await start_two_uploads(client, configs)
    await client.event("cancel", {"ref": "0"})
    await first.leave()

    # When bytes already in transit arrive on the left channel
    reply = await first.chunk(b"cd")

    # Then they are acknowledged without error, and don't bring the canceled file back
    assert reply == {"status": "ok", "response": {}}
    assert set(configs[0].entries_by_ref) == {"1"}

    # And the second upload is unaffected
    assert (await second.chunk(b"cd"))["status"] == "ok"
    await client.event("save")
    assert saved == [b"abcd"]


async def test_upload_channel_join_rejects_a_file_that_was_never_chosen(connect):
    # Given a view with an upload input, but no file chosen
    configs: list[UploadConfig] = []
    client = connect({"/": documents_view(configs, [])})
    await client.join("/")
    uploads = FakeUploadClient(client)

    # When the browser tries to upload a file it never chose
    reply = (await uploads.join(pdf("unknown", "example.pdf"))).join_reply

    # Then the join is refused, no file or upload is registered, and the view keeps working
    assert reply == {"status": "error", "response": {"reason": "disallowed"}}
    assert configs[0].entries_by_ref == {}
    assert configs[0].uploads.uploads == {}
    assert (await client.event("ping"))["status"] == "ok"


async def test_upload_channel_join_rejects_a_file_awaiting_approval(connect):
    # Given a chosen PDF that hasn't been approved with allow_upload yet
    configs: list[UploadConfig] = []
    client = connect({"/": documents_view(configs, [])})
    await client.join("/")
    uploads = FakeUploadClient(client)
    await uploads.select("documents", configs[0].ref, [pdf("0", "example.pdf")])

    # When the browser tries to upload it using its own metadata as the token
    reply = (await uploads.join(pdf("0", "example.pdf"))).join_reply

    # Then the join is refused, the file still awaits approval, and no upload is started
    assert reply == {"status": "error", "response": {"reason": "disallowed"}}
    assert set(configs[0].entries_by_ref) == {"0"}
    assert not configs[0].entries_by_ref["0"].preflighted
    assert configs[0].uploads.uploads == {}
    assert (await client.event("ping"))["status"] == "ok"


async def test_upload_channel_join_accepts_an_approved_file(connect):
    # Given a chosen PDF approved with allow_upload
    configs: list[UploadConfig] = []
    saved: list[bytes] = []
    client = connect({"/": documents_view(configs, saved)})
    await client.join("/")
    uploads = FakeUploadClient(client)
    file = pdf("0", "example.pdf")
    await uploads.select("documents", configs[0].ref, [file])
    token = (await uploads.allow(configs[0].ref, [file]))["response"]["entries"]["0"]

    # When the browser joins the upload channel with the token from allow_upload
    upload = await uploads.join(token)

    # Then the join is accepted and the file's bytes are received
    assert upload.join_reply == {"status": "ok", "response": {}}
    await upload.chunk(b"ab")
    await upload.chunk(b"cd")
    await client.event("save")
    assert saved == [b"abcd"]


async def test_upload_channel_join_rejects_a_file_already_uploading(connect):
    # Given an approved PDF already uploading, with some bytes received
    configs: list[UploadConfig] = []
    saved: list[bytes] = []
    client = connect({"/": documents_view(configs, saved)})
    await client.join("/")
    uploads = FakeUploadClient(client)
    file = pdf("0", "example.pdf")
    await uploads.select("documents", configs[0].ref, [file])
    token = (await uploads.allow(configs[0].ref, [file]))["response"]["entries"]["0"]
    original = await uploads.join(token)
    await original.chunk(b"ab")

    # When a second channel tries to upload the same file
    reply = (await uploads.join(token)).join_reply

    # Then the second join is refused without starting another upload
    assert reply == {"status": "error", "response": {"reason": "already_registered"}}
    assert list(configs[0].uploads.uploads) == [original.join_ref]

    # And the original upload keeps its bytes and can finish
    assert (await original.chunk(b"cd"))["status"] == "ok"
    await client.event("save")
    assert saved == [b"abcd"]
