import pytest

from pyview.uploads import UploadConfig, UploadConstraints

from .factories import upload_entry_data


def selected_file(config, name, file_type):
    config.add_entries(
        [upload_entry_data(name=name, file_type=file_type, size=4, path=config.name)]
    )
    return config.entries_by_ref["0"]


def test_pdf_only_input_rejects_jpg():
    # Given an upload input that accepts only PDF extensions
    config = UploadConfig(name="document", constraints=UploadConstraints(accept=[".pdf"]))

    # When a JPG is selected
    entry = selected_file(config, "photo.jpg", "image/jpeg")

    # Then the file is invalid with a clear file-type error
    assert not entry.valid
    assert [error.code for error in entry.errors] == ["not_accepted"]
    assert entry.errors[0].ref == "0"
    assert entry.errors[0].message == "File type not accepted"


def test_pdf_only_input_accepts_pdf():
    # Given an upload input that accepts only PDF extensions
    config = UploadConfig(name="document", constraints=UploadConstraints(accept=[".pdf"]))

    # When a PDF is selected
    entry = selected_file(config, "example.pdf", "application/pdf")

    # Then the file is valid with no errors
    assert entry.valid
    assert entry.errors == []


def test_jpg_extension_accepts_jpeg_mime_type():
    # Given an upload input that accepts JPG files
    config = UploadConfig(name="photo", constraints=UploadConstraints(accept=[".jpg"]))

    # When a JPEG image uses the equivalent .jpeg extension
    entry = selected_file(config, "photo.jpeg", "image/jpeg")

    # Then the JPEG MIME type satisfies the JPG rule
    assert entry.valid
    assert entry.errors == []


def test_extension_alias_without_matching_mime_type_is_rejected():
    # Given an upload input that accepts JPG files
    config = UploadConfig(name="photo", constraints=UploadConstraints(accept=[".jpg"]))

    # When a .jpeg file is selected without a reported MIME type
    entry = selected_file(config, "photo.jpeg", "")

    # Then neither the configured extension nor its MIME type matches
    assert not entry.valid
    assert [error.code for error in entry.errors] == ["not_accepted"]


def test_custom_extension_is_accepted_without_a_known_mime_type():
    # Given an upload input that accepts an application's custom file extension
    config = UploadConfig(name="attachment", constraints=UploadConstraints(accept=[".custom"]))

    # When a matching file is selected without a reported MIME type
    entry = selected_file(config, "data.custom", "")

    # Then the explicit extension rule is enough to accept the file
    assert entry.valid
    assert entry.errors == []


def test_image_input_accepts_jpg():
    # Given an upload input that accepts any image MIME type
    config = UploadConfig(name="photo", constraints=UploadConstraints(accept=["image/*"]))

    # When a JPEG image is selected
    entry = selected_file(config, "photo.jpg", "image/jpeg")

    # Then the file is valid with no errors
    assert entry.valid
    assert entry.errors == []


def test_image_input_rejects_pdf():
    # Given an upload input that accepts any image MIME type
    config = UploadConfig(name="photo", constraints=UploadConstraints(accept=["image/*"]))

    # When a PDF is selected
    entry = selected_file(config, "example.pdf", "application/pdf")

    # Then the file is invalid because it is not an image
    assert not entry.valid
    assert [error.code for error in entry.errors] == ["not_accepted"]


def test_exact_mime_type_accepts_matching_file():
    # Given an upload input that accepts the PDF MIME type
    config = UploadConfig(
        name="document", constraints=UploadConstraints(accept=["application/pdf"])
    )

    # When a file with that MIME type is selected, even without an extension
    entry = selected_file(config, "document", "application/pdf")

    # Then the file is valid with no errors
    assert entry.valid
    assert entry.errors == []


def test_exact_mime_type_rejects_nonmatching_file():
    # Given an upload input that accepts the PDF MIME type
    config = UploadConfig(
        name="document", constraints=UploadConstraints(accept=["application/pdf"])
    )

    # When a JPEG image is selected
    entry = selected_file(config, "photo.jpg", "image/jpeg")

    # Then the file is invalid because its MIME type is not accepted
    assert not entry.valid
    assert [error.code for error in entry.errors] == ["not_accepted"]


def test_input_without_type_restrictions_accepts_any_file():
    # Given an upload input with no file-type restrictions
    config = UploadConfig(name="attachment", constraints=UploadConstraints(accept=[]))

    # When a file with an unknown type and extension is selected
    entry = selected_file(config, "data.custom", "")

    # Then the file is valid with no errors
    assert entry.valid
    assert entry.errors == []


def test_extension_accepts_uppercase_filename():
    # Given an upload input that accepts JPG extensions
    config = UploadConfig(name="photo", constraints=UploadConstraints(accept=[".jpg"]))

    # When an uppercase JPG filename is selected with only a generic MIME type
    entry = selected_file(config, "photo.JPG", "application/octet-stream")

    # Then the filename extension is enough to accept the file regardless of case
    assert entry.valid
    assert entry.errors == []


