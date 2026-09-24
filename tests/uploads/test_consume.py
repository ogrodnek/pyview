from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from pyview.uploads import (
    ExternalUploadMeta,
    UploadConstraints,
    UploadInProgressError,
    UploadManager,
)


async def test_consuming_incomplete_external_upload_preserves_it_for_completion():
    # Given an approved cloud upload that is halfway finished
    metadata = ExternalUploadMeta(uploader="S3", url="https://example.com/upload")
    manager = UploadManager()
    config = manager.allow_upload(
        "document",
        UploadConstraints(accept=[".pdf"], max_files=1),
        external=AsyncMock(return_value=metadata),
    )
    file = {
        "ref": "0",
        "name": "example.pdf",
        "type": "application/pdf",
        "size": 4,
        "path": "document",
    }
    config.add_entries([file])
    await manager.process_allow_upload({"ref": config.ref, "entries": [file]}, context=None)
    config.update_progress("0", 50)
    entry = config.entries_by_ref["0"]

    # When the app tries to consume the file before the cloud upload finishes
    # Then it receives a clear error before gaining access to the unfinished upload
    with (
        pytest.raises(UploadInProgressError, match="Cannot consume upload '0'.*still in progress"),
        config.consume_external_upload("0"),
    ):
        pytest.fail("An incomplete cloud upload must not be yielded for consumption")

    # And the upload keeps its metadata and progress so it can finish
    assert config.entries_by_ref["0"] is entry
    assert entry.meta == metadata
    assert entry.progress == 50

    # When the upload finishes and the app retries consumption
    config.update_progress("0", 100)
    with config.consume_external_upload("0") as consumed:
        # Then the completed upload is available and is removed only after consumption
        assert consumed is entry
        assert consumed.done
        assert config.entries_by_ref["0"] is entry
    assert "0" not in config.entries_by_ref


async def test_consuming_incomplete_external_batch_preserves_all_entries():
    # Given two approved cloud uploads, one complete and one halfway finished
    metadata = ExternalUploadMeta(uploader="S3", url="https://example.com/upload")
    manager = UploadManager()
    config = manager.allow_upload(
        "documents",
        UploadConstraints(accept=[".pdf"], max_files=2),
        external=AsyncMock(return_value=metadata),
    )
    first_file = {
        "ref": "0",
        "name": "first.pdf",
        "type": "application/pdf",
        "size": 4,
        "path": "documents",
    }
    second_file = {**first_file, "ref": "1", "name": "second.pdf"}
    config.add_entries([first_file, second_file])
    await manager.process_allow_upload(
        {"ref": config.ref, "entries": [first_file, second_file]}, context=None
    )
    config.update_progress("0", 100)
    config.update_progress("1", 50)
    first_entry = config.entries_by_ref["0"]
    second_entry = config.entries_by_ref["1"]

    # When the app tries to consume the batch before the second upload finishes
    # Then it receives a clear error before gaining access to either upload
    with (
        pytest.raises(UploadInProgressError, match="Cannot consume upload '1'.*still in progress"),
        config.consume_external_uploads(),
    ):
        pytest.fail("An incomplete cloud upload batch must not be yielded for consumption")

    # And both uploads keep their metadata and progress so the batch can finish
    assert config.entries_by_ref["0"] is first_entry
    assert config.entries_by_ref["1"] is second_entry
    assert first_entry.meta == second_entry.meta == metadata
    assert first_entry.progress == 100
    assert second_entry.progress == 50

    # When the second upload finishes and the app retries consumption
    config.update_progress("1", 100)
    with config.consume_external_uploads() as consumed:
        # Then both completed uploads are available and are removed only after consumption
        assert consumed == [first_entry, second_entry]
        assert all(entry.done for entry in consumed)
        assert set(config.entries_by_ref) == {"0", "1"}
    assert config.entries_by_ref == {}


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


def test_consuming_unstarted_upload_preserves_selection():
    # Given a selected PDF whose upload has not started
    manager = UploadManager()
    config = manager.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
    config.add_entries(
        [
            {
                "ref": "0",
                "name": "example.pdf",
                "type": "application/pdf",
                "size": 4,
                "path": "document",
            }
        ]
    )
    selected_entry = config.entries_by_ref["0"]

    # When the app tries to consume the file before its upload starts
    # Then it receives an in-progress error instead of treating the file as missing
    with (
        pytest.raises(UploadInProgressError, match="Cannot consume upload '0'.*still in progress"),
        config.consume_upload_entry("0"),
    ):
        pytest.fail("A selected file whose upload has not started must not be yielded")

    # And the selection remains available to upload later
    assert config.entries_by_ref["0"] is selected_entry
    assert config.uploads.uploads == {}


async def test_consuming_unknown_ref_yields_none_without_affecting_selected_file(approved_upload):
    # Given an existing upload and a ref that does not belong to any selected file
    _, config, upload = approved_upload

    # When the app tries to consume the unknown ref
    with config.consume_upload_entry("unknown") as consumed:
        # Then it receives no file
        assert consumed is None

    # And the existing upload and selection remain intact
    assert not upload.file.closed
    assert Path(upload.file.name).exists()
    assert config.uploads.uploads["upload-join"] is upload
    assert set(config.entries_by_ref) == {"0"}


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


async def test_consuming_batch_with_unstarted_upload_preserves_both_entries():
    # Given two selected PDFs, with the first fully received and the second not yet uploading
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
        {"ref": config.ref, "entries": [first_file]}, context=None
    )
    try:
        manager.add_upload("first-join", {"token": response["entries"]["0"]})
        manager.add_chunk("first-join", b"abcd")
        first_upload = config.uploads.uploads["first-join"]
        first_path = Path(first_upload.file.name)
        second_entry = config.entries_by_ref["1"]

        # When the app tries to consume the batch before the second upload starts
        # Then it receives a clear error before gaining access to the completed file
        with (
            pytest.raises(
                UploadInProgressError, match="Cannot consume upload '1'.*still in progress"
            ),
            config.consume_uploads(),
        ):
            pytest.fail("A batch containing a file that has not started must not be yielded")

        # And the completed file and the waiting selection are both preserved
        assert not first_upload.file.closed
        assert first_path.read_bytes() == b"abcd"
        assert config.uploads.uploads["first-join"] is first_upload
        assert set(config.entries_by_ref) == {"0", "1"}
        assert config.entries_by_ref["1"] is second_entry

        # And the second file can still be approved and uploaded
        response = await manager.process_allow_upload(
            {"ref": config.ref, "entries": [second_file]}, context=None
        )
        manager.add_upload("second-join", {"token": response["entries"]["1"]})
        manager.add_chunk("second-join", b"efgh")
        with config.consume_uploads() as uploads:
            assert {upload.entry.ref for upload in uploads} == {"0", "1"}
            assert all(upload.is_complete for upload in uploads)
    finally:
        manager.close()
