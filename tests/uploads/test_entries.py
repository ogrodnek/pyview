from pathlib import Path

import pytest

from pyview.uploads import UploadConstraints, UploadManager

from .factories import upload_entry_data


async def test_selecting_another_file_preserves_existing_upload_state():
    # Given an approved PDF upload that is halfway finished
    manager = UploadManager()
    config = manager.allow_upload(
        "documents",
        UploadConstraints(accept=[".pdf"], max_files=2),
        auto_upload=True,
    )
    first_file = upload_entry_data(
        name="first.pdf", file_type="application/pdf", size=4, path=config.name
    )
    config.add_entries([first_file])
    await manager.process_allow_upload({"ref": config.ref, "entries": [first_file]}, context=None)
    config.update_progress("0", 50)

    # When another PDF is selected and the browser includes the original file again
    second_file = {**first_file, "ref": "1", "name": "second.pdf"}
    config.add_entries([first_file, second_file])

    # Then the original upload keeps its approval and progress
    assert config.entries_by_ref["0"].preflighted
    assert config.entries_by_ref["0"].progress == 50
    assert not config.entries_by_ref["0"].done

    # And the new file is registered once, ready to request its own upload approval
    assert set(config.entries_by_ref) == {"0", "1"}
    assert not config.entries_by_ref["1"].preflighted
    assert config.entries_by_ref["1"].progress == 0


@pytest.mark.parametrize("upload_started", [False, True], ids=["selected", "uploading"])
async def test_new_selection_replaces_file_in_single_file_input(upload_started):
    # Given a single-file input with a PDF selected, possibly already uploading
    manager = UploadManager()
    config = manager.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
    first_file = upload_entry_data(
        name="draft.pdf", file_type="application/pdf", size=4, path=config.name
    )
    config.add_entries([first_file])
    upload = None
    try:
        if upload_started:
            response = await manager.process_allow_upload(
                {"ref": config.ref, "entries": [first_file]}, context=None
            )
            manager.add_upload("first-join", {"token": response["entries"]["0"]})
            manager.add_chunk("first-join", b"ab")
            upload = config.uploads.uploads["first-join"]

        # When the user selects a different PDF without explicitly canceling the first
        second_file = {**first_file, "ref": "1", "name": "final.pdf"}
        config.add_entries([second_file])

        # Then only the replacement is selected, awaiting approval with no upload errors
        assert set(config.entries_by_ref) == {"1"}
        assert config.entries_by_ref["1"].name == "final.pdf"
        assert not config.entries_by_ref["1"].preflighted
        assert config.errors == []

        # And any upload and temporary file belonging to the previous selection are removed
        assert config.uploads.uploads == {}
        if upload is not None:
            assert upload.file.closed
            assert not Path(upload.file.name).exists()
    finally:
        manager.close()
