from pathlib import Path


async def test_canceling_upload_removes_temporary_file_and_prevents_consumption(started_upload):
    # Given an approved PDF upload with some bytes already received
    manager, config, upload = started_upload
    manager.add_chunk("upload-join", b"ab")
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


async def test_chunk_arriving_after_cancellation_is_ignored(started_upload):
    # Given a PDF upload canceled after some bytes were received
    manager, config, upload = started_upload
    manager.add_chunk("upload-join", b"ab")
    temporary_path = Path(upload.file.name)
    config.cancel_entry("0")

    # When bytes already in transit arrive for the canceled upload
    manager.add_chunk("upload-join", b"cd")

    # Then they are ignored without reopening the file or restoring the upload
    assert upload.file.closed
    assert not temporary_path.exists()
    assert config.uploads.uploads == {}
    assert config.entries_by_ref == {}
