from pyview.uploads import UploadConstraints, UploadManager


async def test_selecting_another_file_preserves_existing_upload_state():
    # Given an approved PDF upload that is halfway finished
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
