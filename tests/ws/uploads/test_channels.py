"""Upload channels (lvu:*): joining, sending chunks, and leaving."""

from pathlib import Path

from ..fake_upload import FakeUploadClient
from .documents import DocumentsPage, pdf


async def start_two_uploads(client, page: DocumentsPage):
    """Choose and allow two PDFs, join an upload channel for each, and send half of each."""
    uploads = FakeUploadClient(client)
    tokens = await uploads.choose(page.config, [pdf("0", "first.pdf"), pdf("1", "second.pdf")])
    first = await uploads.join(tokens["0"])
    second = await uploads.join(tokens["1"])
    await first.chunk(b"ab")
    await second.chunk(b"ab")
    return first, second


async def test_leaving_an_active_upload_channel_cleans_up_only_that_upload(connect):
    # Given two PDFs being uploaded, each halfway received
    page = DocumentsPage(max_files=2)
    client = connect({"/": page.view})
    await client.join("/")
    config = page.config
    first, second = await start_two_uploads(client, page)
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
    assert page.saved == [b"abcd"]


async def test_leaving_a_canceled_upload_channel_keeps_the_view_and_the_other_upload(connect):
    # Given two PDFs being uploaded, where the app has canceled the first
    page = DocumentsPage(max_files=2)
    client = connect({"/": page.view})
    await client.join("/")
    first, second = await start_two_uploads(client, page)
    await client.event("cancel", {"ref": "0"})

    # When the browser leaves the canceled file's channel
    reply = await first.leave()

    # Then the leave is acknowledged and only the second file remains
    assert reply == {"status": "ok", "response": {}}
    assert set(page.config.entries_by_ref) == {"1"}

    # And the second upload can still finish, and is the only one the view consumes
    assert (await second.chunk(b"cd"))["status"] == "ok"
    await client.event("save")
    assert page.saved == [b"abcd"]


async def test_chunk_after_leaving_an_upload_channel_is_ignored(connect):
    # Given a canceled upload whose channel the browser has left
    page = DocumentsPage(max_files=2)
    client = connect({"/": page.view})
    await client.join("/")
    first, second = await start_two_uploads(client, page)
    await client.event("cancel", {"ref": "0"})
    await first.leave()

    # When bytes already in transit arrive on the left channel
    reply = await first.chunk(b"cd")

    # Then they are acknowledged without error, and don't bring the canceled file back
    assert reply == {"status": "ok", "response": {}}
    assert set(page.config.entries_by_ref) == {"1"}

    # And the second upload is unaffected
    assert (await second.chunk(b"cd"))["status"] == "ok"
    await client.event("save")
    assert page.saved == [b"abcd"]


async def test_upload_channel_join_rejects_a_file_that_was_never_chosen(connect):
    # Given a view with an upload input, but no file chosen
    page = DocumentsPage()
    client = connect({"/": page.view})
    await client.join("/")
    uploads = FakeUploadClient(client)

    # When the browser tries to upload a file it never chose
    reply = (await uploads.join(pdf("unknown"))).join_reply

    # Then the join is refused, no file or upload is registered, and the view keeps working
    assert reply == {"status": "error", "response": {"reason": "disallowed"}}
    assert page.config.entries_by_ref == {}
    assert page.config.uploads.uploads == {}
    assert (await client.event("ping"))["status"] == "ok"


async def test_upload_channel_join_rejects_a_file_awaiting_approval(connect):
    # Given a chosen PDF that hasn't been approved with allow_upload yet
    page = DocumentsPage()
    client = connect({"/": page.view})
    await client.join("/")
    uploads = FakeUploadClient(client)
    await uploads.select("document", page.config.ref, [pdf()])

    # When the browser tries to upload it using its own metadata as the token
    reply = (await uploads.join(pdf())).join_reply

    # Then the join is refused, the file still awaits approval, and no upload is started
    assert reply == {"status": "error", "response": {"reason": "disallowed"}}
    assert set(page.config.entries_by_ref) == {"0"}
    assert not page.config.entries_by_ref["0"].preflighted
    assert page.config.uploads.uploads == {}
    assert (await client.event("ping"))["status"] == "ok"


async def test_upload_channel_join_accepts_an_approved_file(connect):
    # Given a chosen PDF approved with allow_upload
    page = DocumentsPage()
    client = connect({"/": page.view})
    await client.join("/")
    uploads = FakeUploadClient(client)
    token = (await uploads.choose(page.config, [pdf()]))["0"]

    # When the browser joins the upload channel with the token from allow_upload
    upload = await uploads.join(token)

    # Then the join is accepted and the file's bytes are received
    assert upload.join_reply == {"status": "ok", "response": {}}
    await upload.chunk(b"ab")
    await upload.chunk(b"cd")
    await client.event("save")
    assert page.saved == [b"abcd"]


async def test_upload_channel_join_rejects_a_file_already_uploading(connect):
    # Given an approved PDF already uploading, with some bytes received
    page = DocumentsPage()
    client = connect({"/": page.view})
    await client.join("/")
    uploads = FakeUploadClient(client)
    token = (await uploads.choose(page.config, [pdf()]))["0"]
    original = await uploads.join(token)
    await original.chunk(b"ab")

    # When a second channel tries to upload the same file
    reply = (await uploads.join(token)).join_reply

    # Then the second join is refused without starting another upload
    assert reply == {"status": "error", "response": {"reason": "already_registered"}}
    assert list(page.config.uploads.uploads) == [original.join_ref]

    # And the original upload keeps its bytes and can finish
    assert (await original.chunk(b"cd"))["status"] == "ok"
    await client.event("save")
    assert page.saved == [b"abcd"]
