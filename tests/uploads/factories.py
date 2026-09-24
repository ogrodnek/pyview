def upload_entry_data(
    *,
    path: str,
    ref: str = "0",
    name: str = "example.pdf",
    file_type: str = "application/pdf",
    size: int = 4,
) -> dict[str, str | int]:
    """Build browser file metadata without selecting or approving an upload."""
    return {
        "ref": ref,
        "name": name,
        "type": file_type,
        "size": size,
        "path": path,
    }
