from pyview.uploads import UploadConstraints, UploadJoinResult, UploadManager

from .factories import upload_entry_data


def test_upload_join_rejects_browser_supplied_approval():
    # Given a selected PDF whose browser metadata claims it already has upload approval
    manager = UploadManager()
    config = manager.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
    file = {**upload_entry_data(path=config.name), "preflighted": True}
    config.add_entries([file])
    try:
        # When the browser starts uploading without requesting approval from the server
        result = manager.add_upload("upload-join", {"token": file})

        # Then the join is rejected and the file remains unapproved
        assert result is UploadJoinResult.DISALLOWED
        assert not config.entries_by_ref["0"].preflighted
        assert config.uploads.uploads == {}
        assert manager.upload_config_join_refs == {}
    finally:
        manager.close()


async def test_upload_join_uses_registered_file_metadata():
    # Given a four-byte PDF selected and approved for direct upload
    manager = UploadManager()
    config = manager.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
    file = upload_entry_data(
        name="example.pdf", file_type="application/pdf", size=4, path=config.name
    )
    config.add_entries([file])
    response = await manager.process_allow_upload(
        {"ref": config.ref, "entries": [file]}, context=None
    )
    try:
        # When the browser starts that upload but supplies a different name, size, and type
        token = {
            **response["entries"]["0"],
            "name": "different.txt",
            "size": 1000,
            "type": "text/plain",
        }
        result = manager.add_upload("upload-join", {"token": token})

        # Then the upload uses the file metadata recorded when it was selected
        assert result is UploadJoinResult.ACCEPTED
        upload = config.uploads.uploads["upload-join"]
        assert upload.entry.name == "example.pdf"
        assert upload.entry.size == 4
        assert upload.entry.type == "application/pdf"

        # And receiving bytes does not overwrite the selected file's percentage progress
        manager.add_chunk("upload-join", b"ab")
        assert config.entries_by_ref["0"].progress == 0
    finally:
        manager.close()
