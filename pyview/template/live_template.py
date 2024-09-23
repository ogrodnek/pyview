from pyview.vendor.ibis import Template
from typing import Any, Union, Protocol, Optional, ClassVar
from dataclasses import asdict, Field
from .serializer import serialize
import os.path
from pyview.template.context_processor import apply_context_processors
from pyview.meta import PyViewMeta


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

    def tree(self, assigns: Assigns, meta: PyViewMeta) -> dict[str, Any]:
        if not isinstance(assigns, dict):
            assigns = serialize(assigns)
        additional_context = apply_context_processors(meta)
        return self.t.tree(additional_context | assigns)

    def render(self, assigns: Assigns, meta: PyViewMeta) -> str:
        if not isinstance(assigns, dict):
            assigns = asdict(assigns)
        additional_context = apply_context_processors(meta)
        return self.t.render(additional_context | assigns)

    def text(self, assigns: Assigns, meta: PyViewMeta) -> str:
        return self.render(assigns, meta)

    def debug(self) -> str:
        return self.t.root_node.to_str()


class RenderedContent(Protocol):
    def tree(self) -> dict[str, Any]: ...

    def text(self) -> str: ...


class LiveRender:
    def __init__(self, template: LiveTemplate, assigns: Any, meta: PyViewMeta):
        self.template = template
        self.assigns = assigns
        self.meta = meta

    def tree(self) -> dict[str, Any]:
        return self.template.tree(self.assigns, self.meta)

    def text(self) -> str:
        return self.template.text(self.assigns, self.meta)


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
        t = LiveTemplate(Template(f.read(), template_id=filename))
        _cache[filename] = (mtime, t)
        return t
