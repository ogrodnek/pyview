from unittest.mock import AsyncMock

import pytest

from pyview.uploads import ExternalUploadMeta, UploadConstraints, UploadManager, live_file_input


@pytest.mark.parametrize("auto_upload", [False, True], ids=["on-submit", "auto-upload"])
async def test_internal_preflight_updates_entry_and_file_input(auto_upload):
    # Given a selected PDF that is allowed to upload directly to the server
    manager = UploadManager()
    config = manager.allow_upload(
        "document",
        UploadConstraints(accept=[".pdf"], max_files=1),
        auto_upload=auto_upload,
    )
    entry = {
        "ref": "0",
        "name": "example.pdf",
        "type": "application/pdf",
        "size": 4,
        "path": "document",
    }
    config.add_entries([entry])

    # When the browser requests permission to upload the file
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [entry]}, context=None
    )

    # Then the file is approved for upload, but has not finished uploading
    assert "error" not in response
    assert set(response["entries"]) == {"0"}
    assert config.entries_by_ref["0"].preflighted
    assert not config.entries_by_ref["0"].done

    # And the file input tells the browser that the file is preflighted, not completed
    html = str(live_file_input(config))
    assert 'data-phx-preflighted-refs="0"' in html
    assert 'data-phx-done-refs=""' in html


async def test_internal_preflight_rejects_file_with_unaccepted_type():
    # Given a JPG selected for an upload input that accepts only PDFs
    manager = UploadManager()
    config = manager.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
    file = {
        "ref": "0",
        "name": "photo.jpg",
        "type": "image/jpeg",
        "size": 4,
        "path": "document",
    }
    config.add_entries([file])

    # When the browser requests permission to upload the rejected file
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [file]}, context=None
    )

    # Then the file-type error is returned and the file remains unapproved
    assert response == {"error": [("0", "not_accepted")]}
    assert not config.entries_by_ref["0"].preflighted


async def test_internal_preflight_only_approves_requested_files():
    # Given two selected PDFs that are waiting for upload approval
    manager = UploadManager()
    config = manager.allow_upload(
        "documents",
        UploadConstraints(accept=[".pdf"], max_files=2),
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

    # When the browser requests permission to upload only the second file
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [second_file]}, context=None
    )

    # Then only the second file is returned and approved for upload
    assert "error" not in response
    assert set(response["entries"]) == {"1"}
    assert config.entries_by_ref["1"].preflighted
    assert not config.entries_by_ref["0"].preflighted


async def test_regular_preflight_rejects_selection_over_file_limit():
    # Given three selected PDFs in an input that allows two files uploaded on submit
    manager = UploadManager()
    config = manager.allow_upload(
        "documents",
        UploadConstraints(accept=[".pdf"], max_files=2),
        auto_upload=False,
    )
    first_file = {
        "ref": "0",
        "name": "first.pdf",
        "type": "application/pdf",
        "size": 4,
        "path": "documents",
    }
    second_file = {**first_file, "ref": "1", "name": "second.pdf"}
    third_file = {**first_file, "ref": "2", "name": "third.pdf"}
    config.add_entries([first_file, second_file, third_file])

    # When the browser requests permission to upload just the first file
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [first_file]}, context=None
    )

    # Then the whole selection exceeds the limit and no file is approved
    assert response == {"error": [(config.ref, "too_many_files")]}
    assert all(not entry.preflighted for entry in config.entries)


async def test_auto_preflight_approves_files_up_to_selection_limit():
    # Given three selected PDFs in an input that automatically uploads at most two files
    manager = UploadManager()
    config = manager.allow_upload(
        "documents",
        UploadConstraints(accept=[".pdf"], max_files=2),
        auto_upload=True,
    )
    first_file = {
        "ref": "0",
        "name": "first.pdf",
        "type": "application/pdf",
        "size": 4,
        "path": "documents",
    }
    second_file = {**first_file, "ref": "1", "name": "second.pdf"}
    third_file = {**first_file, "ref": "2", "name": "third.pdf"}
    config.add_entries([first_file, second_file, third_file])

    # When the browser requests permission to upload all three files
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [first_file, second_file, third_file]}, context=None
    )

    # Then the first two files are approved and the extra file remains unapproved
    assert "error" not in response
    assert set(response["entries"]) == {"0", "1"}
    assert config.entries_by_ref["0"].preflighted
    assert config.entries_by_ref["1"].preflighted
    assert not config.entries_by_ref["2"].preflighted
    assert [error.code for error in config.errors] == ["too_many_files"]


async def test_internal_preflight_skips_already_approved_file():
    # Given a PDF approved for direct upload that is halfway finished
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
    await manager.process_allow_upload({"ref": config.ref, "entries": [file]}, context=None)
    config.update_progress("0", 50)
    approved_entry = config.entries_by_ref["0"]

    # When the browser requests upload approval for the same file again
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [file]}, context=None
    )

    # Then no newly approved entries are returned to the browser
    assert "error" not in response
    assert response["entries"] == {}

    # And the existing upload keeps its approval and progress
    assert config.entries_by_ref["0"] is approved_entry
    assert approved_entry.preflighted
    assert approved_entry.progress == 50


async def test_external_preflight_rejects_file_before_presigning():
    # Given a JPG selected for a cloud upload input that accepts only PDFs
    metadata = ExternalUploadMeta(uploader="S3", url="https://example.com/upload")
    presign = AsyncMock(return_value=metadata)
    manager = UploadManager()
    config = manager.allow_upload(
        "document",
        UploadConstraints(accept=[".pdf"], max_files=1),
        external=presign,
    )
    file = {
        "ref": "0",
        "name": "photo.jpg",
        "type": "image/jpeg",
        "size": 4,
        "path": "document",
    }
    config.add_entries([file])

    # When the browser requests permission to upload the rejected file
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [file]}, context=None
    )

    # Then the file-type error is returned without requesting a signed upload
    assert response == {"error": [("0", "not_accepted")]}
    presign.assert_not_called()
    assert not config.entries_by_ref["0"].preflighted


async def test_external_preflight_skips_already_approved_file():
    # Given a PDF approved for cloud upload that is halfway finished
    metadata = ExternalUploadMeta(uploader="S3", url="https://example.com/upload")
    presign = AsyncMock(return_value=metadata)
    manager = UploadManager()
    config = manager.allow_upload(
        "document",
        UploadConstraints(accept=[".pdf"], max_files=1),
        external=presign,
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
    approved_entry = config.entries_by_ref["0"]
    presign.assert_awaited_once()

    # When the browser requests upload approval for the same file again
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [file]}, context=None
    )

    # Then no new upload is signed or returned to the browser
    presign.assert_awaited_once()
    assert "error" not in response
    assert response["entries"] == {}

    # And the existing upload keeps its approval, metadata, and progress
    assert config.entries_by_ref["0"] is approved_entry
    assert approved_entry.preflighted
    assert approved_entry.meta == metadata
    assert approved_entry.progress == 50
