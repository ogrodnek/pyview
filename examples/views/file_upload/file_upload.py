from pyview import LiveView, LiveViewSocket
from pyview.uploads import UploadConfig, UploadConstraints
from dataclasses import dataclass, field
from pyview.vendor.ibis import filters
from .file_repository import FileRepository, FileEntry
import math


@filters.register
def readable_size(input) -> str:
    try:
        num = int(input)
    except Exception:
        return input

    magnitude = int(math.floor(math.log(num, 1024)))
    val = num / math.pow(1024, magnitude)
    if magnitude > 7:
        return "{:.1f} {}B".format(val, "Yi")
    return "{:3.0f} {}B".format(val, ["", "K", "M", "G", "T", "P", "E", "Z"][magnitude])


@dataclass
class FileUploadDemoContext:
    upload_config: UploadConfig
    file_repository: FileRepository = field(default_factory=FileRepository)
    uploaded_files: list[FileEntry] = field(default_factory=list)


class FileUploadDemoLiveView(LiveView[FileUploadDemoContext]):
    """
    File Upload

    File upload example, with previews and progress bars.
    """

    async def mount(self, socket: LiveViewSocket[FileUploadDemoContext], session):
        config = socket.allow_upload(
            "photos",
            constraints=UploadConstraints(
                max_file_size=1 * 1024 * 1024, max_files=3, accept=[".jpg", ".jpeg"]
            ),
        )
        socket.context = FileUploadDemoContext(upload_config=config)
        socket.live_title = "File Upload Demo"

    async def handle_event(
        self, event, payload, socket: LiveViewSocket[FileUploadDemoContext]
    ):
        if event == "cancel":
            cancel_ref = payload["ref"]
            socket.context.upload_config.cancel_entry(cancel_ref)
            return

        if event == "save":
            with socket.context.upload_config.consume_uploads() as uploads:
                for upload in uploads:
                    socket.context.file_repository.add_file(
                        upload.entry.name, upload.file.name, upload.entry.type
                    )
            socket.context.uploaded_files = [
                f for f in socket.context.file_repository.get_all_files()
            ]
