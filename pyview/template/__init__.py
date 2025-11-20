import sys

from pyview.vendor.ibis import Template

from .context_processor import context_processor
from .live_template import LiveRender, LiveTemplate, RenderedContent, template_file
from .root_template import RootTemplate, RootTemplateContext, defaultRootTemplate
from .utils import find_associated_css, find_associated_file
from .context_processor import context_processor

__all__ = [
    "Template",
    "LiveTemplate",
    "template_file",
    "RenderedContent",
    "LiveRender",
    "RootTemplate",
    "RootTemplateContext",
    "defaultRootTemplate",
    "find_associated_css",
    "find_associated_file",
    "context_processor",
]

# T-string template support is only available on Python 3.14+
if sys.version_info >= (3, 14):
    from .template_view import TemplateView

    __all__.append("TemplateView")
