from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from pyview.components import SocketWithComponents


@dataclass
class PyViewMeta:
    """
    Metadata passed to LiveView render and template methods.

    Attributes:
        socket: Optional reference to the socket (for component registration).
                Can be either ConnectedLiveViewSocket or UnconnectedSocket.
        root_path: The ASGI root_path for reverse proxy path prefix mounting.
    """

    socket: Optional["SocketWithComponents"] = field(default=None, repr=False)
    root_path: str = ""

    @property
    def flash(self) -> dict[str, Any]:
        return self.socket.flash if self.socket else {}
