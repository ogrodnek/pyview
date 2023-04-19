from typing import TypeVar, Generic, Optional, Union
from .live_socket import LiveViewSocket, UnconnectedSocket
from pyview.template import LiveTemplate, template_file, RenderedContent, LiveRender
import inspect
from pyview.events import InfoEvent

T = TypeVar("T")

AnySocket = Union[LiveViewSocket[T], UnconnectedSocket[T]]


class LiveView(Generic[T]):
    def __init__(self):
        pass

    async def mount(self, socket: AnySocket):
        pass

    async def handle_event(self, event, payload, socket: LiveViewSocket[T]):
        pass

    async def handle_info(self, event: InfoEvent, socket: LiveViewSocket[T]):
        pass

    async def handle_params(self, url, params, socket: AnySocket):
        pass

    async def render(self, assigns: T) -> RenderedContent:
        html_render = _find_render(self)

        if html_render:
            return LiveRender(html_render, assigns)

        raise NotImplementedError()


def _find_render(m: LiveView) -> Optional[LiveTemplate]:
    cf = inspect.getfile(m.__class__)
    return _find_template(cf)


def _find_template(cf: str) -> Optional[LiveTemplate]:
    if cf.endswith(".py"):
        cf = cf[:-3]
        return template_file(cf + ".html")
