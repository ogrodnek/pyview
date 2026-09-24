from pathlib import Path

from pyview.uploads import UploadConstraints, UploadManager


async def test_canceling_upload_removes_temporary_file_and_prevents_consumption():
    # Given an approved PDF upload with some bytes already received
    manager = UploadManager()
    config = manager.allow_upload(
        "document",
        UploadConstraints(accept=[".pdf"], max_files=1),
    )
    file = {
        "ref": "0",
        "name": "example.pdf",
        "type": "application/pdf",
        "size": 4,
        "path": "document",
    }
    config.add_entries([file])
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [file]}, context=None
    )
    manager.add_upload("upload-join", {"token": response["entries"]["0"]})
    try:
        manager.add_chunk("upload-join", b"ab")
        upload = config.uploads.uploads["upload-join"]
        temporary_path = Path(upload.file.name)
        assert temporary_path.read_bytes() == b"ab"

        # When the user cancels the file
        config.cancel_entry("0")

        # Then its temporary file is closed and deleted
        assert upload.file.closed
        assert not temporary_path.exists()

        # And the file is no longer listed or available for consumption
        assert "0" not in config.entries_by_ref
        assert "upload-join" not in config.uploads.uploads
        with config.consume_uploads() as uploads:
            assert uploads == []
    finally:
        manager.close()


async def test_chunk_arriving_after_cancellation_is_ignored():
    # Given a PDF upload canceled after some bytes were received
    manager = UploadManager()
    config = manager.allow_upload(
        "document",
        UploadConstraints(accept=[".pdf"], max_files=1),
    )
    file = {
        "ref": "0",
        "name": "example.pdf",
        "type": "application/pdf",
        "size": 4,
        "path": "document",
    }
    config.add_entries([file])
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [file]}, context=None
    )
    manager.add_upload("upload-join", {"token": response["entries"]["0"]})
    try:
        manager.add_chunk("upload-join", b"ab")
        upload = config.uploads.uploads["upload-join"]
        temporary_path = Path(upload.file.name)
        config.cancel_entry("0")

        # When bytes already in transit arrive for the canceled upload
        manager.add_chunk("upload-join", b"cd")

        # Then they are ignored without reopening the file or restoring the upload
        assert upload.file.closed
        assert not temporary_path.exists()
        assert config.uploads.uploads == {}
        assert config.entries_by_ref == {}
    finally:
        manager.close()
