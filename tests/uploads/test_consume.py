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


@pytest.fixture
async def approved_upload_batch():
    manager = UploadManager()
    config = manager.allow_upload("documents", UploadConstraints(accept=[".pdf"], max_files=2))
    first_file = {
        "ref": "0",
        "name": "first.pdf",
        "type": "application/pdf",
        "size": 4,
        "path": "documents",
    }
    second_file = {**first_file, "ref": "1", "name": "second.pdf"}
    config.add_entries([first_file, second_file])
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [first_file, second_file]}, context=None
    )
    try:
        manager.add_upload("first-join", {"token": response["entries"]["0"]})
        manager.add_upload("second-join", {"token": response["entries"]["1"]})
        yield (
            manager,
            config,
            config.uploads.uploads["first-join"],
            config.uploads.uploads["second-join"],
        )
    finally:
        manager.close()


async def test_consuming_batch_with_incomplete_upload_preserves_all_files(approved_upload_batch):
    # Given two uploads, one fully received and the other only halfway uploaded
    manager, config, first_upload, second_upload = approved_upload_batch
    manager.add_chunk("first-join", b"abcd")
    manager.add_chunk("second-join", b"ef")
    first_path = Path(first_upload.file.name)
    second_path = Path(second_upload.file.name)

    # When the app tries to consume the batch before the second file finishes
    # Then it receives a clear error before gaining access to either file
    with (
        pytest.raises(UploadInProgressError, match="Cannot consume.*still in progress"),
        config.consume_uploads(),
    ):
        pytest.fail("A batch containing an incomplete upload must not be yielded")

    # And both files and their upload entries remain available
    assert not first_upload.file.closed
    assert not second_upload.file.closed
    assert first_path.read_bytes() == b"abcd"
    assert second_path.read_bytes() == b"ef"
    assert config.uploads.uploads["first-join"] is first_upload
    assert config.uploads.uploads["second-join"] is second_upload
    assert set(config.entries_by_ref) == {"0", "1"}

    # And the incomplete file can finish uploading
    manager.add_chunk("second-join", b"gh")
    assert second_path.read_bytes() == b"efgh"


async def test_consuming_fully_received_batch_yields_files_and_cleans_up(approved_upload_batch):
    # Given two uploads with all their bytes received
    manager, config, first_upload, second_upload = approved_upload_batch
    manager.add_chunk("first-join", b"abcd")
    manager.add_chunk("second-join", b"efgh")
    first_path = Path(first_upload.file.name)
    second_path = Path(second_upload.file.name)

    # When the app consumes the batch
    with config.consume_uploads() as consumed:
        # Then it can access both complete files during consumption
        assert consumed == [first_upload, second_upload]
        assert not first_upload.file.closed
        assert not second_upload.file.closed
        assert first_path.read_bytes() == b"abcd"
        assert second_path.read_bytes() == b"efgh"

    # And both temporary files and their upload entries are removed afterward
    assert first_upload.file.closed
    assert second_upload.file.closed
    assert not first_path.exists()
    assert not second_path.exists()
    assert config.uploads.uploads == {}
    assert config.entries_by_ref == {}
