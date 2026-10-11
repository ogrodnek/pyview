from pyview.uploads import UploadChunkResult


async def test_oversized_chunk_unregisters_its_upload_channel(started_upload):
    # Given an approved four-byte PDF with two bytes already received
    manager, config, upload = started_upload
    manager.add_chunk("upload-join", b"ab")

    # When another chunk would exceed the file's declared size
    result = manager.add_chunk("upload-join", b"cde")

    # Then the chunk is rejected and the channel no longer maps to the upload
    assert result is UploadChunkResult.FILE_SIZE_LIMIT_EXCEEDED
    assert manager.upload_config_join_refs == {}


async def test_received_bytes_are_counted_separately_from_percentage_progress(started_upload):
    # Given a four-byte upload with two bytes received and the browser reporting 50 percent
    manager, config, upload = started_upload
    manager.add_chunk("upload-join", b"ab")
    config.update_progress("0", 50)
    assert not upload.is_complete

    # When the remaining two bytes arrive before another browser progress update
    manager.add_chunk("upload-join", b"cd")

    # Then the byte count includes both chunks and the file is complete
    assert upload.bytes_received == 4
    assert upload.is_complete
    assert not config.uploads.no_progress()

    # And receiving bytes does not turn either entry's percentage progress into a byte count
    assert config.entries_by_ref["0"].progress == 50
    assert upload.entry.progress == 0
