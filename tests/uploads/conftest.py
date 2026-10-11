import pytest

from pyview.uploads import UploadConstraints, UploadManager

from .factories import upload_entry_data


@pytest.fixture
async def started_upload():
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
        manager.add_upload("upload-join", {"token": response["entries"]["0"]})
        yield manager, config, config.uploads.uploads["upload-join"]
    finally:
        manager.close()
