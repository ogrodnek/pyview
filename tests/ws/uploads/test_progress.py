"""Progress reports for uploads, and the app's progress and completion callbacks."""

from pathlib import Path

from pyview.uploads import ConstraintViolation, ExternalUploadMeta, UploadFailure, UploadSuccess

from ..fake_upload import FakeUploadClient
from .documents import DocumentsPage, pdf


async def presign(entry, context) -> ExternalUploadMeta:
    return ExternalUploadMeta(uploader="S3")


async def start_cloud_upload(client, page: DocumentsPage) -> FakeUploadClient:
    """Choose the PDF and have it approved for a direct-to-cloud upload."""
    uploads = FakeUploadClient(client)
    await uploads.choose(page.config, [pdf()])
    return uploads


async def test_progress_callback_sees_a_cloud_upload_failure(connect):
    # Given a cloud upload, and an app that observes its progress and completion
    seen = []
    completed = []

    async def observe(entry, socket):
        seen.append((socket, entry.progress, entry.valid, entry.done, list(entry.errors)))

    async def complete(entry, result, socket):
        completed.append((entry.ref, result, socket))

    page = DocumentsPage(external=presign, progress=observe, entry_complete=complete)
    client = connect({"/": page.view})
    await client.join("/")
    uploads = await start_cloud_upload(client, page)
    await uploads.progress(page.config.ref, "0", 50)

    # When the browser reports that the cloud upload failed
    reply = await uploads.progress(page.config.ref, "0", {"error": "Connection lost"})

    # Then the progress callback sees the failure recorded on the half-finished file
    assert reply["status"] == "ok"
    socket = page.socket
    failed = [ConstraintViolation(ref="0", code="upload_failed")]
    assert seen == [(socket, 50, True, False, []), (socket, 50, False, False, failed)]

    # And the completion callback runs once, with the failure
    assert completed == [("0", UploadFailure(error="Connection lost"), socket)]


async def test_progress_callback_can_consume_a_completed_multipart_cloud_upload(connect):
    # Given an app that consumes cloud uploads as soon as its progress callback sees them complete
    consumed = []

    async def consume_completed(entry, socket) -> None:
        with page.config.consume_external_upload(entry.ref) as upload:
            if upload is not None:
                consumed.append((upload.ref, upload.done, upload.progress))

    page = DocumentsPage(external=presign, progress=consume_completed)
    client = connect({"/": page.view})
    await client.join("/")
    uploads = await start_cloud_upload(client, page)

    # When the browser reports multipart completion with its uploaded parts
    completion = {
        "complete": True,
        "upload_id": "upload-1",
        "parts": [{"PartNumber": 1, "ETag": "abc"}],
    }
    reply = await uploads.progress(page.config.ref, "0", completion)

    # Then the callback consumes the completed file, and it isn't restored afterwards
    assert reply["status"] == "ok"
    assert consumed == [("0", True, 100)]
    assert page.config.entries_by_ref == {}


async def test_progress_callback_runs_before_the_completion_callback_consumes_the_upload(connect):
    # Given an app that observes progress and consumes cloud uploads in its completion callback
    callbacks = []

    async def observe(entry, socket):
        callbacks.append(("progress", entry.done, entry.progress))

    async def consume_completed(entry, result, socket) -> None:
        with page.config.consume_external_upload(entry.ref):
            callbacks.append(("complete", result))

    page = DocumentsPage(external=presign, progress=observe, entry_complete=consume_completed)
    client = connect({"/": page.view})
    await client.join("/")
    uploads = await start_cloud_upload(client, page)

    # When the browser reports that the cloud upload reached 100 percent
    await uploads.progress(page.config.ref, "0", 100)

    # Then progress is observed as complete before the completion callback consumes the file
    assert callbacks == [("progress", True, 100), ("complete", UploadSuccess())]
    assert page.config.entries_by_ref == {}


async def test_progress_callback_can_consume_a_fully_received_local_upload(connect):
    # Given a local upload whose bytes have all arrived
    received = []

    async def consume_completed(entry, socket) -> None:
        with page.config.consume_upload_entry(entry.ref) as upload:
            if upload is not None:
                received.append(Path(upload.file.name).read_bytes())

    page = DocumentsPage(progress=consume_completed)
    client = connect({"/": page.view})
    await client.join("/")
    uploads = FakeUploadClient(client)
    tokens = await uploads.choose(page.config, [pdf()])
    upload = await uploads.join(tokens["0"])
    await upload.chunk(b"abcd")
    file = page.config.uploads.uploads[upload.join_ref].file

    # When the browser reports completion and the app consumes the file in its progress callback
    reply = await uploads.progress(page.config.ref, "0", 100)

    # Then the callback receives the complete file, and consuming it cleans it up
    assert reply["status"] == "ok"
    assert received == [b"abcd"]
    assert page.config.entries_by_ref == {}
    assert file.closed
    assert not Path(file.name).exists()
