from pyview.template.live_template import LiveTemplate, template_file, LiveRender
from pyview.template.utils import find_associated_file
from typing import Optional, Generic, TypeVar, Any

T = TypeVar("T")


class LiveComponent(Generic[T]):
    def __init__(self) -> None:
        pass

    async def mount(self, socket: T):
        pass

    async def update(self, socket: T, template_vars: dict[str, Any]):
        pass

    async def render(self, assigns: T, meta):
        html_render = _find_render(self)

        if html_render:
            return LiveRender(html_render, assigns, meta)

        raise NotImplementedError()


def _find_render(m: object) -> Optional[LiveTemplate]:
    html = find_associated_file(m, ".html")
    if html is not None:
        return template_file(html)
