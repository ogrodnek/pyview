from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from pyview.live_socket import ConnectedLiveViewSocket


@dataclass
class PyViewMeta:
    """
    Metadata passed to LiveView render and template methods.

    Attributes:
        socket: Optional reference to the connected socket (for component registration)
    """

    socket: Optional["ConnectedLiveViewSocket"] = field(default=None, repr=False)
