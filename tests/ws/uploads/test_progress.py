"""Progress reports for uploads, and the app's progress and completion callbacks."""

from pathlib import Path
from typing import Any, Callable, Optional

from pyview.uploads import (
    ConstraintViolation,
    ExternalUploadMeta,
    UploadConfig,
    UploadConstraints,
    UploadFailure,
    UploadSuccess,
)

from ..fake_upload import FakeUploadClient
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


async def presign(entry, context) -> ExternalUploadMeta:
    return ExternalUploadMeta(uploader="S3")


def document_upload_view(
    configs: list[UploadConfig],
    sockets: Optional[list[Any]] = None,
    *,
    external: Optional[Callable] = None,
    progress: Optional[Callable] = None,
    entry_complete: Optional[Callable] = None,
):
    """A view with one "document" upload, using the given upload callbacks."""

    class Documents(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            if sockets is not None:
                sockets.append(socket)
            configs.append(
                socket.allow_upload(
                    "document",
                    UploadConstraints(accept=[".pdf"], max_files=1),
                    external=external,
                    progress=progress,
                    entry_complete=entry_complete,
                )
            )

    return Documents


async def start_cloud_upload(client, config: UploadConfig) -> FakeUploadClient:
    """Choose the PDF and have it approved for a direct-to-cloud upload."""
    uploads = FakeUploadClient(client)
    await uploads.select("document", config.ref, [PDF])
    await uploads.allow(config.ref, [PDF])
    return uploads


async def test_progress_callback_sees_a_cloud_upload_failure(connect):
    # Given a cloud upload, and an app that observes its progress and completion
    configs: list[UploadConfig] = []
    sockets: list[Any] = []
    seen = []
    completed = []

    async def observe(entry, socket):
        seen.append((socket, entry.progress, entry.valid, entry.done, list(entry.errors)))

    async def complete(entry, result, socket):
        completed.append((entry.ref, result, socket))

    client = connect(
        {
            "/": document_upload_view(
                configs, sockets, external=presign, progress=observe, entry_complete=complete
            )
        }
    )
    await client.join("/")
    uploads = await start_cloud_upload(client, configs[0])
    await uploads.progress(configs[0].ref, "0", 50)

    # When the browser reports that the cloud upload failed
    reply = await uploads.progress(configs[0].ref, "0", {"error": "Connection lost"})

    # Then the progress callback sees the failure recorded on the half-finished file
    assert reply["status"] == "ok"
    [socket] = sockets
    failed = [ConstraintViolation(ref="0", code="upload_failed")]
    assert seen == [(socket, 50, True, False, []), (socket, 50, False, False, failed)]

    # And the completion callback runs once, with the failure
    assert completed == [("0", UploadFailure(error="Connection lost"), socket)]


async def test_progress_callback_can_consume_a_completed_multipart_cloud_upload(connect):
    # Given an app that consumes cloud uploads as soon as its progress callback sees them complete
    configs: list[UploadConfig] = []
    consumed = []

    async def consume_completed(entry, socket):
        with configs[0].consume_external_upload(entry.ref) as upload:
            if upload is not None:
                consumed.append((upload.ref, upload.done, upload.progress))

    client = connect(
        {"/": document_upload_view(configs, external=presign, progress=consume_completed)}
    )
    await client.join("/")
    uploads = await start_cloud_upload(client, configs[0])

    # When the browser reports multipart completion with its uploaded parts
    completion = {
        "complete": True,
        "upload_id": "upload-1",
        "parts": [{"PartNumber": 1, "ETag": "abc"}],
    }
    reply = await uploads.progress(configs[0].ref, "0", completion)

    # Then the callback consumes the completed file, and it isn't restored afterwards
    assert reply["status"] == "ok"
    assert consumed == [("0", True, 100)]
    assert configs[0].entries_by_ref == {}


async def test_progress_callback_runs_before_the_completion_callback_consumes_the_upload(connect):
    # Given an app that observes progress and consumes cloud uploads in its completion callback
    configs: list[UploadConfig] = []
    callbacks = []

    async def observe(entry, socket):
        callbacks.append(("progress", entry.done, entry.progress))

    async def consume_completed(entry, result, socket):
        with configs[0].consume_external_upload(entry.ref):
            callbacks.append(("complete", result))

    client = connect(
        {
            "/": document_upload_view(
                configs, external=presign, progress=observe, entry_complete=consume_completed
            )
        }
    )
    await client.join("/")
    uploads = await start_cloud_upload(client, configs[0])

    # When the browser reports that the cloud upload reached 100 percent
    await uploads.progress(configs[0].ref, "0", 100)

    # Then progress is observed as complete before the completion callback consumes the file
    assert callbacks == [("progress", True, 100), ("complete", UploadSuccess())]
    assert configs[0].entries_by_ref == {}


async def test_progress_callback_can_consume_a_fully_received_local_upload(connect):
    # Given a local upload whose bytes have all arrived
    configs: list[UploadConfig] = []
    received = []

    async def consume_completed(entry, socket):
        with configs[0].consume_upload_entry(entry.ref) as upload:
            if upload is not None:
                received.append(Path(upload.file.name).read_bytes())

    client = connect({"/": document_upload_view(configs, progress=consume_completed)})
    await client.join("/")
    uploads = FakeUploadClient(client)
    await uploads.select("document", configs[0].ref, [PDF])
    token = (await uploads.allow(configs[0].ref, [PDF]))["response"]["entries"]["0"]
    upload = await uploads.join(token)
    await upload.chunk(b"abcd")
    file = configs[0].uploads.uploads[upload.join_ref].file

    # When the browser reports completion and the app consumes the file in its progress callback
    reply = await uploads.progress(configs[0].ref, "0", 100)

    # Then the callback receives the complete file, and consuming it cleans it up
    assert reply["status"] == "ok"
    assert received == [b"abcd"]
    assert configs[0].entries_by_ref == {}
    assert file.closed
    assert not Path(file.name).exists()
