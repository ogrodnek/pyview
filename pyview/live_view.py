from typing import Any, Generic, Optional, TypeVar
from urllib.parse import ParseResult

from pyview.events import InfoEvent
from pyview.meta import PyViewMeta
from pyview.template import (
    LiveRender,
    LiveTemplate,
    RenderedContent,
    find_associated_file,
    template_file,
)

from .live_socket import ConnectedLiveViewSocket, LiveViewSocket

T = TypeVar("T")

Session = dict[str, Any]
URL = ParseResult


class LiveView(Generic[T]):
    def __init__(self):
        pass

    async def mount(self, socket: LiveViewSocket[T], session: Session):
        pass

    async def handle_event(self, *args, **kwargs) -> None:
        """Handle client events (clicks, form submissions).

        Common signatures:
            handle_event(self, socket, amount: int)      # new style
            handle_event(self, event, payload, socket)   # legacy style
        """
        pass

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[T]):
        pass

    async def handle_params(self, *args, **kwargs) -> None:
        """Called when URL params change.

        Common signatures:
            handle_params(self, socket, page: int = 1)   # new style
            handle_params(self, url, params, socket)     # legacy style
        """
        pass

    async def disconnect(self, socket: ConnectedLiveViewSocket[T]):
        pass

    async def render(self, assigns: T, meta: PyViewMeta) -> RenderedContent:
        html_render = _find_render(self)

        if html_render:
            return LiveRender(html_render, assigns, meta)

        raise NotImplementedError()


def _find_render(m: LiveView) -> Optional[LiveTemplate]:
    html = find_associated_file(m, ".html")
    if html is not None:
        return template_file(html)