def test_pdf_extension_accepts_generic_mime_type():
    # Given an upload input that accepts PDF extensions
    config = UploadConfig(name="document", constraints=UploadConstraints(accept=[".pdf"]))

    # When a PDF filename is selected but the browser reports only a generic MIME type
    entry = selected_file(config, "document.pdf", "application/octet-stream")

    # Then the matching extension is enough to accept the file
    assert entry.valid
    assert entry.errors == []


def test_mime_only_input_rejects_matching_filename_with_wrong_type():
    # Given an upload input that accepts only the JPEG MIME type
    config = UploadConfig(name="photo", constraints=UploadConstraints(accept=["image/jpeg"]))

    # When a JPG filename is reported as a PHP file
    entry = selected_file(config, "photo.jpg", "application/x-httpd-php")

    # Then the filename cannot satisfy a rule that requires the JPEG MIME type
    assert not entry.valid
    assert [error.code for error in entry.errors] == ["not_accepted"]


def test_mime_only_input_accepts_matching_type_with_unexpected_extension():
    # Given an upload input that accepts MPEG audio by MIME type
    config = UploadConfig(name="audio", constraints=UploadConstraints(accept=["audio/mpeg"]))

    # When a file with an MP4 extension is reported as MPEG audio
    entry = selected_file(config, "photo.mp4", "audio/mpeg")

    # Then the matching MIME type is enough to accept the file
    assert entry.valid
    assert entry.errors == []


def test_mixed_rules_accept_file_matching_wildcard():
    # Given an upload input that accepts images, PDF extensions, or MPEG audio
    config = UploadConfig(
        name="attachment", constraints=UploadConstraints(accept=["image/*", ".pdf", "audio/mpeg"])
    )

    # When an image without a filename extension is selected
    entry = selected_file(config, "photo", "image/webp")

    # Then matching the image wildcard alone is enough
    assert entry.valid
    assert entry.errors == []


def test_mixed_rules_accept_file_matching_extension():
    # Given an upload input that accepts images, PDF extensions, or MPEG audio
    config = UploadConfig(
        name="attachment", constraints=UploadConstraints(accept=["image/*", ".pdf", "audio/mpeg"])
    )

    # When a PDF filename is selected with only a generic MIME type
    entry = selected_file(config, "document.pdf", "application/octet-stream")

    # Then matching the PDF extension alone is enough
    assert entry.valid
    assert entry.errors == []


def test_mixed_rules_accept_file_matching_exact_mime_type():
    # Given an upload input that accepts images, PDF extensions, or MPEG audio
    config = UploadConfig(
        name="attachment", constraints=UploadConstraints(accept=["image/*", ".pdf", "audio/mpeg"])
    )

    # When a file with an MP4 extension is reported as MPEG audio
    entry = selected_file(config, "photo.mp4", "audio/mpeg")

    # Then matching the MPEG audio MIME type alone is enough
    assert entry.valid
    assert entry.errors == []


def test_mixed_rules_reject_file_matching_none():
    # Given an upload input that accepts images, PDF extensions, or MPEG audio
    config = UploadConfig(
        name="attachment", constraints=UploadConstraints(accept=["image/*", ".pdf", "audio/mpeg"])
    )

    # When a plain text file is selected
    entry = selected_file(config, "notes.txt", "text/plain")

    # Then the file is rejected because none of the rules match
    assert not entry.valid
    assert [error.code for error in entry.errors] == ["not_accepted"]


@pytest.mark.parametrize(
    ("accepted_type", "reported_type"),
    [("application/pdf", "APPLICATION/PDF"), ("APPLICATION/PDF", "application/pdf")],
)
def test_exact_mime_type_matching_ignores_case(accepted_type, reported_type):
    # Given an upload input that accepts the PDF MIME type
    config = UploadConfig(name="document", constraints=UploadConstraints(accept=[accepted_type]))

    # When a file is selected with a MIME type that differs only in letter case
    entry = selected_file(config, "document", reported_type)

    # Then the file is accepted without changing its reported MIME type
    assert entry.valid
    assert entry.errors == []
    assert entry.type == reported_type
    assert config.constraints.accept == [accepted_type]


@pytest.mark.parametrize(
    ("accepted_type", "reported_type"),
    [("image/*", "IMAGE/JPEG"), ("IMAGE/*", "image/jpeg")],
)
def test_wildcard_mime_type_matching_ignores_case(accepted_type, reported_type):
    # Given an upload input that accepts any image MIME type
    config = UploadConfig(name="photo", constraints=UploadConstraints(accept=[accepted_type]))

    # When an image is selected with a MIME type whose letter case differs from the rule
    entry = selected_file(config, "photo", reported_type)

    # Then the image is accepted without changing its reported MIME type
    assert entry.valid
    assert entry.errors == []
    assert entry.type == reported_type
    assert config.constraints.accept == [accepted_type]


def test_extension_mime_type_matching_ignores_case():
    # Given an upload input that accepts JPG files
    config = UploadConfig(name="photo", constraints=UploadConstraints(accept=[".jpg"]))

    # When a .jpeg file is selected with an uppercase JPEG MIME type
    entry = selected_file(config, "photo.jpeg", "IMAGE/JPEG")

    # Then the equivalent MIME type satisfies the JPG rule regardless of case
    assert entry.valid
    assert entry.errors == []
    assert entry.type == "IMAGE/JPEG"
