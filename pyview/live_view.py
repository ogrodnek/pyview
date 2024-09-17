from typing import TypeVar, Generic, Optional, Union, Any
from .live_socket import LiveViewSocket, ConnectedLiveViewSocket
from pyview.template import (
    LiveTemplate,
    template_file,
    RenderedContent,
    LiveRender,
    find_associated_file,
)
from pyview.events import InfoEvent
from urllib.parse import ParseResult

T = TypeVar("T")

Session = dict[str, Any]

# TODO: ideally this would always be a ParseResult, but we need to update push_patch
URL = Union[ParseResult, str]


class LiveView(Generic[T]):
    def __init__(self):
        pass

    async def mount(self, socket: LiveViewSocket[T], session: Session):
        pass

    async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[T]):
        pass

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[T]):
        pass

    async def handle_params(self, url: URL, params, socket: LiveViewSocket[T]):
        pass

    async def disconnect(self, socket: ConnectedLiveViewSocket[T]):
        pass

    async def render(self, assigns: T) -> RenderedContent:
        html_render = _find_render(self)

        if html_render:
            return LiveRender(html_render, assigns)

        raise NotImplementedError()


def _find_render(m: LiveView) -> Optional[LiveTemplate]:
    html = find_associated_file(m, ".html")
    if html is not None:
        return template_file(html)
