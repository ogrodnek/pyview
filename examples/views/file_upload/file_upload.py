from pyview import LiveView, LiveViewSocket
from pyview.events import InfoEvent
from typing import Optional
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class FileUploadDemoContext:
    files: list[str] = field(default_factory=list)
    message: Optional[str] = None


class FileUploadDemoLiveView(LiveView[FileUploadDemoContext]):
    async def mount(self, socket: LiveViewSocket[FileUploadDemoContext], _session):
        socket.context = FileUploadDemoContext()

        if socket.connected:
            await socket.subscribe("file_upload")
