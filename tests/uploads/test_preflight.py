import pytest

from pyview.uploads import UploadConstraints, UploadManager, live_file_input


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
