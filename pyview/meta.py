from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from pyview.components import SocketWithComponents


@dataclass
class PyViewMeta:
    """
    Metadata passed to LiveView render and template methods.

    Attributes:
        socket: Optional reference to the socket (for component registration).
                Can be either ConnectedLiveViewSocket or UnconnectedSocket.
    """

    socket: Optional["SocketWithComponents"] = field(default=None, repr=False)
