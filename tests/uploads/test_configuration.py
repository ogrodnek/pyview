from pathlib import Path

import pytest

from pyview.uploads import UploadConfigurationInUseError, UploadConstraints, UploadManager

from .factories import upload_entry_data


def test_reconfiguring_upload_with_selected_file_preserves_configuration():
    # Given a PDF input with a selected file that has not started uploading
    manager = UploadManager()
    config = manager.allow_upload("document", UploadConstraints(accept=[".pdf"], max_files=1))
    config.add_entries([upload_entry_data(path=config.name)])
    entry = config.entries_by_ref["0"]

    # When the app tries to change that input to accept images
    # Then it is told to consume or cancel the selected file first
    with pytest.raises(
        UploadConfigurationInUseError,
        match="Cannot reconfigure upload 'document': consume or cancel its existing entries first",
    ):
        manager.allow_upload("document", UploadConstraints(accept=["image/*"]))

    # And the original input and selected file remain available
    assert manager.config_for_name("document") is config
    assert config.entries_by_ref["0"] is entry
    assert config.constraints.accept == [".pdf"]


async def test_reconfiguring_active_upload_preserves_received_file(started_upload):
    # Given a PDF upload that has received half of its bytes
    manager, config, upload = started_upload
    manager.add_chunk("upload-join", b"ab")
    temporary_path = Path(upload.file.name)
    try:
        # When the app tries to replace its upload configuration
        # Then replacement is rejected and the original upload remains usable
        with pytest.raises(UploadConfigurationInUseError):
            manager.allow_upload("document", UploadConstraints(accept=["image/*"]))

        assert manager.config_for_name("document") is config
        assert manager.upload_config_join_refs["upload-join"] is config
        assert config.uploads.for_entry("0") is upload
        assert not upload.file.closed
        assert temporary_path.read_bytes() == b"ab"
        manager.add_chunk("upload-join", b"cd")
        assert temporary_path.read_bytes() == b"abcd"
    finally:
        config.cancel_entry("0")


def test_reconfiguring_empty_upload_updates_configuration():
    # Given a PDF input with no selected files
    manager = UploadManager()
    original = manager.allow_upload("document", UploadConstraints(accept=[".pdf"]))

    # When the app changes the input to accept images
    replacement = manager.allow_upload("document", UploadConstraints(accept=["image/*"]))

    # Then the new configuration replaces the empty input
    assert manager.config_for_name("document") is replacement
    assert replacement.ref != original.ref
    assert replacement.constraints.accept == ["image/*"]


async def test_reconfiguring_upload_after_cancellation_succeeds(started_upload):
    # Given an upload whose last file was canceled
    manager, config, upload = started_upload
    temporary_path = Path(upload.file.name)
    config.cancel_entry("0")

    # When the app changes the input to accept images
    replacement = manager.allow_upload("document", UploadConstraints(accept=["image/*"]))

    # Then the new configuration is available and the canceled file stays cleaned up
    assert manager.config_for_name("document") is replacement
    assert replacement.ref != config.ref
    assert replacement.constraints.accept == ["image/*"]
    assert upload.file.closed
    assert not temporary_path.exists()


async def test_reconfiguring_upload_after_consumption_succeeds(started_upload):
    # Given an upload whose last file finished and was consumed
    manager, config, upload = started_upload
    temporary_path = Path(upload.file.name)
    manager.add_chunk("upload-join", b"abcd")
    with config.consume_uploads():
        pass

    # When the app changes the input to accept images
    replacement = manager.allow_upload("document", UploadConstraints(accept=["image/*"]))

    # Then the new configuration is available and the consumed file stays cleaned up
    assert manager.config_for_name("document") is replacement
    assert replacement.ref != config.ref
    assert replacement.constraints.accept == ["image/*"]
    assert upload.file.closed
    assert not temporary_path.exists()
