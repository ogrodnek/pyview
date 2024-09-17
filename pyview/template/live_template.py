from pyview.vendor.ibis import Template
from typing import Any, Union, Protocol, Optional, ClassVar
from dataclasses import asdict, Field
from .serializer import serialize
import os.path


class DataclassInstance(Protocol):
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]


Assigns = Union[dict[str, Any], DataclassInstance]


# TODO: should we still support this?
class DictConvertable(Protocol):
    def asdict(self) -> dict[str, Any]: ...


class LiveTemplate:
    t: Template

    def __init__(self, template: Template):
        self.t = template

    def tree(self, assigns: Assigns) -> dict[str, Any]:
        if not isinstance(assigns, dict):
            assigns = serialize(assigns)
        return self.t.tree(assigns)

    def render(self, assigns: Assigns) -> str:
        if not isinstance(assigns, dict):
            assigns = asdict(assigns)
        return self.t.render(assigns)

    def text(self, assigns: Assigns) -> str:
        return self.render(assigns)

    def debug(self) -> str:
        return self.t.root_node.to_str()


class RenderedContent(Protocol):
    def tree(self) -> dict[str, Any]: ...

    def text(self) -> str: ...


class LiveRender:
    def __init__(self, template: LiveTemplate, assigns: Any):
        self.template = template
        self.assigns = assigns

    def tree(self) -> dict[str, Any]:
        return self.template.tree(self.assigns)

    def text(self) -> str:
        return self.template.text(self.assigns)


_cache = {}


def template_file(filename: str) -> Optional[LiveTemplate]:
    """Renders a template file with the given assigns."""
    if not os.path.isfile(filename):
        return None

    mtime = os.path.getmtime(filename)
    if filename in _cache:
        cached_mtime, cached_template = _cache[filename]
        if cached_mtime == mtime:
            return cached_template

    with open(filename, "r") as f:
        t = LiveTemplate(Template(f.read()))
        _cache[filename] = (mtime, t)
        return t
