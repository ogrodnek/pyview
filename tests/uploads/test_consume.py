from pathlib import Path

import pytest

from pyview.uploads import UploadConstraints, UploadInProgressError, UploadManager


@pytest.fixture
async def approved_upload():
    manager = UploadManager()
    config = manager.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
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
    try:
        manager.add_upload("upload-join", {"token": response["entries"]["0"]})
        yield manager, config, config.uploads.uploads["upload-join"]
    finally:
        manager.close()


async def test_consuming_incomplete_upload_preserves_it_for_completion(approved_upload):
    # Given an approved four-byte file with only its first two bytes received
    manager, config, upload = approved_upload
    manager.add_chunk("upload-join", b"ab")
    temporary_path = Path(upload.file.name)

    # When the app tries to consume the file before all its bytes arrive
    # Then it receives a clear error before gaining access to the partial file
    with (
        pytest.raises(UploadInProgressError, match="Cannot consume.*still in progress"),
        config.consume_upload_entry("0"),
    ):
        pytest.fail("An incomplete upload must not be yielded for consumption")

    # And the upload and its received bytes remain available to finish uploading
    assert not upload.file.closed
    assert temporary_path.read_bytes() == b"ab"
    assert config.uploads.uploads["upload-join"] is upload
    assert "0" in config.entries_by_ref
    manager.add_chunk("upload-join", b"cd")
    assert temporary_path.read_bytes() == b"abcd"


async def test_consuming_fully_received_upload_yields_file_and_cleans_up(approved_upload):
    # Given an approved four-byte file with all four bytes received
    manager, config, upload = approved_upload
    manager.add_chunk("upload-join", b"abcd")
    temporary_path = Path(upload.file.name)

    # When the app consumes the completed file
    with config.consume_upload_entry("0") as consumed:
        # Then it can access the complete file during consumption
        assert consumed is upload
        assert not consumed.file.closed
        assert temporary_path.read_bytes() == b"abcd"

    # And the temporary file and upload entry are removed afterward
    assert upload.file.closed
    assert not temporary_path.exists()
    assert config.uploads.uploads == {}
    assert config.entries_by_ref == {}
