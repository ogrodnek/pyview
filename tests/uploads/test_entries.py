from pathlib import Path

from pyview.uploads import UploadConstraints, UploadManager

from .factories import upload_entry_data


def test_selecting_file_ignores_browser_supplied_upload_state():
    # Given a PDF input and browser metadata claiming a file is finished, canceled, and invalid
    manager = UploadManager()
    config = manager.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
    file = {
        **upload_entry_data(path=config.name),
        "last_modified": 1700000000000,
        "uuid": "browser-supplied-id",
        "upload_config": {"name": "other-input"},
        "valid": False,
        "errors": [{"ref": "0", "code": "upload_failed"}],
        "progress": 100,
        "done": True,
        "cancelled": True,
        "meta": {"uploader": "browser-supplied-uploader"},
    }

    # When the file is selected
    config.add_entries([file])

    # Then its upload state starts fresh, with its identity and validation owned by the server
    entry = config.entries_by_ref["0"]
    assert entry.uuid != "browser-supplied-id"
    assert entry.upload_config is config
    assert entry.valid
    assert entry.errors == []
    assert entry.progress == 0
    assert not entry.done
    assert not entry.cancelled
    assert entry.meta is None

    # And the file's browser metadata is preserved
    assert entry.ref == "0"
    assert entry.name == "example.pdf"
    assert entry.size == 4
    assert entry.type == "application/pdf"
    assert entry.path == config.name
    assert entry.last_modified == 1700000000000


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


def test_new_selection_replaces_selected_file_in_single_file_input():
    # Given a single-file input with a PDF selected whose upload has not started
    manager = UploadManager()
    config = manager.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
    first_file = upload_entry_data(
        name="draft.pdf", file_type="application/pdf", size=4, path=config.name
    )
    config.add_entries([first_file])

    # When the user selects a different PDF without explicitly canceling the first
    second_file = {**first_file, "ref": "1", "name": "final.pdf"}
    config.add_entries([second_file])

    # Then only the replacement is selected, awaiting approval with no upload errors
    assert set(config.entries_by_ref) == {"1"}
    assert config.entries_by_ref["1"].name == "final.pdf"
    assert not config.entries_by_ref["1"].preflighted
    assert config.errors == []
    assert config.uploads.uploads == {}


async def test_new_selection_replaces_in_progress_upload_in_single_file_input(started_upload):
    # Given a single-file input with a four-byte PDF upload that is halfway received
    manager, config, upload = started_upload
    manager.add_chunk("upload-join", b"ab")
    temporary_path = Path(upload.file.name)

    # When the user selects a different PDF without explicitly canceling the upload
    replacement = upload_entry_data(
        ref="1", name="final.pdf", file_type="application/pdf", size=4, path=config.name
    )
    config.add_entries([replacement])

    # Then only the replacement is selected, awaiting approval with no upload errors
    assert set(config.entries_by_ref) == {"1"}
    assert config.entries_by_ref["1"].name == "final.pdf"
    assert not config.entries_by_ref["1"].preflighted
    assert config.errors == []

    # And the previous upload is removed and its temporary file is closed and deleted
    assert config.uploads.uploads == {}
    assert upload.file.closed
    assert not temporary_path.exists()
