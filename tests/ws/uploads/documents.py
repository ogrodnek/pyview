"""A page with a PDF upload input, and the file metadata the browser sends for it."""

from pathlib import Path
from typing import Any, Callable, Optional

from pyview.live_socket import ConnectedLiveViewSocket
from pyview.live_view import LiveView
from pyview.uploads import UploadConfig, UploadConstraints

from ..views import StaticView


def pdf(
    ref: str = "0", name: str = "example.pdf", *, size: int = 4, upload: str = "document"
) -> dict[str, Any]:
    """File metadata as the browser sends it for a PDF chosen in the named upload input."""
    return {
        "path": upload,
        "ref": ref,
        "last_modified": 1,
        "name": name,
        "relative_path": "",
        "type": "application/pdf",
        "size": size,
    }


class DocumentsPage:
    """A view with one PDF upload input, and what it has seen.

    `config` and `socket` are set when the view mounts; `saved` collects the bytes of
    consumed files. Events: "save" consumes the uploads, "cancel" cancels the entry
    with the given ref, and anything else is a no-op.
    """

    def __init__(
        self,
        upload: str = "document",
        max_files: int = 1,
        *,
        external: Optional[Callable] = None,
        progress: Optional[Callable] = None,
        entry_complete: Optional[Callable] = None,
    ):
        self.saved: list[bytes] = []
        self._config: Optional[UploadConfig] = None
        self._socket: Optional[ConnectedLiveViewSocket] = None
        page = self

        class Documents(StaticView):
            async def mount(self, socket, session):
                await super().mount(socket, session)
                page._socket = socket
                page._config = socket.allow_upload(
                    upload,
                    UploadConstraints(accept=[".pdf"], max_files=max_files),
                    external=external,
                    progress=progress,
                    entry_complete=entry_complete,
                )

            async def handle_event(self, event, payload, socket):
                if event == "save":
                    with page.config.consume_uploads() as uploads:
                        page.saved.extend(Path(upload.file.name).read_bytes() for upload in uploads)
                elif event == "cancel":
                    page.config.cancel_entry(payload["ref"])

        self.view: type[LiveView] = Documents

    @property
    def config(self) -> UploadConfig:
        assert self._config is not None, "the view hasn't mounted"
        return self._config

    @property
    def socket(self) -> ConnectedLiveViewSocket:
        assert self._socket is not None, "the view hasn't mounted"
        return self._socket
